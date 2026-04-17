#!/usr/bin/env python3
"""
scheduler_daemon.py — 로보99 일정 스케줄러

모든 정기 작업을 하나의 데몬으로 관리.
tmux 세션에서 실행: tmux new-session -d -s scheduler "cd ~/robo99_hq/scripts && uv run python scheduler_daemon.py"

작업 스케줄 (KST):
  화~토 07:02  미장 마감 리포트 (claude AI)
  평일 08:00   장전 브리핑 (claude AI)
  평일 09:20   장초반 스크리닝 (Python 파이프라인)
  평일 14:00   장중 스크리닝 (Python 파이프라인)
  평일 15:40   장마감 특징주 분류 (Python + claude AI)

변경 이력:
  2026-04-04  run_script 재시도 로직 추가, 실패 시 텔레그램 알림, 타임아웃 설정 분리
"""

import atexit
import fcntl
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# vault_writer 통합 (Phase 1)
# scripts/ 디렉토리를 sys.path 에 명시 추가 — openclaw 등 외부 실행 환경에서도 import 보장
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
_VW_IMPORT_ERR: str = ""
try:
    from vault_writer import VaultWriter
    _VAULT_WRITER = None  # lazy init after BASE defined
except Exception as _e:
    import traceback
    traceback.print_exc()
    _VW_IMPORT_ERR = str(_e)
    print(f"⚠️ vault_writer import 실패: {_e} — fallback 모드 사용", file=sys.stderr)
    VaultWriter = None
    _VAULT_WRITER = None

# ── 경로 ──────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent   # robo99_hq/
SCRIPTS = Path(__file__).resolve().parent       # scripts/
LOG_DIR = BASE / "alerts"
LOG_DIR.mkdir(parents=True, exist_ok=True)

KST = pytz.timezone("Asia/Seoul")

# ── 스크립트별 타임아웃 설정 (초) ────────────────────
SCRIPT_TIMEOUTS = {
    "collect_market_data.py": 600,    # yfinance batch: 넉넉하게 10분
    "stage2_scanner.py": 480,         # 500개 종목 스캔: 8분
    "rs_ranking.py": 600,             # RS 랭킹: 10분 (종목 600개 순차 요청)
    "geek_filter.py": 120,            # 필터링: 2분
    "stage2_briefing.py": 120,        # 브리핑 생성: 2분
    "vcp_scanner.py": 180,            # VCP 스캔: 3분
    "theme_volume_screener.py": 120,  # 테마 스크리너: 2분
}
DEFAULT_TIMEOUT = 300

def _get_vault_writer():
    """VaultWriter 싱글톤 (lazy init)."""
    global _VAULT_WRITER
    if _VAULT_WRITER is None and VaultWriter is not None:
        try:
            _VAULT_WRITER = VaultWriter(base_dir=BASE)
            log.info("vault_writer 초기화 성공")
        except Exception as e:
            log.error(f"vault_writer 초기화 실패: {e}", exc_info=True)
    return _VAULT_WRITER


def _extract_json(text: str) -> str:
    """Claude stdout 에서 JSON 블록을 추출.

    시도 순서:
      1) ```json ... ``` 코드블록
      2) 첫 '{' ~ 마지막 '}' (가장 바깥 객체)
      3) 원문 그대로 (vault_writer 가 파싱 실패 처리)
    """
    import re as _re
    # 1. 코드블록
    m = _re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", text, _re.DOTALL)
    if m:
        return m.group(1)
    # 2. 바깥쪽 braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    # 3. fallback
    return text


# ── 텔레그램 알림 (lib.telegram 위임) ──────────────────
from lib import telegram as _tg  # noqa: E402
from lib.config import TG_CHAT_ID  # noqa: E402

def notify_failure(job_name: str, detail: str):
    """실패 시 텔레그램으로 즉시 알림. lib.telegram.send_alert 위임."""
    now = datetime.now(KST).strftime("%H:%M")
    title = f"스케줄러 {now}] {job_name} 실패"
    try:
        ok = _tg.send_alert(title, detail)
        if ok:
            log.info(f"실패 알림 발송: {job_name}")
        else:
            log.warning(f"실패 알림 전송 실패 (토큰 없음?): {job_name}")
    except Exception as e:
        log.error(f"알림 발송 예외: {e}")

# ── 로깅 (로그 로테이션: 5MB × 3파일) ────────────────
from logging.handlers import RotatingFileHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            LOG_DIR / "scheduler.log",
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("scheduler")


# ── 실행 헬퍼 ─────────────────────────────────────────
def run_script(script_name: str, env_extra: dict = None, retries: int = 1, retry_delay: int = 10):
    """uv run python <script> 실행 (재시도 지원)

    Args:
        script_name: 실행할 스크립트 파일명
        env_extra: 추가 환경변수
        retries: 최대 시도 횟수 (1 = 재시도 없음, 2 = 1회 재시도)
        retry_delay: 재시도 전 대기 시간(초)
    """
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    cmd = ["uv", "run", "python", script_name]
    timeout = SCRIPT_TIMEOUTS.get(script_name, DEFAULT_TIMEOUT)

    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                log.info(f"재시도 {attempt}/{retries}: {script_name}")
                time.sleep(retry_delay)
            else:
                log.info(f"실행: {' '.join(cmd)} (timeout={timeout}s)")

            result = subprocess.run(cmd, cwd=str(SCRIPTS), env=env, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                log.info(f"{script_name} 완료")
                return True
            else:
                err_msg = result.stderr[:500] if result.stderr else "(stderr 비어있음)"
                log.error(f"{script_name} 실패 (시도 {attempt}/{retries}):\n{err_msg}")
        except subprocess.TimeoutExpired:
            log.error(f"{script_name} 타임아웃 ({timeout}초 초과, 시도 {attempt}/{retries})")
        except Exception as e:
            log.error(f"{script_name} 예외 (시도 {attempt}/{retries}): {e}")

    # 모든 시도 실패
    notify_failure(script_name, f"타임아웃({timeout}초) 또는 오류 — {retries}회 시도 후 최종 실패")
    return False


def run_claude(prompt: str, task_name: str) -> str | None:
    """Claude CLI 실행. lib.claude_runner 에 위임.

    lib.claude_runner 는 재시도 2회 + 진단 로그 (exit code, stdout 첫 200자, stderr 첫 300자)
    + 최종 실패 시 텔레그램 알림까지 포함.
    """
    from lib import claude_runner
    return claude_runner.run(prompt, task_name, retries=2, timeout=600, retry_delay=10)


# ── 작업 정의 ─────────────────────────────────────────
def job_market_report():
    """화~토 07:02 — 미장 마감 리포트"""
    log.info("=== 미장 마감 리포트 시작 ===")
    ok = run_script("collect_market_data.py", retries=2, retry_delay=15)
    if not ok:
        log.error("collect_market_data.py 최종 실패 — Claude 리포트 생략")
        return
    run_claude(
        "Read ~/CLAUDE.md. "
        "Read ~/robo99_hq/watchlist.md. "
        "Use the /market-report skill to generate today's US market closing report. "
        "Send it to Telegram chat_id 1883449676. "
        f"Save to ~/robo99_hq/alerts/report_{datetime.now(KST).strftime('%Y%m%d')}.md",
        "미장 마감 리포트",
    )


def job_premarket():
    """평일 08:00 — 장전 브리핑 (compiled context 기반 delta-only, vault_writer 경유)"""
    log.info("=== 장전 브리핑 시작 ===")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    vw = _get_vault_writer()

    # Step 1: compiled context 생성 (Python이 .state 파일 전체를 읽어 요약)
    ctx_ok = run_script("compile_premarket_context.py")
    ctx_path = f"~/robo99_hq/alerts/compiled/premarket_context_{today}.json"
    if not ctx_ok:
        log.warning("compile_premarket_context 경고 발생 — 컨텍스트 파일은 생성됨, 브리핑 계속 진행")

    # Step 2: LLM은 compiled context 한 파일만 읽고 JSON 반환
    stdout = run_claude(
        f"Read {ctx_path}. "
        f"Today is {today}. "
        "이 파일에는 장전 브리핑에 필요한 모든 엔티티 상태가 컴파일되어 있다. "
        "주요 필드: "
        "  watchlist_active[]: 각 종목의 status/thesis/last_briefed/days_since_briefed/catalysts_pending/invalidation/next_review/is_review_due. "
        "  active_events[]: 이벤트 phase, linked_tickers, last_catalyst. "
        "  prev_briefing_date + prev_briefing_summary: 어제 브리핑 내용 (반복 방지용). "
        "  screener_top[]: 전일 스크리너 상위 종목 (change_pct/vol_ratio/is_reappearance). "
        "  compile_warnings[]: 파싱 경고 목록 (ZERO_PARSE/UNRESOLVED_ALIAS 있으면 macro_context에 한 줄 언급). "
        "=== Delta-only 원칙 === "
        "DO NOT repeat yesterday's content (prev_briefing_summary 참조). "
        "For each watchlist_active ticker, output ONLY one of: "
        "(a) new_news — overnight specific headline/data not in prev_briefing_summary; "
        "(b) status_change — catalysts_pending resolved, invalidation triggered, thesis changed; "
        "(c) scheduled — is_review_due==true or known catalyst lands today; "
        "(d) no_change — no new information since last_briefed. "
        "=== 출력 형식: 반드시 JSON 만 출력 === "
        "DO NOT write any files. DO NOT send Telegram. DO NOT output markdown. "
        "Output ONLY a single JSON object: "
        '{"briefing_date": "YYYY-MM-DD", '
        '"macro_context": "1-2 line overnight macro summary", '
        '"items": [{"ticker_code": "005930", "ticker_name": "삼성전기", '
        '"change_type": "new_news|status_change|scheduled|no_change", '
        '"priority": "A|B|C", "reason": "one-line narrative", '
        '"themes": ["MLCC"], "action_hint": "intraday checkpoint"}], '
        '"unchanged_tickers": ["LITE", "NVDA"], '
        '"screener_top5": [{"ticker_code": "028050", "ticker_name": "삼성E&A", '
        '"change_pct": 5.65, "vol_ratio": 5.8, "trade_value_억": 4813, '
        '"market_cap_조": 9.9, "tag": "🚀55일신고가", "is_reappearance": true, '
        '"catalyst": "one-line reason"}], '
        f'"screener_date": "{today}"'
        "} "
        "no_change items: ticker_code + ticker_name only. "
        "non-no_change items: priority + reason required. "
        "screener_top5: screener_top 상위 5종목 그대로 사용 (is_reappearance는 컨텍스트 값 사용). "
        "Output ONLY the JSON — no explanation, no markdown, no extra text.",
        "장전 브리핑",
    )

    if stdout is None:
        log.error("장전 브리핑: Claude stdout 없음")
        return

    # vault_writer 로 처리 (검증 → 렌더 → 저장 → 텔레그램)
    if vw:
        # stdout 에서 JSON 블록 추출 (Claude 가 마크다운 코드블록으로 감쌀 수 있음)
        raw_json = _extract_json(stdout)
        result = vw.process_premarket(raw_json, run_id=f"premarket_{today}")
        log.info(f"vault_writer 결과: {json.dumps({k: v for k, v in result.items() if k != 'warnings'}, ensure_ascii=False)}")
        if result.get("warnings"):
            log.warning(f"경고: {result['warnings']}")
    else:
        # vault_writer import 실패 — live 파일 직접 쓰기 금지, quarantine 보존 후 알림
        log.error(f"vault_writer 미사용 (import 오류: {_VW_IMPORT_ERR}) — live 파일 저장 차단")
        q_dir = BASE / "alerts" / "quarantine"
        q_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        q_path = q_dir / f"{ts}_premarket_no_vault_writer.txt"
        q_path.write_text(stdout, encoding="utf-8")
        notify_failure("장전 브리핑", f"vault_writer import 실패로 파일 저장 차단. raw stdout → {q_path.name}")


def job_screening_morning():
    """평일 09:20 — 장초반 스크리닝 파이프라인"""
    log.info("=== 장초반 스크리닝 시작 ===")
    # 1. RS 랭킹 (하루 1회)
    run_script("rs_ranking.py")
    # 2. Stage2 → Geek 필터 → 브리핑 (stage2는 재시도 1회)
    ok = run_script("stage2_scanner.py", retries=2, retry_delay=15)
    if ok:
        geek_ok = run_script("geek_filter.py")
        if geek_ok:
            run_script("stage2_briefing.py")
        else:
            log.warning("geek_filter 실패 — stale 데이터 방지를 위해 briefing 스킵")
    # 3. VCP 스캐너 (자동 발송)
    run_script("vcp_scanner.py", env_extra={"VCP_AUTO_SEND": "1"})
    # 4. watchlist 교차 확인
    run_claude(
        "Read ~/CLAUDE.md and ~/robo99_hq/watchlist.md. "
        "Read ~/robo99_hq/alerts/stage2_geek_filtered.json. "
        "Check if any ACTIVE watchlist tickers appear in screening results. "
        "If yes, send a brief note to Telegram chat_id 1883449676 highlighting the overlap.",
        "watchlist 교차 확인",
    )


def job_screening_midday():
    """평일 14:00 — 장중 스크리닝 파이프라인"""
    log.info("=== 장중 스크리닝 시작 ===")
    # RS는 오전에 이미 실행 — 생략
    ok = run_script("stage2_scanner.py", retries=2, retry_delay=15)
    if ok:
        geek_ok = run_script("geek_filter.py")
        if geek_ok:
            run_script("stage2_briefing.py")   # 중복 방지는 sent_hashes로 자동 처리
        else:
            log.warning("geek_filter 실패 — stale 데이터 방지를 위해 briefing 스킵")
    run_script("vcp_scanner.py", env_extra={"VCP_AUTO_SEND": "1"})


def job_theme_screener():
    """평일 15:40 — 장마감 특징주 테마별 분류 (vault_writer 경유)"""
    log.info("=== 장마감 특징주 스크리닝 시작 ===")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    ok = run_script("theme_volume_screener.py")
    if not ok:
        log.error("theme_volume_screener.py 실패 — 스킵")
        return
    vw = _get_vault_writer()

    stdout = run_claude(
        f"Read ~/CLAUDE.md. "
        f"Read ~/robo99_hq/alerts/theme_screener.json. "
        f"Today is {today}. "
        f"=== 사전 컨텍스트 읽기 === "
        f"Glob ~/robo99_hq/themes/active/*.md and read their frontmatter to know which themes are already tracked. "
        f"Glob ~/robo99_hq/tickers/.state/*.yaml — note which stocks already have entity state (재등장 판단용). "
        f"=== 출력 형식: 반드시 JSON 만 출력 === "
        f"DO NOT write any files. DO NOT send Telegram. DO NOT output markdown. "
        f"Output ONLY a single JSON object to stdout with this exact structure: "
        '{"briefing_date": "YYYY-MM-DD", '
        '"header": "[YYYY-MM-DD 특징주 테마별 분류] / 기준: ...", '
        '"groups": [{"theme": "테마명", "narrative": "one-line WHY", '
        '"stocks": [{"ticker_code": "005930", "ticker_name": "삼성전기", '
        '"change_pct": 5.45, "vol_ratio": 2.5, "trade_value_억": 1597, '
        '"market_cap_조": 5.7, "tag": "🚀55일신고가", "is_reappearance": false}]}], '
        '"misc_stocks": [{"ticker_code": "...", "ticker_name": "...", '
        '"change_pct": 0, "vol_ratio": 0, "trade_value_억": 0, '
        '"market_cap_조": 0, "tag": "", "is_reappearance": false, '
        '"catalyst": "individual catalyst line"}]} '
        f"Rules for grouping: "
        f"1) Group stocks by shared catalyst/theme (use AI judgment, not just the theme field). "
        f"   재사용 가능한 테마명이 themes/active 에 이미 존재하면 그 이름을 그대로 사용 (새 이름 만들지 말 것). "
        f"2) For each group: narrative explains WHY these stocks moved together today. "
        f"3) Ungrouped stocks go in misc_stocks with individual catalyst lines. "
        f"4) is_reappearance=true if ticker already exists in tickers/.state with recent last_seen. "
        f"Output ONLY the JSON — no explanation, no markdown, no extra text.",
        "장마감 특징주 분류",
    )

    if stdout is None:
        log.error("장마감 특징주: Claude stdout 없음")
        return

    if vw:
        raw_json = _extract_json(stdout)
        result = vw.process_theme_screener(raw_json, run_id=f"theme_{today}")
        log.info(f"vault_writer 결과: {json.dumps({k: v for k, v in result.items() if k != 'warnings'}, ensure_ascii=False)}")
        if result.get("warnings"):
            log.warning(f"경고: {result['warnings']}")
    else:
        # vault_writer import 실패 — live 파일 직접 쓰기 금지, quarantine 보존 후 알림
        log.error(f"vault_writer 미사용 (import 오류: {_VW_IMPORT_ERR}) — live 파일 저장 차단")
        q_dir = BASE / "alerts" / "quarantine"
        q_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        q_path = q_dir / f"{ts}_theme_screener_no_vault_writer.txt"
        q_path.write_text(stdout, encoding="utf-8")
        notify_failure("장마감 특징주 분류", f"vault_writer import 실패로 파일 저장 차단. raw stdout → {q_path.name}")


def job_system_health():
    """매일 23:00 — 시스템 자가 점검"""
    log.info("=== 시스템 자가 점검 시작 ===")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    # 1. watchlist 동기화 확인
    run_script("sync_watchlist.py")
    # 2. Claude가 오늘의 스케줄러 로그를 분석하고 요약
    run_claude(
        "Read ~/CLAUDE.md. "
        f"Today is {today}. Run a system health check: "
        "1) Read ~/robo99_hq/alerts/scheduler.log — count today's successes and failures. "
        "2) Read ~/robo99_hq/alerts/watchlist_sync.json — check if any events are missing from watchlist.md. "
        "   If missing events exist, update watchlist.md to add them in the appropriate section (ACTIVE or MONITORING). "
        "3) Check the freshness of key data files: alerts/market_snapshot_*.json, alerts/rs_rankings.json, alerts/stage2_geek_filtered.json. "
        "4) Send a concise daily system health summary to Telegram chat_id 1883449676. "
        "Format: [시스템 점검 {today}] 스케줄 N/N 성공, 데이터 신선도 OK/STALE, watchlist 동기화 상태.",
        "시스템 자가 점검",
    )


def job_weekly_upgrade():
    """토요일 08:00 — 히트레이트 분석 + 시장 레짐 파라미터 업그레이드"""
    log.info("=== weekly_market_upgrade 시작 ===")
    result = run_script("weekly_market_upgrade.py", retries=1)
    if result is None:
        notify_failure("weekly_market_upgrade", "weekly_market_upgrade.py 실행 실패")


def job_vault_push():
    """매일 23:10 — Obsidian 볼트 변경사항 GitHub 자동 push"""
    log.info("=== vault git push 시작 ===")
    import subprocess
    try:
        # 변경사항 스테이징
        subprocess.run(["git", "add", "-A"], cwd=str(BASE), check=True, capture_output=True)

        # 변경사항 있는지 확인
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(BASE), capture_output=True
        )
        if diff.returncode == 0:
            log.info("변경사항 없음 — push 스킵")
            return

        # 커밋
        today = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        msg = f"auto: vault sync {today}"
        subprocess.run(["git", "commit", "-m", msg], cwd=str(BASE), check=True, capture_output=True)

        # push
        result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(BASE), capture_output=True, text=True
        )
        if result.returncode == 0:
            log.info("vault push 완료")
        else:
            log.error(f"vault push 실패: {result.stderr[:200]}")
            from lib import telegram
            telegram.send_alert("vault push 실패", result.stderr[:200])

    except Exception as e:
        log.error(f"vault push 예외: {e}")


# ── 메인 ──────────────────────────────────────────────
LOCKFILE = BASE / "alerts" / ".scheduler.lock"


def _acquire_lock():
    """PID lockfile 로 동시 실행 방지. 실패 시 즉시 종료."""
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    fd = open(LOCKFILE, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"이미 다른 스케줄러가 실행 중입니다 (lockfile: {LOCKFILE})", file=sys.stderr)
        sys.exit(1)
    fd.write(str(os.getpid()))
    fd.flush()
    atexit.register(lambda: (fd.close(), LOCKFILE.unlink(missing_ok=True)))
    return fd


def main():
    _acquire_lock()
    log.info("스케줄러 데몬 시작")
    log.info(f"작업 디렉토리: {BASE}")
    log.info(f"sys.path[0]: {sys.path[0] if sys.path else '(empty)'}")
    log.info(f"VaultWriter class: {'loaded' if VaultWriter is not None else 'NONE — import 실패'}"
             + (f" (err: {_VW_IMPORT_ERR})" if _VW_IMPORT_ERR else ""))

    sched = BlockingScheduler(timezone=KST)

    # 화~토 07:02 — 미장 마감 리포트 (미국장 Mon-Fri ET = KST Tue-Sat)
    sched.add_job(job_market_report, CronTrigger(day_of_week="tue-sat", hour=7, minute=2, timezone=KST),
                  id="market_report", max_instances=1, misfire_grace_time=300)

    # 평일 08:00 — 장전 브리핑
    sched.add_job(job_premarket, CronTrigger(day_of_week="mon-fri", hour=8, minute=0, timezone=KST),
                  id="premarket", max_instances=1, misfire_grace_time=300)

    # 평일 09:20 — 장초반 스크리닝
    sched.add_job(job_screening_morning, CronTrigger(day_of_week="mon-fri", hour=9, minute=20, timezone=KST),
                  id="screening_morning", max_instances=1, misfire_grace_time=120)

    # 평일 14:00 — 장중 스크리닝
    sched.add_job(job_screening_midday, CronTrigger(day_of_week="mon-fri", hour=14, minute=0, timezone=KST),
                  id="screening_midday", max_instances=1, misfire_grace_time=120)

    # 평일 15:40 — 장마감 특징주 분류
    sched.add_job(job_theme_screener, CronTrigger(day_of_week="mon-fri", hour=15, minute=40, timezone=KST),
                  id="theme_screener", max_instances=1, misfire_grace_time=300)

    # 매일 23:00 — 시스템 자가 점검
    sched.add_job(job_system_health, CronTrigger(hour=23, minute=0, timezone=KST),
                  id="system_health", max_instances=1, misfire_grace_time=600)

    # 매일 23:10 — vault GitHub push
    sched.add_job(job_weekly_upgrade, CronTrigger(day_of_week="sat", hour=8, minute=0, timezone=KST),
                  id="weekly_upgrade", name="주간 히트레이트·레짐 업그레이드",
                  misfire_grace_time=3600, max_instances=1)

    sched.add_job(job_vault_push, CronTrigger(hour=23, minute=10, timezone=KST),
                  id="vault_push", max_instances=1, misfire_grace_time=300)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: (sched.shutdown(wait=False), sys.exit(0)))

    log.info("스케줄 등록 완료:")
    log.info("  화~토 07:02 — 미장 마감 리포트")
    log.info("  평일 08:00 — 장전 브리핑")
    log.info("  평일 09:20 — 장초반 스크리닝")
    log.info("  평일 14:00 — 장중 스크리닝")
    log.info("  평일 15:40 — 장마감 특징주 분류")
    log.info("  매일 23:00 — 시스템 자가 점검")
    log.info("  매일 23:10 — vault GitHub push")

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("스케줄러 종료")


if __name__ == "__main__":
    main()

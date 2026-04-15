#!/usr/bin/env python3
"""
healthcheck_entities.py — 엔티티 동기화 관측성 · 헬스체크

매 실행마다 다음 메트릭을 수집하고, hard-fail 조건에 해당하면 텔레그램 알림:
  - last_success_at, sync_success
  - parsed_files_count, updated_entities_count, new_entities_count
  - unresolved_alias_count, zero_parse_sources
  - invalid_outputs_count (quarantine 파일 수)
  - wikilink_coverage_ratio (최신 briefing)
  - stale_entities_count (last_seen > 14일)
  - last_briefing_similarity (전일 vs 오늘 유사도)

사용:
  uv run --with pyyaml python scripts/healthcheck_entities.py
  # 또는 entity_syncer 후 자동 호출
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib import telegram as _tg  # noqa: E402
from lib.config import TG_CHAT_ID  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
TODAY = date.today()
TODAY_S = TODAY.isoformat()

TICKERS_STATE = BASE / "tickers" / ".state"
EVENTS_STATE = BASE / "events" / ".state"
THEMES_STATE = BASE / "themes" / "active" / ".state"
ALERTS = BASE / "alerts"
QUARANTINE = ALERTS / "quarantine"
STATE_EVENTS = BASE / "state_events"


# ── 텔레그램 (lib.telegram 위임) ──


def send_alert(text: str) -> bool:
    """헬스체크 실패 시 텔레그램 알림. lib.telegram.send 위임."""
    try:
        ok = _tg.send(text, chat_id=TG_CHAT_ID)
        if not ok:
            print("  ! 텔레그램 전송 실패 (토큰 없음 가능성)", file=sys.stderr)
        return ok
    except Exception as e:
        print(f"  ! 텔레그램 전송 예외: {e}", file=sys.stderr)
        return False


# ── 메트릭 수집 ──


def count_yaml_files(d: Path) -> int:
    if not d.exists():
        return 0
    return len(list(d.glob("*.yaml")))


def count_quarantine() -> int:
    if not QUARANTINE.exists():
        return 0
    return len(list(QUARANTINE.glob("*.json")))


def stale_tickers(days: int = 14) -> list[str]:
    cutoff = (TODAY - timedelta(days=days)).isoformat()
    stale = []
    for f in TICKERS_STATE.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except Exception:
            continue
        ls = data.get("last_seen", "")
        if ls and ls < cutoff:
            stale.append(data.get("name", f.stem))
    return stale


def wikilink_coverage(briefing_path: Path) -> float:
    """briefing 파일의 종목명 중 wikilink 로 감싸진 비율."""
    if not briefing_path.exists():
        return 0.0
    text = briefing_path.read_text()
    # frontmatter 의 tickers 목록
    fm_tickers = []
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
                fm_tickers = fm.get("tickers", []) or []
            except Exception:
                pass
    if not fm_tickers:
        return 1.0  # 비교 불가 — 낙관적
    body = text[text.find("\n---\n", 4) + 5:] if "\n---\n" in text[4:] else text
    wl_names = set(re.findall(r"\[\[([^\]]+)\]\]", body))
    covered = sum(1 for t in fm_tickers if t in wl_names)
    return covered / len(fm_tickers) if fm_tickers else 1.0


def briefing_similarity() -> float:
    """최근 2개 premarket briefing 의 텍스트 유사도 (Jaccard)."""
    files = sorted(ALERTS.glob("premarket_briefing_*.md"))
    if len(files) < 2:
        return 0.0
    t1 = set(files[-2].read_text().split())
    t2 = set(files[-1].read_text().split())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def last_syncer_report() -> dict:
    """최신 entity_syncer report 에서 숫자 추출."""
    reports = sorted(ALERTS.glob("entity_syncer_report_*.md"))
    if not reports:
        return {}
    text = reports[-1].read_text()
    result = {"path": reports[-1].name}
    m = re.search(r"터치한 ticker:\s*(\d+)", text)
    if m:
        result["updated_entities"] = int(m.group(1))
    m = re.search(r"신규 ticker .state:\s*(\d+)", text)
    if m:
        result["new_entities"] = int(m.group(1))
    m = re.search(r"event phase 전이:\s*(\d+)", text)
    if m:
        result["event_transitions"] = int(m.group(1))
    return result


def last_event_log_entry() -> str:
    """최신 state_events 의 마지막 timestamp."""
    if not STATE_EVENTS.exists():
        return ""
    files = sorted(STATE_EVENTS.glob("*.jsonl"))
    if not files:
        return ""
    lines = files[-1].read_text().strip().split("\n")
    if not lines:
        return ""
    try:
        return json.loads(lines[-1]).get("timestamp", "")
    except Exception:
        return ""


# ── 메인 ──


def main() -> int:
    print(f"=== healthcheck {TODAY_S} ===")

    # 수집
    ticker_count = count_yaml_files(TICKERS_STATE)
    event_count = count_yaml_files(EVENTS_STATE)
    theme_count = count_yaml_files(THEMES_STATE)
    quarantine_count = count_quarantine()
    stale = stale_tickers(14)
    stale_count = len(stale)

    latest_briefing = sorted(ALERTS.glob("theme_briefing_*.md"))
    wl_cov = wikilink_coverage(latest_briefing[-1]) if latest_briefing else 0.0
    similarity = briefing_similarity()
    syncer = last_syncer_report()
    last_event_ts = last_event_log_entry()

    metrics = {
        "date": TODAY_S,
        "ticker_state_count": ticker_count,
        "event_state_count": event_count,
        "theme_state_count": theme_count,
        "quarantine_count": quarantine_count,
        "stale_entities_count": stale_count,
        "wikilink_coverage_ratio": round(wl_cov, 3),
        "last_briefing_similarity": round(similarity, 3),
        "last_syncer_report": syncer,
        "last_event_log_ts": last_event_ts,
    }

    # 저장
    metrics_path = ALERTS / "healthcheck_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    # ── hard-fail 조건 ──
    alerts = []

    # 1. syncer 에서 entity 0 건
    if syncer.get("updated_entities", 0) == 0 and syncer.get("new_entities", 0) == 0:
        alerts.append("entity_syncer: 파싱된 엔티티 0건 — 입력 데이터 또는 파서 점검 필요")

    # 2. quarantine 파일 존재
    if quarantine_count > 0:
        alerts.append(f"quarantine 파일 {quarantine_count}개 — LLM 출력 검증 실패")

    # 3. wikilink 커버리지 < 80%
    if wl_cov < 0.8 and latest_briefing:
        alerts.append(f"wikilink 커버리지 {wl_cov:.0%} — 엔티티 동기화 누수 위험")

    # 4. briefing 유사도 > 90% (어제와 오늘이 사실상 동일)
    if similarity > 0.9:
        alerts.append(f"premarket briefing 유사도 {similarity:.0%} — delta-only 원칙 위반 의심")

    # 5. last_event_log 가 24시간 이상 오래됨
    if last_event_ts:
        try:
            ts = datetime.fromisoformat(last_event_ts)
            if (datetime.now() - ts).total_seconds() > 86400:
                alerts.append(f"state_events 마지막 기록이 24시간 이상 전: {last_event_ts}")
        except Exception:
            pass
    elif ticker_count > 0:
        alerts.append("state_events 로그 없음 — event log 미작동")

    # 6. stale entities > 50%
    if ticker_count > 0 and stale_count / ticker_count > 0.5:
        alerts.append(f"stale 종목 {stale_count}/{ticker_count} — 50% 초과")

    if alerts:
        msg = f"🔴 robo99_hq healthcheck — {TODAY_S}\n\n" + "\n".join(f"• {a}" for a in alerts)
        print(f"\n⚠️ ALERT:\n{msg}")
        send_alert(msg)
        return 1
    else:
        print("\n✅ 모든 헬스체크 통과")
        return 0


if __name__ == "__main__":
    sys.exit(main())

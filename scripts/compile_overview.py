#!/usr/bin/env python3
"""
compile_overview.py — 채널 멘션 → 20_wiki/tickers/{종목코드}.md 초안 생성

Fable 5 (claude-fable-5) 를 사용해서:
  1. 채널 raw 메시지에서 많이 언급된 종목 파악
  2. 해당 종목의 원문들을 읽어 기업 분석 wiki 초안 생성
  3. 20_wiki/tickers/ 에 저장 (기존 파일 있으면 스킵)

실행:
  cd ~/robo99_hq/scripts && uv run python compile_overview.py
  또는 --ticker 플래그로 특정 종목만: --ticker 009150
  또는 --force 로 기존 파일 덮어쓰기
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.config import BASE
from lib import claude_runner
from lib.mention_matcher import load_states, find_mentions as _find_mentions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("compile_overview")

CONSENSUS_RAW = BASE / "40_consensus" / "raw"
TICKERS_LEGACY = BASE / "tickers"
STATE_DIR = TICKERS_LEGACY / ".state"
WIKI_TICKERS = BASE / "20_wiki" / "tickers"

# 최소 멘션 수 (이 이상이어야 wiki 생성)
MIN_MENTIONS = 2
# 종목당 LLM에 전달할 최대 원문 수
MAX_RAW_PER_TICKER = 20
# 원문 하나당 최대 길이
MAX_BODY_LEN = 800


def load_ticker_states() -> dict[str, dict]:
    """tickers/.state/*.yaml → {name: {ticker, name, ...}} 매핑."""
    states: dict[str, dict] = {}
    if not STATE_DIR.exists():
        return states
    for sf in STATE_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(sf.read_text(encoding="utf-8")) or {}
            name = data.get("name") or sf.stem.split("-", 1)[-1]
            if name:
                states[name] = data
        except Exception:
            pass
    return states


def collect_mentions(states: dict) -> dict[str, list[dict]]:
    """40_consensus/raw/ 전체 스캔 → 종목별 raw 파일 목록. lib.mention_matcher 위임."""
    name_to_code, code_to_name = load_states(STATE_DIR)
    mentions: dict[str, list[dict]] = defaultdict(list)

    for rf in sorted(CONSENSUS_RAW.glob("**/*.md")):
        try:
            text = rf.read_text(encoding="utf-8")
        except Exception:
            continue

        body = re.sub(r"^---.*?---\n\n?", "", text, flags=re.DOTALL).strip()
        if not body:
            continue

        try:
            parts = rf.relative_to(CONSENSUS_RAW).parts
            date_str = f"{parts[1]}-{parts[2]}-{parts[3]}" if len(parts) >= 4 else ""
        except Exception:
            date_str = ""

        found = _find_mentions(body, name_to_code, code_to_name)
        for name in found:
            mentions[name].append({
                "file": rf,
                "body": body[:MAX_BODY_LEN],
                "date": date_str,
                "channel": rf.relative_to(CONSENSUS_RAW).parts[0] if len(rf.relative_to(CONSENSUS_RAW).parts) >= 1 else "",
            })

    return mentions


def _generate_wiki(
    ticker_name: str,
    ticker_code: str,
    state: dict,
    raw_mentions: list[dict],
) -> str | None:
    """Fable 5 로 ticker wiki 초안 생성. 실패 시 None."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    sample = sorted(raw_mentions, key=lambda x: x["date"], reverse=True)[:MAX_RAW_PER_TICKER]

    raw_texts = "\n\n---\n".join(
        f"[{m['channel']} {m['date']}]\n{m['body']}" for m in sample
    )

    existing_thesis = state.get("thesis", "")
    existing_themes = ", ".join(state.get("themes", []))
    existing_status = state.get("status", "")

    prompt = (
        f"종목: {ticker_name} ({ticker_code})\n"
        f"현재 status: {existing_status}\n"
        f"알려진 thesis: {existing_thesis}\n"
        f"알려진 테마: {existing_themes}\n\n"
        f"=== 채널 원문 ({len(sample)}건) ===\n{raw_texts}\n\n"
        "=== 지시사항 ===\n"
        "위 채널 메시지들을 분석해서 아래 포맷의 ticker wiki를 작성하세요.\n"
        "알 수 없는 정보는 '(채널 데이터 없음)'으로 표기. 추측 금지.\n\n"
        f"# [Ticker] {ticker_name} ({ticker_code})\n\n"
        "## 1. 핵심 펀더멘털 (Core Fundamental)\n"
        "- 사업 구조, 주요 제품, 글로벌 포지션 1-3줄\n\n"
        "## 2. 주가 트리거 / 반복 패턴\n"
        "- 채널에서 관찰된 가격 촉매, 모멘텀 패턴 1-3개\n\n"
        "## 3. 누적 이벤트 타임라인\n"
        "- 채널에서 언급된 주요 이벤트 날짜순 목록\n\n"
        "## 4. 리스크 요인 / 오버행\n"
        "- 채널에서 언급된 리스크 1-3개\n\n"
        "## 5. 나의 매매 복기\n"
        "- (아직 기록 없음)\n\n"
        "위 형식 그대로 마크다운만 출력. 설명 없이."
    )

    return claude_runner.run(
        prompt,
        f"compile_overview_{ticker_name}",
        model="claude-fable-5",
        timeout=300,
    )


def _write_wiki(ticker_code: str, ticker_name: str, state: dict, body: str) -> Path:
    """20_wiki/tickers/{code}-{name}.md 에 atomic write."""
    WIKI_TICKERS.mkdir(parents=True, exist_ok=True)

    fname = f"{ticker_code}-{ticker_name}.md" if ticker_code else f"{ticker_name}.md"
    out_path = WIKI_TICKERS / fname

    themes = state.get("themes", [])
    status = state.get("status", "monitoring")
    fm = {
        "name": ticker_name,
        "ticker": ticker_code,
        "status": status,
        "themes": themes,
        "generated_by": "compile_overview.py",
        "generated_at": datetime.now().isoformat(),
        "source": "channel_mentions",
    }
    fm_str = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{fm_str}\n---\n\n{body.strip()}\n"

    # atomic write
    fd, tmp = tempfile.mkstemp(dir=str(WIKI_TICKERS), prefix=f".{fname}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(out_path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return out_path


def run(target_ticker: str | None = None, force: bool = False, min_mentions: int = MIN_MENTIONS):
    log.info("compile_overview 시작")

    states = load_ticker_states()
    log.info(f"종목 상태 로드: {len(states)}개")

    mentions = collect_mentions(states)
    log.info(f"멘션 있는 종목: {len(mentions)}개")

    # 처리 대상 필터링
    targets = {
        name: msgs for name, msgs in mentions.items()
        if len(msgs) >= min_mentions
    }
    if target_ticker:
        targets = {n: m for n, m in targets.items()
                   if states.get(n, {}).get("ticker") == target_ticker or n == target_ticker}

    log.info(f"wiki 생성 대상: {len(targets)}개 (멘션 {min_mentions}건 이상)")

    created = 0
    skipped = 0
    failed = 0

    for name, msgs in sorted(targets.items(), key=lambda x: -len(x[1])):
        state = states.get(name, {})
        code = str(state.get("ticker", "")).strip()

        # 기존 파일 체크
        fname = f"{code}-{name}.md" if code else f"{name}.md"
        out_path = WIKI_TICKERS / fname
        if out_path.exists() and not force:
            log.info(f"  스킵 (기존 파일): {name} ({len(msgs)}건)")
            skipped += 1
            continue

        log.info(f"  생성 중: {name} ({len(msgs)}건) → claude-fable-5")
        body = _generate_wiki(name, code, state, msgs)

        if not body:
            log.warning(f"  실패: {name} — LLM 응답 없음")
            failed += 1
            continue

        path = _write_wiki(code, name, state, body)
        log.info(f"  저장: {path.relative_to(BASE)}")
        created += 1

    log.info(f"완료 — 생성:{created} 스킵:{skipped} 실패:{failed}")
    return created, skipped, failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="특정 종목코드 또는 이름만 처리")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    parser.add_argument("--min-mentions", type=int, default=MIN_MENTIONS,
                        help=f"최소 멘션 수 (기본: {MIN_MENTIONS})")
    args = parser.parse_args()

    run(target_ticker=args.ticker, force=args.force, min_mentions=args.min_mentions)

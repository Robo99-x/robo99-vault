#!/usr/bin/env python3
"""
consensus_digest.py — 애널 채널 일일 LLM 요약 + Telegram 발송

40_consensus/raw/ 의 오늘 파일들을 읽어서
Claude LLM으로 종목별/테마별 요약을 생성하고
Telegram으로 발송한다.

실행:
  cd ~/robo99_hq/scripts && uv run python consensus_digest.py
  scheduler_daemon.py 에서 매일 18:00 KST 자동 실행
"""
from __future__ import annotations

import logging
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.config import BASE
from lib import telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("consensus_digest")

CONSENSUS_DIR = BASE / "40_consensus"
RAW_DIR = CONSENSUS_DIR / "raw"
DIGEST_DIR = CONSENSUS_DIR / "digests"

# 메시지당 body 최대 길이 (토큰 절감)
_MAX_BODY = 600
# 채널당 최대 메시지 수
_MAX_MSGS = 60


def _read_raw_files(channel_dir: Path, target_date: date) -> list[dict]:
    """오늘 날짜 raw 파일 읽기 → 메시지 list."""
    day_dir = channel_dir / target_date.strftime("%Y/%m/%d")
    if not day_dir.exists():
        return []

    messages = []
    for f in sorted(day_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        body = re.sub(r"^---.*?---\n\n?", "", text, flags=re.DOTALL).strip()
        if not body:
            continue
        messages.append({"file": f.name, "body": body})
    return messages


def _llm_digest(channel_name: str, messages: list[dict], target_date: date) -> str | None:
    """Claude LLM으로 채널 메시지 요약. 실패 시 None."""
    from lib import claude_runner

    date_str = target_date.strftime("%Y-%m-%d")
    sample = messages[:_MAX_MSGS]
    bodies = "\n\n---\n".join(m["body"][:_MAX_BODY] for m in sample)

    prompt = (
        f"채널: {channel_name} | 날짜: {date_str} | {len(messages)}건"
        + (f" (상위 {len(sample)}건 표시)" if len(messages) > len(sample) else "")
        + f"\n\n=== 원문 ===\n{bodies}\n\n"
        "=== 지시사항 ===\n"
        "투자자 관점의 채널 일일 요약을 작성하세요.\n"
        "형식 (이 순서 그대로):\n"
        f"[{channel_name} {date_str}] 총 {len(messages)}건\n\n"
        "종목/테마별\n"
        "• 종목명: 핵심 포인트 1-2줄\n\n"
        "매크로/기타\n"
        "• 포인트 1줄\n\n"
        "3,500자 이내. 한국어. 마크다운 볼드/이탤릭 없이 plain text."
    )

    return claude_runner.run(prompt, f"consensus_digest_{channel_name}", timeout=180)


def _rule_based_digest(channel_name: str, messages: list[dict], target_date: date) -> str:
    """LLM 실패 시 fallback — rule-based 집계."""
    date_str = target_date.strftime("%Y-%m-%d")
    total = len(messages)

    tp_pat = [
        re.compile(r"목표주가[\s:]*([0-9]{3,7})(?:,000)?원"),
        re.compile(r"TP[\s:]+([0-9,]{3,10})"),
    ]
    opinion_pat = re.compile(
        r"(강력\s*매수|적극\s*매수|매수|중립|매도|BUY|HOLD|SELL)", re.I
    )
    opinion_map = {
        "강력매수": "매수", "적극매수": "매수", "매수": "매수",
        "buy": "매수", "중립": "중립", "hold": "중립",
        "보유": "중립", "매도": "매도", "sell": "매도",
    }

    by_ticker: dict[str, list[str]] = defaultdict(list)
    misc = []
    for m in messages:
        body = m["body"]
        ticker = None
        tc = re.search(r"\((\d{6})\)", body)
        if tc:
            ticker = tc.group(1)
        else:
            en = re.search(r"\b([A-Z]{2,5})\b", body)
            if en and en.group(1) not in {"AI", "IT", "FY", "YoY", "QoQ", "TP", "EPS", "PER", "ROE"}:
                ticker = en.group(1)

        line = body[:120].replace("\n", " ")
        if ticker:
            by_ticker[ticker].append(line)
        else:
            misc.append(line)

    lines = [
        f"[{channel_name} {date_str}] 총 {total}건 (rule-based fallback)",
        "",
    ]
    for ticker, excerpts in sorted(by_ticker.items()):
        lines.append(f"• {ticker}: {excerpts[0]}")
    if misc:
        lines.append("")
        lines.append(f"기타 {len(misc)}건")
    return "\n".join(lines)


def run(target_date: date | None = None):
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime("%Y-%m-%d")
    log.info(f"Digest 시작: {date_str}")

    if not RAW_DIR.exists():
        log.warning(f"RAW_DIR 없음: {RAW_DIR}")
        return

    total_digests = 0

    for channel_dir in sorted(RAW_DIR.iterdir()):
        if not channel_dir.is_dir():
            continue
        channel_name = channel_dir.name
        messages = _read_raw_files(channel_dir, target_date)
        if not messages:
            log.info(f"{channel_name}: 오늘 메시지 없음 — 스킵")
            continue

        log.info(f"{channel_name}: {len(messages)}건 → LLM 요약 중")
        digest_text = _llm_digest(channel_name, messages, target_date)

        if not digest_text:
            log.warning(f"{channel_name}: LLM 실패 — rule-based fallback 사용")
            digest_text = _rule_based_digest(channel_name, messages, target_date)

        # 파일 저장
        out_dir = DIGEST_DIR / channel_name / target_date.strftime("%Y/%m")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{date_str}_digest.md"
        out_file.write_text(digest_text, encoding="utf-8")
        log.info(f"저장: {out_file.relative_to(BASE)}")

        # Telegram 발송
        ok = telegram.send(digest_text)
        if ok:
            log.info(f"{channel_name}: Telegram 발송 완료")
        else:
            log.warning(f"{channel_name}: Telegram 발송 실패 (파일은 저장됨)")

        total_digests += 1

    log.info(f"완료: {total_digests}개 채널 처리")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="처리할 날짜 (YYYY-MM-DD, 기본: 오늘)")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else None
    run(target)

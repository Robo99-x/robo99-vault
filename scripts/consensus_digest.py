#!/usr/bin/env python3
"""
consensus_digest.py — 애널 채널 일일 집계

40_consensus/raw/ 의 오늘 파일들을 읽어서
종목별로 집계(TP/의견/Outlier)하고
40_consensus/digests/ 에 저장한다.

실행:
  cd ~/robo99_hq/scripts && uv run python consensus_digest.py
  또는 scheduler_daemon.py 에서 매일 18:00 KST 자동 실행
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("consensus_digest")

CONSENSUS_DIR = BASE / "40_consensus"
RAW_DIR = CONSENSUS_DIR / "raw"
DIGEST_DIR = CONSENSUS_DIR / "digests"

# ── 정규식 패턴 ────────────────────────────────────────────
# 목표주가
_TP_PATTERNS = [
    re.compile(r"목표주가[\s:]*([0-9]{3,7})(?:,000)?원"),
    re.compile(r"TP[\s:]+([0-9,]{3,10})"),
    re.compile(r"목표[\s]*([0-9]{3,7})(?:,000)?원"),
    re.compile(r"([0-9]{2,6})(?:,000)?원으로\s*(?:상향|하향|유지)"),
]

# 투자의견
_OPINION_PATTERNS = [
    re.compile(r"(강력\s*매수|적극\s*매수|매수\s*추가|매수|중립|매도|비중\s*확대|보유|OUTPERFORM|BUY|HOLD|SELL|OVERWEIGHT|UNDERWEIGHT)", re.I),
]

# 종목명/코드
_TICKER_PATTERNS = [
    re.compile(r"([가-힣]+(?:전자|증권|화학|건설|바이오|제약|테크|홀딩스|그룹|에너지|금융|모터스|항공))\b"),
    re.compile(r"\((\d{6})\)"),  # (종목코드)
    re.compile(r"([A-Z]{2,5})\s*\("),  # 영문 티커
]

# 의견 정규화
_OPINION_MAP = {
    "강력매수": "매수", "적극매수": "매수", "매수추가": "매수",
    "매수": "매수", "buy": "매수", "outperform": "매수", "overweight": "매수",
    "비중확대": "매수",
    "중립": "중립", "hold": "중립", "보유": "중립",
    "매도": "매도", "sell": "매도", "underweight": "매도",
}


def _extract_tp(text: str) -> int | None:
    for pat in _TP_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).replace(",", "")
            try:
                tp = int(val)
                # 천원 단위 짧게 쓴 경우 (e.g. 102 → 102,000)
                if tp < 10000:
                    tp *= 1000
                if 1000 <= tp <= 10_000_000:
                    return tp
            except ValueError:
                pass
    return None


def _extract_opinion(text: str) -> str | None:
    for pat in _OPINION_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(1).strip().replace(" ", "").lower()
            return _OPINION_MAP.get(raw)
    return None


def _extract_ticker(text: str) -> str | None:
    # 종목코드 우선
    m = re.search(r"\((\d{6})\)", text)
    if m:
        return m.group(1)
    # 영문 티커
    m = re.search(r"\b([A-Z]{2,5})\b", text)
    if m and m.group(1) not in {"AI", "IT", "FY", "YoY", "QoQ", "TP", "EPS", "PER", "ROE"}:
        return m.group(1)
    # 한글 종목명 (첫 번째만)
    m = _TICKER_PATTERNS[0].search(text)
    if m:
        return m.group(1)
    return None


def _read_raw_files(channel_dir: Path, target_date: date) -> list[dict]:
    """오늘 날짜 raw 파일 읽기 → 메시지 list."""
    day_dir = channel_dir / target_date.strftime("%Y/%m/%d")
    if not day_dir.exists():
        return []

    messages = []
    for f in sorted(day_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        # frontmatter 제거
        body = re.sub(r"^---.*?---\n\n?", "", text, flags=re.DOTALL).strip()
        if not body:
            continue
        messages.append({
            "file": f.name,
            "body": body,
            "tp": _extract_tp(body),
            "opinion": _extract_opinion(body),
            "ticker": _extract_ticker(body),
        })
    return messages


def _build_digest(channel_name: str, messages: list[dict], target_date: date) -> str:
    """메시지 리스트 → digest markdown."""
    date_str = target_date.strftime("%Y-%m-%d")
    total = len(messages)

    # 종목별 그룹핑
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    no_ticker = []
    for m in messages:
        if m["ticker"]:
            by_ticker[m["ticker"]].append(m)
        else:
            no_ticker.append(m)

    lines = [
        f"---",
        f"channel: {channel_name}",
        f"date: {date_str}",
        f"total_messages: {total}",
        f"tickers_covered: {len(by_ticker)}",
        f"generated_at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} KST",
        f"---",
        f"",
        f"# {channel_name} 컨센서스 집계 ({date_str})",
        f"",
        f"총 {total}건 | 종목 {len(by_ticker)}개",
        f"",
    ]

    for ticker, msgs in sorted(by_ticker.items()):
        tps = [m["tp"] for m in msgs if m["tp"]]
        opinions = [m["opinion"] for m in msgs if m["opinion"]]

        lines.append(f"## {ticker}")

        # TP 집계
        if tps:
            avg_tp = int(sum(tps) / len(tps))
            tp_range = f"{min(tps):,} ~ {max(tps):,}"
            lines.append(f"TP 평균: {avg_tp:,}원 | 범위: {tp_range}원 ({len(tps)}건)")

            # Outlier 탐지 (평균에서 15% 이상 이탈)
            threshold = avg_tp * 0.15
            outliers = [(m, m["tp"]) for m in msgs if m["tp"] and abs(m["tp"] - avg_tp) > threshold]
            if outliers:
                lines.append(f"⚠️ Outlier:")
                for m, tp in outliers:
                    lines.append(f"  - {m['file']}: TP {tp:,}원 (평균 대비 {(tp - avg_tp) / avg_tp * 100:+.0f}%)")

        # 의견 집계
        if opinions:
            from collections import Counter
            cnt = Counter(opinions)
            opinion_str = " / ".join(f"{k} {v}건" for k, v in cnt.most_common())
            lines.append(f"의견: {opinion_str}")

        # 원문 링크
        lines.append(f"원문: {', '.join(m['file'] for m in msgs)}")
        lines.append("")

    if no_ticker:
        lines.append(f"## 기타 (종목 미분류)")
        for m in no_ticker:
            lines.append(f"- {m['file']}")
        lines.append("")

    return "\n".join(lines)


def run(target_date: date | None = None):
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime("%Y-%m-%d")
    log.info(f"Digest 생성 시작: {date_str}")

    total_digests = 0

    for channel_dir in sorted(RAW_DIR.iterdir()):
        if not channel_dir.is_dir():
            continue
        channel_name = channel_dir.name
        messages = _read_raw_files(channel_dir, target_date)
        if not messages:
            log.info(f"{channel_name}: 오늘 메시지 없음")
            continue

        log.info(f"{channel_name}: {len(messages)}건 처리")
        digest_md = _build_digest(channel_name, messages, target_date)

        # 저장
        out_dir = DIGEST_DIR / channel_name / target_date.strftime("%Y/%m")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{date_str}_digest.md"
        out_file.write_text(digest_md, encoding="utf-8")
        log.info(f"저장: {out_file.relative_to(BASE)}")
        total_digests += 1

    log.info(f"Digest 생성 완료: {total_digests}개 채널")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="처리할 날짜 (YYYY-MM-DD, 기본: 오늘)")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else None
    run(target)

#!/usr/bin/env python3
"""
compile_channel_mentions.py — 채널 raw → 종목 .md backlink 자동 누적

각 종목 .md의 '## 채널 멘션' 섹션을 40_consensus/raw/ 게시물 기반으로 갱신.
다른 섹션(기업개요/투자포인트/수급 특징주 등)은 절대 건드리지 않음.

매칭 방식 (deterministic):
  1) 본문에서 6자리 숫자 추출 → tickers/.state/*.yaml 의 ticker 필드와 매칭
  2) 종목명 substring 매칭 (3자 이상, 제외 리스트 통과)

실행:
  cd ~/robo99_hq/scripts && uv run python compile_channel_mentions.py
"""
from __future__ import annotations

import re
import sys
import yaml
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── 경로 ────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
TICKERS_DIR = BASE / "tickers"
STATE_DIR = TICKERS_DIR / ".state"
CONSENSUS_DIR = BASE / "40_consensus" / "raw"

# ── 상수 ────────────────────────────────────────────────
SECTION_HEADER = "## 채널 멘션"
SECTION_COMMENT_PREFIX = (
    "<!-- compile_channel_mentions.py 자동 생성. 수동 편집 금지 (덮어쓰기됨)."
)
MAX_MENTIONS_PER_TICKER = 30
MIN_NAME_LENGTH = 3  # substring 매칭 최소 글자수

# 너무 짧거나 일반적이어서 substring 매칭 시 충돌 위험 → 코드 매칭만 사용
EXCLUDE_NAMES_FROM_SUBSTRING = {
    "T", "NC", "GS", "SK", "LG", "두산", "삼성", "현대", "롯데",
    "한국", "한진", "효성", "코오롱", "한화", "AT&T",
}


# ── 유틸 ────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """YAML frontmatter 분리 → (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = {}
    return fm if isinstance(fm, dict) else {}, parts[2].lstrip("\n")


def derive_title(filename: str, body: str) -> str:
    """본문 첫 비어있지 않은 줄 → 파일명 fallback."""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("<!--"):
            # 60자로 제한, 마크다운 링크 안에 들어갈 거라 ] 문자 escape
            return line[:60].replace("[", "(").replace("]", ")")
    stem = Path(filename).stem
    m = re.match(r"^\d{6}_\d+_(.+)$", stem)
    if m:
        return m.group(1).replace("_", " ")[:60]
    return stem[:60]


def load_ticker_states() -> tuple[dict, dict]:
    """tickers/.state → (name_to_ticker, code_to_name)."""
    name_to_ticker: dict[str, str] = {}
    code_to_name: dict[str, str] = {}
    if not STATE_DIR.exists():
        return name_to_ticker, code_to_name

    for sf in STATE_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(sf.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                continue
            name = data.get("name") or sf.stem.split("-", 1)[-1]
            code = str(data.get("ticker", "")).strip()
            if name:
                name_to_ticker[name] = code
            if code and code.isdigit() and len(code) == 6:
                code_to_name[code] = name
        except Exception:
            pass
    return name_to_ticker, code_to_name


def find_mentions(
    content: str,
    name_to_ticker: dict,
    code_to_name: dict,
) -> set[str]:
    """raw 본문에서 언급된 종목명 set."""
    found: set[str] = set()

    # 1) 6자리 코드 매칭 (앞뒤 숫자 없는)
    for code in re.findall(r"(?<!\d)(\d{6})(?!\d)", content):
        if code in code_to_name:
            found.add(code_to_name[code])

    # 2) 이름 substring 매칭 (3자 이상)
    for name in name_to_ticker:
        if len(name) < MIN_NAME_LENGTH:
            continue
        if name in EXCLUDE_NAMES_FROM_SUBSTRING:
            continue
        if name in content:
            found.add(name)

    return found


def format_section(mentions: list[dict], today_str: str) -> str:
    """채널별 그룹핑, 날짜 내림차순."""
    by_channel: dict[str, list[dict]] = defaultdict(list)
    for m in mentions:
        by_channel[m["channel"]].append(m)

    lines = [
        SECTION_HEADER,
        f"{SECTION_COMMENT_PREFIX} last_compiled: {today_str} -->",
        "",
    ]
    for channel in sorted(by_channel.keys()):
        items = sorted(by_channel[channel], key=lambda x: x["date"], reverse=True)
        items = items[:MAX_MENTIONS_PER_TICKER]
        lines.append(f"### {channel} ({len(items)}건)")
        for m in items:
            lines.append(f"- {m['date']} [{m['title']}]({m['rel_path']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_SECTION_RE = re.compile(r"(?ms)^## 채널 멘션\s*\n.*?(?=^## |\Z)")


def update_ticker_md(md_path: Path, section_content: str) -> bool:
    """ticker .md의 '## 채널 멘션' 섹션 교체. 다른 섹션 건드리지 않음."""
    if not md_path.exists():
        return False
    content = md_path.read_text(encoding="utf-8")

    if _SECTION_RE.search(content):
        content = _SECTION_RE.sub("", content).rstrip() + "\n\n" + section_content
    else:
        content = content.rstrip() + "\n\n" + section_content

    md_path.write_text(content, encoding="utf-8")
    return True


# ── 메인 ────────────────────────────────────────────────

def main() -> int:
    today_str = datetime.now().strftime("%Y-%m-%d")

    name_to_ticker, code_to_name = load_ticker_states()
    print(f"종목 상태 로드: names={len(name_to_ticker)} codes={len(code_to_name)}")

    if not CONSENSUS_DIR.exists():
        print(f"❌ {CONSENSUS_DIR} 없음")
        return 1

    raw_files = sorted(CONSENSUS_DIR.glob("**/*.md"))
    print(f"raw 파일: {len(raw_files)}개")

    mentions_per_ticker: dict[str, list[dict]] = defaultdict(list)
    files_with_match = 0

    for rf in raw_files:
        try:
            text = rf.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️ 읽기 실패: {rf.name} ({e})")
            continue

        fm, body = parse_frontmatter(text)

        # channel: frontmatter 우선, fallback은 경로 (40_consensus/raw/{channel}/...)
        channel = str(fm.get("channel", "")).strip()
        if not channel:
            try:
                channel = rf.relative_to(CONSENSUS_DIR).parts[0]
            except Exception:
                channel = "unknown"

        # date: frontmatter 우선, fallback은 경로 끝 (../YYYY/MM/DD/)
        date_raw = str(fm.get("date", "")).strip()
        if date_raw:
            date_str = date_raw.replace("/", "-")[:10]
        else:
            try:
                parts = rf.relative_to(CONSENSUS_DIR).parts
                # ../{channel}/YYYY/MM/DD/file.md
                if len(parts) >= 4:
                    date_str = f"{parts[1]}-{parts[2]}-{parts[3]}"
                else:
                    date_str = ""
            except Exception:
                date_str = ""

        title = derive_title(rf.name, body)
        rel_path = rf.relative_to(BASE).as_posix()

        # 제목 + 본문에서 매칭
        search_content = title + "\n" + body
        found = find_mentions(search_content, name_to_ticker, code_to_name)
        if found:
            files_with_match += 1

        for ticker_name in found:
            mentions_per_ticker[ticker_name].append({
                "channel": channel,
                "date": date_str,
                "title": title,
                "rel_path": rel_path,
            })

    print(f"멘션 발견 파일: {files_with_match}/{len(raw_files)}")
    print(f"매칭된 종목: {len(mentions_per_ticker)}개")

    sorted_tickers = sorted(
        mentions_per_ticker.items(), key=lambda x: len(x[1]), reverse=True
    )
    print("멘션 수 상위 10:")
    for name, mns in sorted_tickers[:10]:
        print(f"  - {name}: {len(mns)}건")

    # 각 종목 .md 갱신
    updated = 0
    skipped_no_file: list[str] = []
    for ticker_name, mentions in mentions_per_ticker.items():
        md_path = TICKERS_DIR / f"{ticker_name}.md"
        if not md_path.exists():
            skipped_no_file.append(ticker_name)
            continue
        section = format_section(mentions, today_str)
        if update_ticker_md(md_path, section):
            updated += 1

    print(f"\n✅ 갱신: {updated}개")
    if skipped_no_file:
        print(f"⏭️ 스킵 (.md 파일 없음): {len(skipped_no_file)}개 — {', '.join(skipped_no_file[:10])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

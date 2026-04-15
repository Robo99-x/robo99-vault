#!/usr/bin/env python3
"""
sync_watchlist.py — events/ 폴더와 watchlist.md 동기화 확인

events/ 에 있지만 watchlist.md ACTIVE 섹션에 없는 이벤트를 찾아
동기화가 필요한 항목 목록을 출력한다.

실제 watchlist.md 수정은 Claude가 판단해서 수행한다.
이 스크립트는 "뭐가 빠져있는지"만 알려주는 토큰 0 도구.

사용:
  uv run python sync_watchlist.py
  → 동기화 필요 항목이 있으면 JSON 출력 + exit 0
  → 이미 동기화 완료면 "동기화 완료" + exit 0
"""

import json
import re
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # robo99_hq/
EVENTS_DIR = BASE / "events"
WATCHLIST = BASE / "watchlist.md"
OUT_PATH = BASE / "alerts" / "watchlist_sync.json"


def get_event_files():
    """events/ 에서 템플릿 제외한 이벤트 파일 목록"""
    events = []
    for f in sorted(EVENTS_DIR.glob("*.md")):
        if f.name.startswith("_"):
            continue
        events.append(f)
    return events


def parse_event_date(filename: str) -> str | None:
    """파일명에서 날짜 추출: 2026-03-17_xxx.md → 2026-03-17"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})_", filename)
    return m.group(1) if m else None


def get_watchlist_links():
    """watchlist.md에서 이벤트 링크 추출"""
    if not WATCHLIST.exists():
        return set()
    text = WATCHLIST.read_text()
    # events/로 시작하는 링크 추출
    return set(re.findall(r"events/([^\)]+\.md)", text))


def main():
    event_files = get_event_files()
    watchlist_links = get_watchlist_links()

    missing = []
    for f in event_files:
        if f.name not in watchlist_links:
            event_date = parse_event_date(f.name)
            missing.append({
                "file": f.name,
                "date": event_date,
                "path": f"events/{f.name}",
            })

    if not missing:
        print("✅ watchlist.md 동기화 완료 — 누락 없음")
        return

    print(f"⚠️ watchlist.md에 누락된 이벤트 {len(missing)}건:")
    for m in missing:
        print(f"  - [{m['date']}] {m['file']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "checked": datetime.now().isoformat(),
        "missing_count": len(missing),
        "missing": missing,
    }, ensure_ascii=False, indent=2))
    print(f"\n상세 → {OUT_PATH}")


if __name__ == "__main__":
    main()

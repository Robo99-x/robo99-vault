#!/usr/bin/env python3
"""
migrate_events_frontmatter.py — events/ 13개 카드의 frontmatter를 통일 포맷으로 마이그레이션

지원 포맷:
  A. 이미 frontmatter 있음 (`---` 블록) → 누락 필드만 보강
  B. `- **Date:**` (대문자, 굵게)
  C. `- **date:**` (소문자, 굵게)
  D. `- Date:` (일반)

통일 후 frontmatter 스키마:
  ---
  event_date: YYYY-MM-DD
  event_type: <카테고리>
  source: <출처>
  tickers: [종목1, 종목2, ...]   # [[]] 표기 제거된 순수 이름
  themes: [테마1, 테마2, ...]
  status: ACTIVE | RESOLVED | INVALIDATED  (기본 ACTIVE)
  migrated_at: 2026-04-08
  ---

본문의 메타데이터 줄(`- Date:` `- Tickers:` 등)은 frontmatter에 흡수되었으므로 제거한다.
원본은 events_backup_20260408/ 에 이미 백업되어 있다.

사용:
  uv run python scripts/migrate_events_frontmatter.py
  uv run python scripts/migrate_events_frontmatter.py --dry-run  # 미리보기
"""

import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EVENTS_DIR = BASE / "events"
TODAY = date.today().isoformat()

# 메타데이터 키 정규화 매핑 (소문자 변환 후)
KEY_MAP = {
    "date": "event_date",
    "event type": "event_type",
    "event_type": "event_type",
    "source": "source",
    "tickers": "tickers",
    "themes": "themes",
    "status": "status",
}

LIST_KEYS = {"tickers", "themes"}


def parse_existing_frontmatter(text: str) -> tuple[dict, str]:
    """이미 frontmatter가 있으면 (dict, 본문) 반환. 없으면 ({}, 원문)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + 5:]
    fm = {}
    for line in fm_block.split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if k in KEY_MAP:
            norm_k = KEY_MAP[k]
            if norm_k in LIST_KEYS:
                # [a, b, c] 형태
                v = v.strip("[]")
                items = [x.strip().strip("[]") for x in v.split(",") if x.strip()]
                fm[norm_k] = items
            else:
                fm[norm_k] = v
    return fm, body


def parse_body_metadata(text: str) -> tuple[dict, str]:
    """본문의 `- Date:` 또는 `- **Date:**` 형식 메타라인을 추출하고 본문에서 제거."""
    fm = {}
    lines = text.split("\n")
    out_lines = []
    meta_pattern = re.compile(
        r"^\s*-\s*\*{0,2}([A-Za-z _]+?)\*{0,2}\s*:\s*\*{0,2}\s*(.*?)\s*\*{0,2}\s*$"
    )
    for line in lines:
        m = meta_pattern.match(line)
        if not m:
            out_lines.append(line)
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if key not in KEY_MAP:
            out_lines.append(line)
            continue
        norm_k = KEY_MAP[key]
        if norm_k in LIST_KEYS:
            # [[종목]], [[종목]] 또는 종목, 종목 또는 [종목]
            # [[ ]] 제거
            val_clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", val)
            val_clean = val_clean.strip("[]").strip("*").strip()
            items = [x.strip().strip("*").strip() for x in val_clean.split(",") if x.strip()]
            fm[norm_k] = items
        else:
            fm[norm_k] = val.strip("*").strip()
        # 이 줄은 본문에서 제거 (frontmatter로 흡수)
    return fm, "\n".join(out_lines)


def normalize_date(s: str) -> str:
    """다양한 날짜 표기를 YYYY-MM-DD 로."""
    s = s.strip()
    m = re.search(r"(\d{4})[-/.]?(\d{1,2})[-/.]?(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return s


def build_frontmatter(fm: dict) -> str:
    """dict → YAML 문자열 (단순, 의존성 없음)."""
    out = ["---"]
    # 정해진 순서로 출력
    order = ["event_date", "event_type", "source", "tickers", "themes", "status", "migrated_at"]
    for key in order:
        if key not in fm:
            continue
        val = fm[key]
        if key in LIST_KEYS:
            # YAML flow style
            items = ", ".join(val) if val else ""
            out.append(f"{key}: [{items}]")
        else:
            # 콜론·하이픈 안전 처리
            sval = str(val)
            if any(c in sval for c in [":", "#", "&", "*", "?", "|", ">", "<", "%", "@", "`"]) or sval.startswith("-"):
                sval = sval.replace('"', '\\"')
                sval = f'"{sval}"'
            out.append(f"{key}: {sval}")
    out.append("---\n")
    return "\n".join(out)


def migrate_one(path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """단일 파일 마이그레이션. (changed, message) 반환."""
    text = path.read_text()
    existing_fm, body_after_fm = parse_existing_frontmatter(text)

    if existing_fm:
        # 이미 frontmatter 존재 → 누락 필드 보강만
        fm = dict(existing_fm)
        body = body_after_fm
    else:
        # 본문에서 메타라인 추출
        fm, body = parse_body_metadata(text)

    # event_date 정규화
    if "event_date" in fm:
        fm["event_date"] = normalize_date(fm["event_date"])
    else:
        # 파일명에서 추출
        m = re.match(r"(\d{4}-\d{2}-\d{2})_", path.name)
        if m:
            fm["event_date"] = m.group(1)

    # 기본값 채우기
    fm.setdefault("status", "ACTIVE")
    fm.setdefault("migrated_at", TODAY)
    if "tickers" not in fm:
        fm["tickers"] = []
    if "themes" not in fm:
        fm["themes"] = []

    new_fm_block = build_frontmatter(fm)

    # 본문 앞쪽의 빈 줄 정리
    body_clean = body.lstrip("\n")
    new_text = new_fm_block + "\n" + body_clean

    if new_text == text:
        return False, "변경 없음"

    if not dry_run:
        path.write_text(new_text)
    return True, f"마이그레이션 ({len(fm)} 필드)"


def main():
    dry_run = "--dry-run" in sys.argv
    targets = sorted(EVENTS_DIR.glob("*.md"))
    targets = [p for p in targets if not p.name.startswith("_")]

    print(f"{'[DRY-RUN] ' if dry_run else ''}대상: {len(targets)}개")
    print("-" * 60)
    changed = 0
    for p in targets:
        ok, msg = migrate_one(p, dry_run=dry_run)
        flag = "✓" if ok else "·"
        print(f"  {flag} {p.name}: {msg}")
        if ok:
            changed += 1
    print("-" * 60)
    print(f"{'[DRY] ' if dry_run else ''}변경된 파일: {changed}/{len(targets)}")


if __name__ == "__main__":
    main()

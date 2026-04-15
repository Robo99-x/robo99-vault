#!/usr/bin/env python3
"""
migrate_active_themes_frontmatter.py — themes/active/*.md 에 frontmatter 추가

5개 노트는 본문에 `- **Created:**`, `- **Status:**` 가 이미 있음.
1개 (SMR) 는 헤더 없음 — 파일 정보로 default 추가.

통일 후 frontmatter:
  ---
  theme: <이름>
  phase: active             # emerging | active | fading | resolved
  created: YYYY-MM-DD
  last_updated: YYYY-MM-DD
  status_note: "<자유 텍스트>"  # 본문 Status 라인 보존
  migrated_at: 2026-04-08
  ---
"""

import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ACTIVE_DIR = BASE / "themes" / "active"
TODAY = date.today().isoformat()


def extract_meta(text: str) -> tuple[dict, str]:
    """본문에서 - **Created:** / - **Last Updated:** / - **Status:** 추출하고 제거."""
    meta = {}
    out_lines = []
    pat = re.compile(r"^\s*-\s*\*{0,2}([A-Za-z _]+?)\*{0,2}\s*:\s*\*{0,2}\s*(.*?)\s*\*{0,2}\s*$")
    for line in text.split("\n"):
        m = pat.match(line)
        if m:
            k = m.group(1).strip().lower().replace(" ", "_")
            v = m.group(2).strip().strip("*").strip()
            if k in ("created", "last_updated", "status"):
                meta[k] = v
                continue
        out_lines.append(line)
    return meta, "\n".join(out_lines)


def migrate(path: Path):
    text = path.read_text()
    if text.startswith("---\n"):
        return False, "이미 frontmatter 있음"

    meta, body = extract_meta(text)
    theme_name = path.stem  # 파일명 그대로 (CPO, MLCC, SMR, 스킨부스터, 스판덱스, 원자력)

    created = meta.get("created", TODAY)
    last_updated = meta.get("last_updated", created)
    status_note = meta.get("status", "active")

    # YAML 안전 escape
    def yval(s):
        s = str(s).replace('"', '\\"')
        if any(c in s for c in [":", "#", "&", "*", "?", "|", ">", "<", "%", "@", "`"]) or s.startswith("-"):
            return f'"{s}"'
        return s

    fm = (
        "---\n"
        f"theme: {yval(theme_name)}\n"
        f"phase: active\n"
        f"created: {created}\n"
        f"last_updated: {last_updated}\n"
        f"status_note: {yval(status_note)}\n"
        f"migrated_at: {TODAY}\n"
        "---\n\n"
    )
    new_text = fm + body.lstrip("\n")
    path.write_text(new_text)
    return True, "추가됨"


def main():
    for p in sorted(ACTIVE_DIR.glob("*.md")):
        if p.name.startswith("_"):
            continue
        ok, msg = migrate(p)
        flag = "✓" if ok else "·"
        print(f"  {flag} {p.name}: {msg}")


if __name__ == "__main__":
    main()

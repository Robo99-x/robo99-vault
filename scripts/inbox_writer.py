#!/usr/bin/env python3
"""
inbox_writer.py — 외부 입력(텔레그램 등)을 00_inbox/에 raw 파일로 저장

Usage:
    echo "뉴스 텍스트" | uv run python inbox_writer.py
    uv run python inbox_writer.py --source telegram < input.txt
    uv run python inbox_writer.py --source dart "공시 내용"

출력: 저장된 파일 경로 (stdout)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import INBOX

log = logging.getLogger("inbox_writer")


def write_raw(text: str, source: str = "telegram") -> Path:
    """raw 텍스트를 00_inbox/YYYY/MM/DD/ 에 저장하고 경로를 반환."""
    now = datetime.now()
    dir_path = INBOX / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    dir_path.mkdir(parents=True, exist_ok=True)

    filename = now.strftime("%Y-%m-%d-%H%M%S") + f"-{source}-raw.md"
    file_path = dir_path / filename
    received_at = now.strftime("%Y-%m-%d %H:%M:%S")

    content = (
        "---\n"
        "type: raw_input\n"
        f"source: {source}\n"
        f'received_at: "{received_at}"\n'
        "processed: false\n"
        "event_card_created: false\n"
        "needs_review: true\n"
        "---\n\n"
        f"# {source.capitalize()} Raw Input — {received_at}\n\n"
        "## Raw Text\n\n"
        f"{text}\n"
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=dir_path, delete=False, suffix=".tmp"
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.rename(tmp.name, file_path)
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

    return file_path


def main() -> None:
    parser = argparse.ArgumentParser(description="00_inbox raw 파일 저장")
    parser.add_argument("text", nargs="?", help="저장할 텍스트 (없으면 stdin)")
    parser.add_argument("--source", default="telegram", help="입력 출처 (기본: telegram)")
    args = parser.parse_args()

    if args.text:
        text = args.text.strip()
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        print("ERROR: 텍스트를 인자 또는 stdin으로 전달하세요.", file=sys.stderr)
        sys.exit(1)

    if not text:
        print("ERROR: 빈 텍스트는 저장하지 않습니다.", file=sys.stderr)
        sys.exit(1)

    path = write_raw(text, source=args.source)
    print(f"saved: {path}")


if __name__ == "__main__":
    main()

"""
lib/mention_matcher.py — 채널 raw 텍스트에서 종목 멘션 추출

compile_channel_mentions.py 와 compile_overview.py 가 공유하는
단일 매칭 진입점. 이 파일만 수정하면 두 스크립트 모두 반영됨.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

# 종목명 substring 매칭 최소 길이
MIN_NAME_LENGTH = 3

# 너무 짧거나 일반적이어서 오탐 위험 → 6자리 코드 매칭만 허용
EXCLUDE_NAMES = {
    "T", "NC", "GS", "SK", "LG", "두산", "삼성", "현대", "롯데",
    "한국", "한진", "효성", "코오롱", "한화", "AT&T",
}


def load_states(state_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """tickers/.state/*.yaml → (name_to_code, code_to_name).

    Returns:
        name_to_code: {종목명: 6자리코드}
        code_to_name: {6자리코드: 종목명}
    """
    name_to_code: dict[str, str] = {}
    code_to_name: dict[str, str] = {}

    if not state_dir.exists():
        return name_to_code, code_to_name

    for sf in state_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(sf.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                continue
            name = (data.get("name") or sf.stem.split("-", 1)[-1]).strip()
            code = str(data.get("ticker", "")).strip()
            if name:
                name_to_code[name] = code
            if code and code.isdigit() and len(code) == 6:
                code_to_name[code] = name
        except Exception:
            pass

    return name_to_code, code_to_name


def find_mentions(
    text: str,
    name_to_code: dict[str, str],
    code_to_name: dict[str, str],
) -> set[str]:
    """텍스트에서 언급된 종목명 set 반환.

    매칭 순서:
      1) 6자리 종목코드 (오탐 없음)
      2) 종목명 substring (MIN_NAME_LENGTH 이상, EXCLUDE_NAMES 제외)
    """
    found: set[str] = set()

    # 1) 6자리 코드
    for code in re.findall(r"(?<!\d)(\d{6})(?!\d)", text):
        if code in code_to_name:
            found.add(code_to_name[code])

    # 2) 종목명 substring
    for name in name_to_code:
        if len(name) < MIN_NAME_LENGTH:
            continue
        if name in EXCLUDE_NAMES:
            continue
        if name in text:
            found.add(name)

    return found

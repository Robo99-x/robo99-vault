#!/usr/bin/env python3
"""
schema_models.py — robo99_hq 스키마 정의

LLM 출력과 .state 파일의 구조를 코드로 명시한다.
pydantic 을 사용하되, 없으면 dataclass fallback.

스키마 버전: 1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# enum
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    NEW_NEWS = "new_news"
    STATUS_CHANGE = "status_change"
    SCHEDULED = "scheduled"
    NO_CHANGE = "no_change"


class Priority(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class TickerStatus(str, Enum):
    MONITORING = "monitoring"
    ENTERED = "entered"
    HOLD = "hold"
    RETIRED = "retired"
    DORMANT = "dormant"


class EventPhase(str, Enum):
    EMERGING = "emerging"
    ACTIVE = "active"
    FADING = "fading"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"


# ---------------------------------------------------------------------------
# LLM 출력 스키마 — Premarket Briefing
# ---------------------------------------------------------------------------

@dataclass
class PremarketItem:
    ticker_code: str          # "005930" or ticker name if code unknown
    ticker_name: str          # "삼성전기"
    change_type: str          # ChangeType value
    priority: str = ""        # "A" / "B" / "C" (only for changed items)
    reason: str = ""          # one-line narrative
    themes: list[str] = field(default_factory=list)
    action_hint: str = ""     # intraday checkpoint hint


@dataclass
class PremarketOutput:
    """LLM 이 stdout 으로 뱉어야 할 JSON 구조."""
    briefing_date: str                         # "2026-04-10"
    macro_context: str = ""                    # 1-2 line macro summary
    items: list[dict] = field(default_factory=list)     # PremarketItem dicts
    unchanged_tickers: list[str] = field(default_factory=list)  # names only
    screener_top5: list[dict] = field(default_factory=list)     # ThemeStock dicts
    screener_date: str = ""


# ---------------------------------------------------------------------------
# LLM 출력 스키마 — Theme Screener Briefing
# ---------------------------------------------------------------------------

@dataclass
class ThemeStock:
    ticker_code: str
    ticker_name: str
    change_pct: float
    vol_ratio: float
    trade_value_억: float = 0.0
    market_cap_조: float = 0.0
    tag: str = ""
    is_reappearance: bool = False
    catalyst: str = ""       # for misc (ungrouped) stocks


@dataclass
class ThemeGroup:
    theme: str               # theme name (e.g. "MLCC")
    narrative: str           # one-line WHY
    stocks: list[dict] = field(default_factory=list)  # ThemeStock dicts


@dataclass
class ThemeScreenerOutput:
    briefing_date: str
    header: str = ""
    groups: list[dict] = field(default_factory=list)       # ThemeGroup dicts
    misc_stocks: list[dict] = field(default_factory=list)  # ThemeStock dicts (ungrouped)


# ---------------------------------------------------------------------------
# 검증 유틸
# ---------------------------------------------------------------------------

_REQUIRED_PREMARKET = {"briefing_date"}
_REQUIRED_THEME_SCREENER = {"briefing_date"}


class ValidationError(Exception):
    """스키마 검증 실패."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_premarket(raw: dict) -> tuple[dict, list[str]]:
    """premarket JSON 검증. (정제된 dict, 경고 리스트) 반환. 치명적이면 raise."""
    errors = []
    warnings = []

    for key in _REQUIRED_PREMARKET:
        if key not in raw:
            errors.append(f"필수 필드 누락: {key}")

    if errors:
        raise ValidationError(errors)

    # items 정제
    items = raw.get("items", [])
    clean_items = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"items[{i}]: dict 아님, 무시")
            continue
        if not item.get("ticker_code") and not item.get("ticker_name"):
            warnings.append(f"items[{i}]: ticker 식별자 없음, 무시")
            continue
        ct = item.get("change_type", "no_change")
        valid_types = {e.value for e in ChangeType}
        if ct not in valid_types:
            warnings.append(f"items[{i}]: change_type '{ct}' 비정상 → no_change 로 대체")
            item["change_type"] = "no_change"
        clean_items.append(item)

    raw["items"] = clean_items
    return raw, warnings


def validate_theme_screener(raw: dict) -> tuple[dict, list[str]]:
    """theme screener JSON 검증."""
    errors = []
    warnings = []

    for key in _REQUIRED_THEME_SCREENER:
        if key not in raw:
            errors.append(f"필수 필드 누락: {key}")

    if errors:
        raise ValidationError(errors)

    groups = raw.get("groups", [])
    for gi, g in enumerate(groups):
        if not isinstance(g, dict):
            warnings.append(f"groups[{gi}]: dict 아님")
            continue
        if not g.get("theme"):
            warnings.append(f"groups[{gi}]: theme 이름 없음")
        stocks = g.get("stocks", [])
        for si, s in enumerate(stocks):
            if not isinstance(s, dict):
                warnings.append(f"groups[{gi}].stocks[{si}]: dict 아님")
            elif not s.get("ticker_name") and not s.get("ticker_code"):
                warnings.append(f"groups[{gi}].stocks[{si}]: ticker 식별자 없음")

    return raw, warnings


# ---------------------------------------------------------------------------
# .state 스키마 검증
# ---------------------------------------------------------------------------

_TICKER_STATE_REQUIRED = {"name"}
_EVENT_STATE_REQUIRED = {"event_id", "event_date", "phase"}
_THEME_STATE_REQUIRED = {"theme", "phase"}


def validate_ticker_state(data: dict) -> list[str]:
    """ticker .state yaml 검증. 경고 리스트 반환."""
    warnings = []
    for key in _TICKER_STATE_REQUIRED:
        if key not in data:
            warnings.append(f"ticker state: 필수 필드 누락: {key}")
    status = data.get("status", "")
    valid_statuses = {e.value for e in TickerStatus}
    if status and status not in valid_statuses:
        warnings.append(f"ticker state: status '{status}' 비정상")
    return warnings


def validate_event_state(data: dict) -> list[str]:
    warnings = []
    for key in _EVENT_STATE_REQUIRED:
        if key not in data:
            warnings.append(f"event state: 필수 필드 누락: {key}")
    phase = data.get("phase", "")
    valid_phases = {e.value for e in EventPhase}
    if phase and phase not in valid_phases:
        warnings.append(f"event state: phase '{phase}' 비정상")
    return warnings


def validate_theme_state(data: dict) -> list[str]:
    warnings = []
    for key in _THEME_STATE_REQUIRED:
        if key not in data:
            warnings.append(f"theme state: 필수 필드 누락: {key}")
    return warnings

#!/usr/bin/env python3
"""
compile_premarket_context.py — 장전 브리핑용 컴파일된 컨텍스트 생성

LLM이 57개 .state 파일을 직접 glob/read 하는 대신,
이 스크립트가 Python으로 한 번에 읽고 task-specific 컨텍스트를 만든다.

출력: alerts/compiled/premarket_context_YYYY-MM-DD.json
사용: job_premarket() 에서 run_script("compile_premarket_context.py") 호출 후
      LLM 프롬프트에 해당 JSON 경로만 전달

하드닝 원칙:
  - 0건 파싱 시 경고 기록 (silent failure 금지)
  - 출력은 atomic write (temp → rename)
  - 토큰 추정치 포함 (컨텍스트 비대 방지)
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

# ── 경로 설정 ─────────────────────────────────────────
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

BASE = _SCRIPTS.parent
TICKERS_STATE = BASE / "tickers" / ".state"
EVENTS_STATE  = BASE / "events" / ".state"
THEMES_STATE  = BASE / "themes" / "active" / ".state"
ALERTS        = BASE / "alerts"
COMPILED_DIR  = ALERTS / "compiled"
WATCHLIST     = BASE / "watchlist.md"
SCREENER_JSON = ALERTS / "theme_screener.json"

TODAY     = date.today()
TODAY_S   = TODAY.isoformat()

# ── 경고/오류 수집 (healthcheck 연동용) ───────────────
_warnings: list[str] = []


# ─────────────────────────────────────────────────────
# 1. Ticker .state 로딩
# ─────────────────────────────────────────────────────

def load_ticker_states() -> dict[str, dict]:
    """tickers/.state/*.yaml → {name: state_dict} 매핑."""
    states: dict[str, dict] = {}
    if not TICKERS_STATE.exists():
        _warnings.append("tickers/.state 디렉토리 없음")
        return states

    files = list(TICKERS_STATE.glob("*.yaml"))
    if not files:
        _warnings.append("ZERO_PARSE: tickers/.state 에 yaml 파일 없음")
        return states

    for f in files:
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            name = data.get("name") or f.stem.split("-", 1)[-1]
            states[name] = data
        except Exception as e:
            _warnings.append(f"ticker state 파싱 오류: {f.name} — {e}")

    return states


# ─────────────────────────────────────────────────────
# 2. Watchlist 파싱 — ACTIVE/MONITORING 종목 추출
# ─────────────────────────────────────────────────────

def parse_watchlist() -> tuple[list[str], list[str]]:
    """watchlist.md → (active_names, monitoring_names).

    마크다운 테이블 행에서 [[종목명]] 패턴을 추출한다.
    """
    if not WATCHLIST.exists():
        _warnings.append("watchlist.md 없음")
        return [], []

    text = WATCHLIST.read_text(encoding="utf-8")
    active: list[str] = []
    monitoring: list[str] = []

    # 섹션 구분
    active_section = re.search(
        r"##\s*🔴\s*ACTIVE.*?(?=##|\Z)", text, re.DOTALL
    )
    monitoring_section = re.search(
        r"##\s*🟡\s*MONITORING.*?(?=##|\Z)", text, re.DOTALL
    )

    wikilink_pat = re.compile(r"\[\[([^\]|]+?)(?:\([^)]*\))?\]\]")

    def extract_names(section_text: str) -> list[str]:
        names = []
        for line in section_text.splitlines():
            if "|" not in line:
                continue
            for m in wikilink_pat.finditer(line):
                name = m.group(1).strip()
                if name and name not in names:
                    names.append(name)
        return names

    if active_section:
        active = extract_names(active_section.group(0))
    if monitoring_section:
        monitoring = extract_names(monitoring_section.group(0))

    if not active and not monitoring:
        _warnings.append("ZERO_PARSE: watchlist.md에서 종목 추출 0건")

    return active, monitoring


# ─────────────────────────────────────────────────────
# 3. Events .state 로딩
# ─────────────────────────────────────────────────────

def load_event_states() -> list[dict]:
    """events/.state/*.yaml → phase·catalyst 요약 리스트."""
    events: list[dict] = []
    if not EVENTS_STATE.exists():
        return events

    for f in sorted(EVENTS_STATE.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            phase = data.get("phase", "")
            if phase in ("resolved", "invalidated"):
                continue  # 종료된 이벤트 제외
            events.append({
                "event_id":       data.get("event_id", f.stem),
                "phase":          phase,
                "event_date":     str(data.get("event_date", "")),
                "expires_on":     str(data.get("expires_on", "")),
                "last_catalyst":  str(data.get("last_catalyst", "")),
                "last_reviewed":  str(data.get("last_reviewed", "")),
                "linked_tickers": [
                    t.get("ticker", t) if isinstance(t, dict) else t
                    for t in data.get("linked_tickers_seen", [])
                ],
            })
        except Exception as e:
            _warnings.append(f"event state 파싱 오류: {f.name} — {e}")

    return events


# ─────────────────────────────────────────────────────
# 4. 이전 브리핑 요약
# ─────────────────────────────────────────────────────

def load_prev_briefing_summary(max_chars: int = 800) -> tuple[str, str]:
    """가장 최근 premarket_briefing_*.md → (date_str, summary).

    frontmatter 제외한 본문 첫 max_chars 자만 반환 (토큰 절감).
    """
    files = sorted(ALERTS.glob("premarket_briefing_*.md"))
    # 오늘 파일은 제외 (아직 생성 전)
    prev_files = [f for f in files if TODAY_S not in f.name]
    if not prev_files:
        return "", ""

    latest = prev_files[-1]
    date_str = re.search(r"\d{4}-\d{2}-\d{2}", latest.name)
    date_str = date_str.group(0) if date_str else latest.stem

    text = latest.read_text(encoding="utf-8")
    # frontmatter(--- ... ---) 제거
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
    summary = body[:max_chars]
    if len(body) > max_chars:
        summary += "…(생략)"

    return date_str, summary


# ─────────────────────────────────────────────────────
# 5. Screener JSON 요약
# ─────────────────────────────────────────────────────

def load_screener_summary(top_n: int = 10) -> list[dict]:
    """theme_screener.json → 상위 종목 요약 (RS proxy 기준 상위 top_n)."""
    if not SCREENER_JSON.exists():
        _warnings.append("theme_screener.json 없음")
        return []

    try:
        data = json.loads(SCREENER_JSON.read_text(encoding="utf-8"))
        stocks = data.get("stocks", [])
        if not stocks:
            _warnings.append("ZERO_PARSE: theme_screener.json stocks 0건")
            return []

        # change_pct 내림차순 정렬 후 상위 N개
        sorted_stocks = sorted(
            stocks,
            key=lambda s: float(s.get("change_pct", 0) or 0),
            reverse=True
        )[:top_n]

        return [
            {
                "ticker_code":      s.get("ticker_code", ""),
                "ticker_name":      s.get("ticker_name", ""),
                "change_pct":       s.get("change_pct", 0),
                "vol_ratio":        s.get("vol_ratio", 0),
                "trade_value_억":   s.get("trade_value_억", 0),
                "market_cap_조":    s.get("market_cap_조", 0),
                "tag":              s.get("tag", ""),
                "theme":            s.get("theme", ""),
            }
            for s in sorted_stocks
        ]
    except Exception as e:
        _warnings.append(f"screener JSON 파싱 오류: {e}")
        return []


# ─────────────────────────────────────────────────────
# 6. 컨텍스트 조립
# ─────────────────────────────────────────────────────

def build_context() -> dict:
    ticker_states = load_ticker_states()
    active_names, monitoring_names = parse_watchlist()
    active_events = load_event_states()
    prev_date, prev_summary = load_prev_briefing_summary()
    screener_top = load_screener_summary()

    # 6-1. 워치리스트 종목별 엔티티 상태 병합
    def enrich(name: str) -> dict:
        state = ticker_states.get(name, {})
        last_briefed = state.get("last_briefed", "")
        next_review  = state.get("next_review", "")
        days_since   = None
        if last_briefed:
            try:
                delta = TODAY - date.fromisoformat(str(last_briefed))
                days_since = delta.days
            except ValueError:
                pass

        # .state에 없는 종목 → unresolved 경고
        if not state:
            _warnings.append(f"UNRESOLVED_ALIAS: '{name}' watchlist에 있으나 tickers/.state에 없음")

        return {
            "ticker_name":       name,
            "ticker_code":       state.get("ticker", state.get("ticker_code", "")),
            "status":            state.get("status", "unknown"),
            "status_since":      str(state.get("status_since", "")),
            "thesis":            state.get("thesis", ""),
            "themes":            state.get("themes", []),
            "last_briefed":      str(last_briefed),
            "days_since_briefed": days_since,
            "is_review_due":     str(next_review) == TODAY_S,
            "next_review":       str(next_review),
            "catalysts_pending": state.get("catalysts_pending", []),
            "invalidation":      state.get("invalidation", ""),
            "last_seen":         str(state.get("last_seen", "")),
            "in_state":          bool(state),
        }

    watchlist_active     = [enrich(n) for n in active_names]
    watchlist_monitoring = [enrich(n) for n in monitoring_names]

    # 6-2. 재등장 여부 표시 (screener에 나온 종목이 이미 .state에 있으면 재등장)
    state_names = set(ticker_states.keys())
    for s in screener_top:
        s["is_reappearance"] = s.get("ticker_name", "") in state_names

    # 6-3. 컨텍스트 조립
    run_id = f"ctx_{TODAY_S}_{uuid.uuid4().hex[:6]}"
    ctx = {
        "compiled_at":        datetime.now().isoformat(),
        "run_id":             run_id,
        "today":              TODAY_S,
        "prev_briefing_date": prev_date,
        "prev_briefing_summary": prev_summary,
        "watchlist_active":      watchlist_active,
        "watchlist_monitoring":  watchlist_monitoring,
        "active_events":         active_events,
        "screener_top":          screener_top,
        "compile_warnings":      _warnings,
        "stats": {
            "ticker_states_loaded":   len(ticker_states),
            "active_watchlist_count": len(watchlist_active),
            "monitoring_count":       len(watchlist_monitoring),
            "active_events_count":    len(active_events),
            "screener_top_count":     len(screener_top),
            "unresolved_aliases":     sum(1 for w in _warnings if "UNRESOLVED_ALIAS" in w),
            "zero_parse_sources":     sum(1 for w in _warnings if "ZERO_PARSE" in w),
        },
    }

    # 토큰 추정 (영어 4자/토큰, 한국어 2자/토큰 근사)
    raw_len = len(json.dumps(ctx, ensure_ascii=False))
    ctx["est_tokens"] = raw_len // 3  # 보수적 추정

    return ctx


# ─────────────────────────────────────────────────────
# 7. Atomic write
# ─────────────────────────────────────────────────────

def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.stem}_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ─────────────────────────────────────────────────────
# 8. 메인
# ─────────────────────────────────────────────────────

def main() -> int:
    ctx = build_context()
    out_path = COMPILED_DIR / f"premarket_context_{TODAY_S}.json"
    atomic_write_json(out_path, ctx)

    stats = ctx["stats"]
    print(
        f"[compile_premarket_context] {TODAY_S} 완료 | "
        f"ticker_states={stats['ticker_states_loaded']} "
        f"active={stats['active_watchlist_count']} "
        f"events={stats['active_events_count']} "
        f"screener_top={stats['screener_top_count']} "
        f"est_tokens≈{ctx['est_tokens']} "
        f"warnings={len(_warnings)}"
    )

    if _warnings:
        print("경고:", file=sys.stderr)
        for w in _warnings:
            print(f"  ! {w}", file=sys.stderr)

    # ZERO_PARSE 또는 UNRESOLVED_ALIAS 가 있으면 exit code 1 (healthcheck 감지용)
    hard_fail = any(
        "ZERO_PARSE" in w or "UNRESOLVED_ALIAS" in w for w in _warnings
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())

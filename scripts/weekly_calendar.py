#!/usr/bin/env python3
"""
weekly_calendar.py — 주간 실적·경제지표 캘린더

일요일 08:30 실행. 다음 주(월~금) 예정된:
  - 워치리스트 + 주요 US 종목 실적 발표 (yfinance)
  - 주요 경제지표 (2026 정규 일정 기반)
를 텔레그램으로 발송.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import telegram as _tg
from lib.config import BASE

# ── 워치리스트에 없어도 항상 추적할 대형주 ────────────────
ALWAYS_WATCH = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "TSM", "AMD", "AVGO", "INTC", "QCOM",
    "JPM", "GS", "BAC", "XOM", "CVX",
]

# watchlist.md 파싱 시 제외할 비-티커 단어 (테마명 등)
TICKER_BLOCKLIST = {
    "MLCC", "CPO", "SMR", "ECM", "IND", "IR", "EU", "USD",
    "KRW", "JPY", "DXY", "VIX", "ETF", "IPO", "ICT",
    "AI", "US", "OK", "IT",
}

# ── 2026 주요 경제지표 고정 일정 ─────────────────────────
# (Fed, BLS, BEA 공식 발표 일정 기반)
FIXED_EVENTS_2026: list[tuple[date, str]] = [
    # FOMC
    (date(2026, 5, 6), "FOMC 회의 (5/6~7)"),
    (date(2026, 5, 7), "FOMC 금리 결정 + 기자회견"),
    (date(2026, 6, 17), "FOMC 회의 (6/17~18)"),
    (date(2026, 6, 18), "FOMC 금리 결정 + 기자회견"),
    (date(2026, 7, 29), "FOMC 회의 (7/29~30)"),
    (date(2026, 7, 30), "FOMC 금리 결정"),
    (date(2026, 9, 16), "FOMC 회의 (9/16~17)"),
    (date(2026, 9, 17), "FOMC 금리 결정 + 기자회견"),
    (date(2026, 10, 28), "FOMC 회의 (10/28~29)"),
    (date(2026, 10, 29), "FOMC 금리 결정"),
    (date(2026, 12, 16), "FOMC 회의 (12/16~17)"),
    (date(2026, 12, 17), "FOMC 금리 결정 + 기자회견"),
    # CPI (매월 약 10~13일, 2026 추정)
    (date(2026, 4, 30), "미국 CPI (3월 확정치 추정)"),
    (date(2026, 5, 13), "미국 CPI (4월)"),
    (date(2026, 6, 11), "미국 CPI (5월)"),
    (date(2026, 7, 14), "미국 CPI (6월)"),
    (date(2026, 8, 12), "미국 CPI (7월)"),
    (date(2026, 9, 10), "미국 CPI (8월)"),
    (date(2026, 10, 14), "미국 CPI (9월)"),
    (date(2026, 11, 12), "미국 CPI (10월)"),
    (date(2026, 12, 10), "미국 CPI (11월)"),
    # NFP (매월 첫째 금요일)
    (date(2026, 5, 1), "미국 NFP (4월 고용)"),
    (date(2026, 6, 5), "미국 NFP (5월 고용)"),
    (date(2026, 7, 3), "미국 NFP (6월 고용)"),
    (date(2026, 8, 7), "미국 NFP (7월 고용)"),
    (date(2026, 9, 4), "미국 NFP (8월 고용)"),
    (date(2026, 10, 2), "미국 NFP (9월 고용)"),
    (date(2026, 11, 6), "미국 NFP (10월 고용)"),
    (date(2026, 12, 4), "미국 NFP (11월 고용)"),
    # GDP (분기별 advance — 분기 종료 후 약 4주)
    (date(2026, 4, 29), "미국 GDP Q1 속보치"),
    (date(2026, 7, 29), "미국 GDP Q2 속보치"),
    (date(2026, 10, 28), "미국 GDP Q3 속보치"),
    # PCE (매월 말)
    (date(2026, 4, 30), "미국 PCE (3월)"),
    (date(2026, 5, 29), "미국 PCE (4월)"),
    (date(2026, 6, 26), "미국 PCE (5월)"),
    (date(2026, 7, 31), "미국 PCE (6월)"),
    (date(2026, 8, 28), "미국 PCE (7월)"),
    (date(2026, 9, 25), "미국 PCE (8월)"),
    (date(2026, 10, 30), "미국 PCE (9월)"),
    (date(2026, 11, 25), "미국 PCE (10월)"),
    (date(2026, 12, 23), "미국 PCE (11월)"),
    # BOK (한국 기준금리 — 연 8회)
    (date(2026, 5, 28), "BOK 기준금리 결정"),
    (date(2026, 7, 16), "BOK 기준금리 결정"),
    (date(2026, 8, 27), "BOK 기준금리 결정"),
    (date(2026, 10, 15), "BOK 기준금리 결정"),
    (date(2026, 11, 26), "BOK 기준금리 결정"),
]


def parse_us_tickers_from_watchlist() -> list[str]:
    """watchlist.md에서 대문자 US 티커 추출. 테마명/약어 제외."""
    wl = BASE / "watchlist.md"
    if not wl.exists():
        return []
    text = wl.read_text(encoding="utf-8")
    found = re.findall(r"\[\[([A-Z]{2,5})\]\]", text)
    return [t for t in found if t.isalpha() and t not in TICKER_BLOCKLIST]


def next_week_range() -> tuple[date, date]:
    """다음 주 월요일~금요일 반환 (일요일 실행 기준)."""
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    mon = today + timedelta(days=days_until_monday)
    fri = mon + timedelta(days=4)
    return mon, fri


def get_earnings_next_week(tickers: list[str], week_start: date, week_end: date) -> list[dict]:
    """yfinance(Yahoo Finance)로 다음 주 실적 발표 종목 조회."""
    try:
        import yfinance as yf
    except ImportError:
        return []

    results = []
    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            cal = t.calendar
            if not cal:
                continue
            dates = cal.get("Earnings Date", [])
            if not dates:
                continue
            ed = dates[0] if hasattr(dates[0], "year") else None
            if ed and week_start <= ed <= week_end:
                eps_low = cal.get("Earnings Low")
                eps_high = cal.get("Earnings High")
                eps_str = ""
                if eps_low and eps_high:
                    eps_str = f"EPS ${eps_low:.2f}~${eps_high:.2f}"
                # 회사명: yfinance info shortName (API 호출 1회 — calendar 호출 시 이미 캐시됨)
                try:
                    name = t.info.get("shortName") or t.info.get("longName") or sym
                except Exception:
                    name = sym
                results.append({"ticker": sym, "name": name, "date": ed, "eps_hint": eps_str})
        except Exception:
            continue

    results.sort(key=lambda x: x["date"])
    return results


def get_econ_events(week_start: date, week_end: date) -> list[dict]:
    """고정 일정에서 해당 주 이벤트 필터링."""
    events = [
        {"date": d, "event": name}
        for d, name in FIXED_EVENTS_2026
        if week_start <= d <= week_end
    ]
    events.sort(key=lambda x: x["date"])
    return events


def format_message(
    earnings: list[dict],
    econ: list[dict],
    week_start: date,
    week_end: date,
) -> str:
    ws = week_start.strftime("%m/%d")
    we = week_end.strftime("%m/%d")
    lines = [f"주간 캘린더 ({ws}~{we})"]
    lines.append("")

    lines.append("[실적 발표]")
    if earnings:
        prev_date = None
        for e in earnings:
            if e["date"] != prev_date:
                if prev_date is not None:
                    lines.append("")
                lines.append(e["date"].strftime("%m/%d(%a)"))
                prev_date = e["date"]
            label = f"{e['ticker']} ({e['name']})" if e.get("name") and e["name"] != e["ticker"] else e["ticker"]
            hint = f"  {e['eps_hint']}" if e["eps_hint"] else ""
            lines.append(f"{label}{hint}")
    else:
        lines.append("없음")
    lines.append("")

    lines.append("[주요 경제지표]")
    if econ:
        prev_date = None
        for e in econ:
            if e["date"] != prev_date:
                if prev_date is not None:
                    lines.append("")
                lines.append(e["date"].strftime("%m/%d(%a)"))
                prev_date = e["date"]
            lines.append(f"• {e['event']}")
    else:
        lines.append("없음")

    return "\n".join(lines)


def main():
    week_start, week_end = next_week_range()

    wl_tickers = parse_us_tickers_from_watchlist()
    all_tickers = list(dict.fromkeys(ALWAYS_WATCH + wl_tickers))

    print(f"다음 주 {week_start}~{week_end}, 티커 {len(all_tickers)}개 조회 중...")
    earnings = get_earnings_next_week(all_tickers, week_start, week_end)
    print(f"  실적 {len(earnings)}건")

    econ = get_econ_events(week_start, week_end)
    print(f"  경제지표 {len(econ)}건")

    msg = format_message(earnings, econ, week_start, week_end)
    print(msg)

    ok = _tg.send(msg)
    if ok:
        print("텔레그램 발송 완료")
    else:
        print("텔레그램 발송 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

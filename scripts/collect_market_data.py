#!/usr/bin/env python3
"""미장 마감 데이터 수집 → alerts/market_snapshot_YYYYMMDD.json

변경 이력:
  2026-04-04  전체 심볼 1회 batch download로 변경 (타임아웃 해결)
              개별 심볼 fallback + 재시도 로직 추가
"""

import json
import time
from datetime import datetime
from pathlib import Path
import yfinance as yf

OUT = Path(__file__).resolve().parent.parent / "alerts"

INDICES = {"S&P 500": "^GSPC", "나스닥": "^IXIC", "다우": "^DJI", "VIX": "^VIX"}
MACRO = {"10Y": "^TNX", "DXY": "DX-Y.NYB", "WTI": "CL=F",
         "USD/KRW": "KRW=X", "USD/JPY": "JPY=X", "금": "GC=F"}
SECTORS = {"XLK": "XLK", "XLF": "XLF", "XLE": "XLE", "XLV": "XLV",
           "XLI": "XLI", "XLRE": "XLRE", "XLP": "XLP", "XLC": "XLC"}
WATCH = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "TSM", "AVGO", "AMD"]

# 모든 심볼을 하나의 dict로 합침 (batch download용)
ALL_SYMBOLS: dict[str, str] = {}
ALL_SYMBOLS.update(INDICES)
ALL_SYMBOLS.update(MACRO)
ALL_SYMBOLS.update(SECTORS)
ALL_SYMBOLS.update({t: t for t in WATCH})

MAX_RETRIES = 2
RETRY_DELAY = 5  # seconds


def _extract_price(data, sym: str, all_tickers: list) -> dict:
    """batch download 결과에서 개별 심볼의 가격/등락률 추출"""
    try:
        if data is not None and len(all_tickers) > 1 and sym in data.columns.get_level_values(0):
            h = data[sym]["Close"].dropna()
        elif data is not None and len(all_tickers) == 1:
            h = data["Close"].dropna()
        else:
            return None  # batch에서 못 찾음 → fallback 필요

        if len(h) >= 2:
            prev, last = float(h.iloc[-2]), float(h.iloc[-1])
            pct = ((last - prev) / prev) * 100 if prev else 0
            return {"symbol": sym, "price": round(last, 2), "change_pct": round(pct, 2)}
        elif len(h) == 1:
            return {"symbol": sym, "price": round(float(h.iloc[0]), 2)}
    except Exception:
        pass
    return None


def _fetch_single(sym: str) -> dict | None:
    """개별 심볼 fallback (batch 실패 시)"""
    try:
        h = yf.Ticker(sym).history(period="2d")["Close"].dropna()
        if len(h) >= 2:
            prev, last = float(h.iloc[-2]), float(h.iloc[-1])
            pct = ((last - prev) / prev) * 100 if prev else 0
            return {"symbol": sym, "price": round(last, 2), "change_pct": round(pct, 2)}
        elif len(h) == 1:
            return {"symbol": sym, "price": round(float(h.iloc[0]), 2)}
    except Exception:
        pass
    return None


def fetch_all() -> dict[str, dict]:
    """모든 심볼을 1회 batch download + 실패 심볼만 개별 재시도"""
    all_tickers = list(set(ALL_SYMBOLS.values()))
    result = {}
    data = None

    # 1단계: batch download (재시도 포함)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  batch download 시도 {attempt}/{MAX_RETRIES} ({len(all_tickers)}개 심볼)...")
            data = yf.download(all_tickers, period="2d", group_by="ticker", threads=True, progress=False)
            if data is not None and not data.empty:
                print(f"  batch 성공 ✓")
                break
        except Exception as e:
            print(f"  batch 시도 {attempt} 실패: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            data = None

    # 2단계: 결과 추출 + 실패 심볼 개별 fallback
    failed = []
    for name, sym in ALL_SYMBOLS.items():
        extracted = _extract_price(data, sym, all_tickers)
        if extracted:
            result[name] = extracted
        else:
            failed.append((name, sym))

    if failed:
        print(f"  {len(failed)}개 심볼 개별 재시도...")
        for name, sym in failed:
            single = _fetch_single(sym)
            if single:
                result[name] = single
            else:
                result[name] = {"symbol": sym, "error": "데이터 수집 실패"}
                print(f"    ⚠️ {name}({sym}) 최종 실패")

    return result


def collect_earnings():
    cred = Path.home() / "robo99_hq" / "secrets" / "fmp"
    if not cred.exists():
        return []
    try:
        import requests
        key = cred.read_text().strip()
        today = datetime.now().strftime("%Y-%m-%d")
        r = requests.get("https://financialmodelingprep.com/api/v3/earning_calendar",
                         params={"from": today, "to": today, "apikey": key}, timeout=15)
        return [e for e in r.json() if e.get("symbol") in WATCH]
    except Exception:
        return []


def main():
    print("📊 데이터 수집 시작...")
    snap = {"timestamp": datetime.now().isoformat(), "date": datetime.now().strftime("%Y-%m-%d")}

    # 전체 심볼 1회 batch download
    all_data = fetch_all()

    # 그룹별 분리
    snap["indices"] = {k: all_data[k] for k in INDICES if k in all_data}
    snap["macro"] = {k: all_data[k] for k in MACRO if k in all_data}
    snap["sectors"] = {k: all_data[k] for k in SECTORS if k in all_data}
    snap["watchlist"] = {t: all_data[t] for t in WATCH if t in all_data}

    print("  실적...")
    snap["earnings"] = collect_earnings()

    # 수집 통계
    total = len(ALL_SYMBOLS)
    ok = sum(1 for v in all_data.values() if "error" not in v)
    snap["_meta"] = {"total_symbols": total, "success": ok, "failed": total - ok}
    print(f"  수집 완료: {ok}/{total} 성공")

    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"market_snapshot_{datetime.now():%Y%m%d}.json"
    f.write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    print(f"✅ {f}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""RS ranking for KOSPI/KOSDAQ
- Universe: top 300 by market cap each; fallback: market cap >= 5000억원
- RS score = 0.6*3M + 0.4*6M return
"""
from datetime import datetime, timedelta
import json
import os
import sys
import time
import traceback
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pykrx import stock
import FinanceDataReader as fdr
import krx_login
krx_login.login_krx()
import pandas as pd

from lib import config  # noqa: E402

CAP_FALLBACK = 5_0000_0000_000  # 5,000억원 (KRW)
TOP_N = 300
LOG_PATH = str(config.ALERTS / "rs_ranking.err")
TICKER_CACHE = str(config.ALERTS / "ticker_cache.json")
RS_OUT_PATH = str(config.ALERTS / "rs_rankings.json")


def _log_err(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def _date(days):
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")


def _fallback_tickers():
    if not os.path.exists(TICKER_CACHE):
        _log_err("ticker_cache.json not found for fallback")
        return []
    with open(TICKER_CACHE, "r") as f:
        return json.load(f).get("top_tickers", [])


def _normalize_cap_columns(df):
    """pykrx가 장 시작 전 영문 칼럼을 반환하는 경우 한글로 정규화"""
    col_map = {
        "Close": "종가", "MarketCap": "시가총액",
        "Volume": "거래량", "TradingValue": "거래대금",
        "Market Cap": "시가총액", "Stocks": "상장주식수",
    }
    df.columns = [col_map.get(c, c) for c in df.columns]
    return df


def _universe(date, market):
    try:
        tickers = stock.get_market_ticker_list(date, market=market)
        caps = stock.get_market_cap_by_ticker(date)
        caps = _normalize_cap_columns(caps)
        # 시가총액 칼럼이 여전히 없으면 전일로 재시도
        if "시가총액" not in caps.columns:
            prev = (datetime.strptime(date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            caps = stock.get_market_cap_by_ticker(prev)
            caps = _normalize_cap_columns(caps)
        caps = caps.loc[caps.index.isin(tickers)].sort_values("시가총액", ascending=False)
        if len(caps) >= TOP_N:
            return caps.head(TOP_N).index.tolist()
        # fallback to market cap threshold
        return caps[caps["시가총액"] >= CAP_FALLBACK].index.tolist()
    except Exception:
        _log_err(f"pykrx universe error ({market}): {traceback.format_exc().strip()}")
        return _fallback_tickers()


def _rs_scores(tickers, d0, d3m, d6m):
    out = []
    d3m_dt = pd.to_datetime(d3m)
    d6m_dt = pd.to_datetime(d6m)
    for t in tickers:
        try:
            df = stock.get_market_ohlcv_by_date(d6m, d0, t)
            if df.empty:
                continue
            c = df["종가"]
            c0 = c.iloc[-1]
            c3 = c.loc[c.index[c.index <= d3m_dt][-1]] if len(c.index[c.index <= d3m_dt]) > 0 else c.iloc[0]
            c6 = c.iloc[0]
            r3 = c0 / c3 - 1
            r6 = c0 / c6 - 1
            score = 0.6 * r3 + 0.4 * r6
            out.append((t, float(score), float(r3), float(r6)))
            time.sleep(0.1)  # NAVER rate limit 방지
            continue
        except Exception:
            _log_err(f"pykrx price error {t}: {traceback.format_exc().strip()}")

        # FDR fallback (NAVER)
        try:
            df = fdr.DataReader(t, (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d"))
            if df is None or df.empty:
                continue
            c = df["Close"]
            c0 = c.iloc[-1]
            c3 = c.loc[c.index[c.index <= d3m_dt][-1]] if len(c.index[c.index <= d3m_dt]) > 0 else c.iloc[0]
            c6 = c.loc[c.index[c.index <= d6m_dt][-1]] if len(c.index[c.index <= d6m_dt]) > 0 else c.iloc[0]
            r3 = c0 / c3 - 1
            r6 = c0 / c6 - 1
            score = 0.6 * r3 + 0.4 * r6
            out.append((t, float(score), float(r3), float(r6)))
        except Exception:
            _log_err(f"FDR price error {t}: {traceback.format_exc().strip()}")
            continue
    return out


def main():
    d0 = _date(0)
    d3m = _date(90)
    d6m = _date(180)

    all_ranked = {}  # ticker -> rs_pct (0~100)

    for market in ["KOSPI", "KOSDAQ"]:
        tickers = _universe(d0, market)
        scores = _rs_scores(tickers, d0, d3m, d6m)
        scores = sorted(scores, key=lambda x: x[1], reverse=True)
        n = len(scores)
        print(f"[{market}] RS TOP 10 (총 {n}개)")
        for rank, (t, score, r3, r6) in enumerate(scores):
            # 백분위: 1위=100, 꼴찌=0
            pct = round((n - rank) / n * 100, 1) if n > 0 else 0
            all_ranked[t] = {"rs_score": round(score * 100, 2), "rs_pct": pct, "r3m": round(r3 * 100, 1), "r6m": round(r6 * 100, 1)}
        for t, score, r3, r6 in scores[:10]:
            try:
                name = stock.get_market_ticker_name(t)
            except Exception:
                name = t
            print(f"{name}({t}) RS={score*100:.1f}% | 3M={r3*100:.1f}% | 6M={r6*100:.1f}%")
        print()

    # JSON 저장 (geek_filter.py에서 로드)
    with open(RS_OUT_PATH, "w") as f:
        json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "rankings": all_ranked}, f, ensure_ascii=False, indent=2)
    print(f"RS rankings saved → {RS_OUT_PATH} ({len(all_ranked)} tickers)")


if __name__ == "__main__":
    main()

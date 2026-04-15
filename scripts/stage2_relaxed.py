import pandas as pd
from datetime import datetime, timedelta
import json
import os
import sys
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from pykrx import stock
import krx_login
krx_login.login_krx()

from lib import config, db  # noqa: E402

CACHE_PATH = str(config.ALERTS / "ticker_cache.json")
CACHE_DB = str(config.CACHE_DB)

def fetch_price_cache(ticker: str, start_date: str, end_date: str):
    try:
        with db.connect() as conn:
            q = """
                SELECT date, open, high, low, close, volume
                FROM ohlcv
                WHERE ticker = ? AND date BETWEEN ? AND ?
                ORDER BY date
            """
            df = pd.read_sql(q, conn, params=(ticker, start_date, end_date))
        if df.empty:
            return None
        df = df.rename(columns={
            "date": "날짜",
            "open": "시가",
            "high": "고가",
            "low": "저가",
            "close": "종가",
            "volume": "거래량",
        })
        df["날짜"] = pd.to_datetime(df["날짜"])
        df = df.set_index("날짜")
        return df
    except Exception:
        return None

def get_relaxed_candidates():
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    
    with open(CACHE_PATH, "r") as f:
        data = json.load(f)
        top_tickers = data.get("top_tickers", [])[:500]

    candidates = []
    
    today_live_df = None
    try:
        today_live_df = stock.get_market_ohlcv_by_ticker(end_date, market="ALL")
    except Exception as e:
        pass

    for ticker in top_tickers:
        df = fetch_price_cache(ticker, start_date, end_date)
        if df is None or len(df) < 150:
            continue
            
        if today_live_df is not None and ticker in today_live_df.index:
            last_dt = df.index[-1]
            if last_dt.strftime("%Y%m%d") != end_date:
                live_row = today_live_df.loc[ticker]
                if pd.notna(live_row["종가"]) and live_row["종가"] > 0:
                    new_idx = pd.to_datetime(end_date)
                    df.loc[new_idx] = {
                        "시가": live_row["시가"],
                        "고가": live_row["고가"],
                        "저가": live_row["저가"],
                        "종가": live_row["종가"],
                        "거래량": live_row["거래량"]
                    }

        close = df["종가"]
        ma50 = close.rolling(window=50).mean()
        ma150 = close.rolling(window=150).mean()
        ma200 = close.rolling(window=200).mean()

        curr_price = close.iloc[-1]
        curr_ma50 = ma50.iloc[-1]
        curr_ma150 = ma150.iloc[-1]
        curr_ma200 = ma200.iloc[-1]
        
        # 완화된 조건: MA150/200 순배열 불문, 가격이 MA50, 150 위에만 있으면 OK
        cond_trend = curr_price > curr_ma50 and curr_price > curr_ma150
        
        # 터틀 조건 완화: 20일 고점 돌파(S1) 또는 55일 고점(S2)
        high_20d = close.rolling(window=20).max().iloc[-1]
        turtle_signal = "S1/S2" if curr_price >= high_20d else "대기"
        cond_turtle = turtle_signal != "대기"
        
        # 거래량 조건 완화: 1.2배 이상 (오전)
        vol = df["거래량"]
        vol20 = vol.rolling(window=20).mean()
        vol_ratio = vol.iloc[-1] / vol20.iloc[-1] if vol20.iloc[-1] else 0
        cond_vol = vol_ratio >= 1.0  # 아침이라 완화
        
        if cond_trend and cond_turtle and cond_vol:
            candidates.append({
                "ticker": ticker,
                "price": int(curr_price),
                "change": round((curr_price - close.iloc[-2]) / close.iloc[-2] * 100, 2),
                "vol_ratio": round(vol_ratio, 2),
                "turtle": turtle_signal,
            })

    if candidates:
        try:
            df_cap = stock.get_market_cap_by_ticker(end_date)
            cap_map = df_cap["시가총액"].to_dict()
            for c in candidates:
                c["market_cap"] = int(cap_map.get(c["ticker"], 0))
                c["name"] = stock.get_market_ticker_name(c["ticker"]) if c["ticker"] in cap_map else c["ticker"]
        except Exception:
            pass

    return candidates

if __name__ == "__main__":
    results = get_relaxed_candidates()
    results = sorted(results, key=lambda x: x.get("change", 0), reverse=True)
    msg = "📊 [03/10 오전] Stage2 결과 (완화형)\n"
    msg += "엄격한 미너비니 추세를 풀고, '단기 수급/이평선 위' 종목 위주로 뽑았습니다.\n\n"
    for r in results[:10]:
        msg += f"• {r.get('name')} ({r.get('ticker')}) {r.get('price')}원 (+{r.get('change')}%) | 거래량비 {r.get('vol_ratio')}\n"
    
    with open(str(config.ALERTS / "stage2_relaxed.txt"), "w") as f:
        f.write(msg)
    print(msg)

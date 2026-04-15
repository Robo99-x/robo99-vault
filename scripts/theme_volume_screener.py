#!/usr/bin/env python3
"""
theme_volume_screener.py — 장마감 특징주 테마별 스크리너

기준: (시총 1조↑ & +5%↑) OR (시총 1조↓ & +7%↑) | 거래량 20일평균 1.5배↑
출력: ~/robo99_hq/alerts/theme_screener.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pandas as pd
import krx_login
krx_login.login_krx()
from pykrx import stock

from lib import config, db  # noqa: E402

BASE = config.BASE
DB_PATH = config.CACHE_DB
THEME_MAP_PATH = config.ALERTS / "cache" / "theme_map.json"
OUTPUT_PATH = config.ALERTS / "theme_screener.json"


def get_screener_list():
    today = datetime.now().strftime("%Y%m%d")

    theme_map = {}
    if THEME_MAP_PATH.exists():
        with open(THEME_MAP_PATH, "r") as f:
            theme_map = json.load(f)

    # 1. 시총 3000억 이상
    try:
        df_cap = stock.get_market_cap_by_ticker(today)
    except Exception as e:
        print(f"시총 데이터 오류: {e}")
        return []
    df_cap = df_cap[df_cap["시가총액"] >= 300_000_000_000]

    # 2. 오늘 OHLCV
    try:
        df_ohlcv = stock.get_market_ohlcv_by_ticker(today, market="ALL")
    except Exception as e:
        print(f"OHLCV 데이터 오류: {e}")
        return []

    df = df_cap.join(df_ohlcv, rsuffix="_ohlcv")

    # 3. 차등 등락률 필터
    cond_small = (df["시가총액"] < 1_000_000_000_000) & (df["등락률"] >= 7.0)
    cond_large = (df["시가총액"] >= 1_000_000_000_000) & (df["등락률"] >= 5.0)
    df = df[cond_small | cond_large]
    if df.empty:
        print("필터 통과 종목 없음")
        return []

    tickers = list(df.index)

    # 4. SQLite에서 히스토리 데이터
    if not DB_PATH.exists():
        print(f"DB 없음: {DB_PATH}")
        return []

    placeholders = ",".join(["?"] * len(tickers))

    q_vol = f"""
        SELECT ticker, AVG(volume) AS avg20
        FROM (
            SELECT ticker, volume,
                   ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY date DESC) as rn
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND date < ?
        )
        WHERE rn <= 20
        GROUP BY ticker
    """
    vol_df = db.query_df(q_vol, params=tickers + [today]).set_index("ticker")

    q_hist = f"""
        SELECT ticker, date, close, high
        FROM ohlcv
        WHERE ticker IN ({placeholders}) AND date <= ?
        ORDER BY ticker, date DESC
    """
    hist_df = db.query_df(q_hist, params=tickers + [today])

    results = []
    for t, row in df.iterrows():
        if t not in vol_df.index:
            continue
        avg20 = vol_df.loc[t]["avg20"]
        if pd.isna(avg20) or avg20 == 0:
            continue

        vol_ratio = row["거래량"] / avg20
        if vol_ratio < 1.5:
            continue

        t_hist = hist_df[hist_df["ticker"] == t]
        rs_proxy = 0.0
        breakout_tag = ""

        if len(t_hist) > 0:
            if len(t_hist) >= 21:
                past_close = t_hist.iloc[20]["close"]
                rs_proxy = ((row["종가"] / past_close) - 1) * 100

            today_close = row["종가"]
            if len(t_hist) >= 56:
                past_55_high = t_hist.iloc[1:56]["high"].max()
                if today_close > past_55_high:
                    breakout_tag = "🚀55일 신고가"
            if not breakout_tag and len(t_hist) >= 21:
                past_20_high = t_hist.iloc[1:21]["high"].max()
                if today_close > past_20_high:
                    breakout_tag = "🚀20일 신고가"

        name = stock.get_market_ticker_name(t)
        themes = theme_map.get(t, ["미분류"])
        theme_str = ", ".join(themes[:2])
        market_cap_trillion = row["시가총액"] / 1_000_000_000_000

        results.append({
            "ticker": t,
            "name": name,
            "close": int(row["종가"]),
            "change": round(float(row["등락률"]), 2),
            "vol_ratio": round(vol_ratio, 1),
            "theme": theme_str,
            "rs_proxy": round(rs_proxy, 2),
            "trade_value_억": int(row["거래대금"]) // 100_000_000,
            "market_cap_조": round(market_cap_trillion, 1),
            "tag": breakout_tag,
        })

    results = sorted(results, key=lambda x: x["rs_proxy"], reverse=True)[:40]
    return results


if __name__ == "__main__":
    print("특징주 스크리닝 시작...")
    res = get_screener_list()
    print(f"필터 통과: {len(res)}종목")

    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "stocks": res,
        "criteria": "시총1조↑ +5%↑ / 시총1조↓ +7%↑ | 거래량 20일평균 1.5배↑",
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {OUTPUT_PATH}")

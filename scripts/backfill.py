import sys
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import krx_login
krx_login.login_krx()
from pykrx import stock
import sqlite3
import pandas as pd

from lib import config  # noqa: E402

DB_PATH = str(config.CACHE_DB)
conn = sqlite3.connect(DB_PATH)

dates = ["20260302", "20260303", "20260304", "20260305", "20260306"]
for d in dates:
    print(f"Fetching {d}...")
    df = stock.get_market_ohlcv_by_ticker(d, market="ALL")
    if df is None or df.empty:
        print(f"No data for {d}")
        continue
    df = df.reset_index().rename(columns={
        "티커": "ticker",
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
    })
    df["date"] = d
    rows = df[["date", "ticker", "open", "high", "low", "close", "volume"]].values.tolist()
    conn.executemany(
        "INSERT OR REPLACE INTO ohlcv(date,ticker,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    print(f"Cached {len(rows)} for {d}")

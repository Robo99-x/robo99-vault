#!/usr/bin/env python3
import os
import sys
import sqlite3
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import FinanceDataReader as fdr

from lib import config  # noqa: E402

DB_PATH = str(config.CACHE_DB)
TICKER_CACHE_PATH = str(config.ALERTS / "ticker_cache.json")
BACKFILL_DAYS = 400
CHUNK_TICKERS = 100
RETRY_MAX = 5
REQUEST_SLEEP_SEC = 0.2
BASE_BACKOFF_SEC = 1


def ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ohlcv (
            date TEXT,
            ticker TEXT,
            open INTEGER,
            high INTEGER,
            low INTEGER,
            close INTEGER,
            volume INTEGER,
            PRIMARY KEY (date, ticker)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_date ON ohlcv(ticker, date)")
    conn.commit()
    return conn


def fetch_with_retry(ticker: str, start: str, end: str):
    last_err = None
    for attempt in range(1, RETRY_MAX + 1):
        try:
            return fdr.DataReader(ticker, start, end)
        except Exception as e:
            last_err = e
            backoff = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
            print(f"retry {ticker} attempt={attempt}/{RETRY_MAX} backoff={backoff}s error={e}")
            time.sleep(backoff)
    raise last_err


def main():
    conn = ensure_db()
    dt = datetime.now()
    start = (dt - timedelta(days=BACKFILL_DAYS - 1)).strftime("%Y-%m-%d")
    end = dt.strftime("%Y-%m-%d")

    try:
        listing = fdr.StockListing("KRX")
        tickers = listing["Code"].tolist()
    except Exception as e:
        print(f"ticker_listing_failed: {e}")
        if os.path.exists(TICKER_CACHE_PATH):
            with open(TICKER_CACHE_PATH, "r", encoding="utf-8") as f:
                tickers = json.load(f).get("top_tickers", [])
            print(f"using_cached_tickers count={len(tickers)}")
        else:
            raise
    total = len(tickers)

    for i, ticker in enumerate(tickers, start=1):
        try:
            df = fetch_with_retry(ticker, start, end)
            time.sleep(REQUEST_SLEEP_SEC)
            if df is None or len(df) == 0:
                print(f"[{i}/{total}] empty {ticker}")
                continue
            df = df.reset_index().rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            required = {"date", "open", "high", "low", "close", "volume"}
            if not required.issubset(df.columns):
                print(f"[{i}/{total}] schema_mismatch {ticker} cols={list(df.columns)}")
                continue
            df["ticker"] = ticker
            df["date"] = df["date"].dt.strftime("%Y%m%d")
            df = df.fillna(0)
            rows = df[["date","ticker","open","high","low","close","volume"]].values.tolist()
            conn.executemany(
                "INSERT OR REPLACE INTO ohlcv(date,ticker,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
                rows,
            )
            print(f"[{i}/{total}] backfilled {ticker} rows={len(rows)}")
        except Exception as e:
            print(f"[{i}/{total}] skip {ticker}: {e}")
            continue
        if i % CHUNK_TICKERS == 0:
            conn.commit()
            print(f"chunk_commit {i}/{total}")
    conn.commit()
    print("done")


if __name__ == "__main__":
    main()

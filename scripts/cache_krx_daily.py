#!/usr/bin/env python3
import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from pykrx import stock
import FinanceDataReader as fdr
import krx_login
krx_login.login_krx()
import pandas as pd

from lib import config, db  # noqa: E402

DB_PATH = str(config.CACHE_DB)
LOG_PATH = str(config.ALERTS / "krx_cache_daily.err")
TICKER_CACHE = str(config.ALERTS / "ticker_cache.json")
MAX_FDR_TICKERS = 80


def _log_err(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def ensure_db():
    """DB 테이블 생성 보장. connect_write 커넥션 반환."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    # connect_write 로 열어서 DDL + commit
    import sqlite3 as _sq
    conn = _sq.connect(DB_PATH)
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


def _fdr_latest_ohlcv():
    if not os.path.exists(TICKER_CACHE):
        _log_err("FDR fallback failed: ticker_cache.json not found")
        return None
    with open(TICKER_CACHE, "r") as f:
        tickers = json.load(f).get("top_tickers", [])
    if not tickers:
        _log_err("FDR fallback failed: empty ticker list")
        return None

    tickers = tickers[:MAX_FDR_TICKERS]
    rows = []
    start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    for t in tickers:
        try:
            df = fdr.DataReader(t, start)
            if df is None or df.empty:
                continue
            last = df.iloc[-1]
            date = df.index[-1].strftime("%Y%m%d")
            rows.append([date, t, last["Open"], last["High"], last["Low"], last["Close"], last["Volume"]])
        except Exception:
            _log_err(f"FDR error for {t}: {traceback.format_exc().strip()}")
            continue

    if not rows:
        _log_err("FDR fallback failed: no rows fetched")
        return None

    return pd.DataFrame(rows, columns=["date", "ticker", "open", "high", "low", "close", "volume"])


def nearest_bday(max_lookback=7):
    dt = datetime.now()
    for i in range(max_lookback):
        d = (dt - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = stock.get_market_ohlcv_by_ticker(d, market="ALL")
            if df is not None and len(df) > 0 and set(["시가", "고가", "저가", "종가"]).issubset(df.columns):
                return d, df, "pykrx"
            _log_err(f"pykrx empty/invalid dataframe for {d}: cols={list(df.columns)}")
        except Exception:
            _log_err(f"pykrx error for {d}: {traceback.format_exc().strip()}")
            continue

    _log_err("pykrx failed for recent days; attempting FDR fallback")
    df = _fdr_latest_ohlcv()
    if df is not None and len(df) > 0:
        return None, df, "fdr"
    return None, None, None


def _get_missing_dates(conn, max_lookback: int = 10) -> list[str]:
    """DB max_date 이후 오늘까지 누락된 거래일 목록 반환 (pykrx 확인 기반)."""
    row = conn.execute("SELECT MAX(date) FROM ohlcv").fetchone()
    db_max = row[0] if row and row[0] else "20000101"

    today = datetime.now()
    missing = []
    for i in range(max_lookback, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        if d <= db_max:
            continue
        if d > today.strftime("%Y%m%d"):
            continue
        # 주말 제외
        dt = datetime.strptime(d, "%Y%m%d")
        if dt.weekday() >= 5:
            continue
        missing.append(d)
    return missing


def _cache_date(conn, date: str) -> bool:
    """특정 날짜의 KRX 데이터를 DB에 삽입. 성공 시 True."""
    try:
        df = stock.get_market_ohlcv_by_ticker(date, market="ALL")
        if df is None or df.empty:
            return False
        if not set(["시가", "고가", "저가", "종가"]).issubset(df.columns):
            return False
        df = df.reset_index().rename(columns={
            "티커": "ticker",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
        })
        df["date"] = date
        rows = df[["date", "ticker", "open", "high", "low", "close", "volume"]].values.tolist()
        conn.executemany(
            "INSERT OR REPLACE INTO ohlcv(date,ticker,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        print(f"cached {len(rows)} rows for {date} (source=pykrx)")
        return True
    except Exception:
        _log_err(f"_cache_date failed for {date}: {traceback.format_exc().strip()}")
        return False


def main():
    conn = ensure_db()

    # catch-up: DB max_date 이후 누락된 거래일 모두 보충
    missing = _get_missing_dates(conn)
    if missing:
        for d in missing:
            ok = _cache_date(conn, d)
            if not ok:
                print(f"ERROR: cannot fetch KRX daily data for {d}")
        return

    # 누락일 없으면 오늘(또는 최근 거래일) 캐시
    date, df, source = nearest_bday()
    if df is None:
        print("ERROR: cannot fetch KRX daily data")
        return

    if source == "pykrx":
        df = df.reset_index().rename(columns={
            "티커": "ticker",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
        })
        df["date"] = date
    elif source == "fdr":
        # already normalized
        pass
    else:
        print("ERROR: unknown data source")
        return

    rows = df[["date", "ticker", "open", "high", "low", "close", "volume"]].values.tolist()
    conn.executemany(
        "INSERT OR REPLACE INTO ohlcv(date,ticker,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    used_date = date if date else df["date"].max()
    print(f"cached {len(rows)} rows for {used_date} (source={source})")


if __name__ == "__main__":
    main()

"""
lib/db.py — SQLite 커넥션 관리

모든 스크립트는 이 모듈을 통해서만 DB에 접근한다.
직접 sqlite3.connect() 호출 금지.

사용법:
    from lib import db

    # 방법 1: context manager
    with db.connect() as conn:
        df = pd.read_sql("SELECT ...", conn)

    # 방법 2: 원라이너
    df = db.query_df("SELECT * FROM ohlcv WHERE ticker = ?", params=("005930",))

    # 방법 3: 쓰기 (commit 자동)
    with db.connect_write() as conn:
        conn.execute("INSERT INTO ohlcv VALUES (?, ?, ...)", params)

    # 방법 4: 캐시 신선도 확인
    if db.cache_is_fresh("20260413"):
        df = db.query_df(...)
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from lib.config import CACHE_DB


@contextmanager
def connect(db_path: str | Path = CACHE_DB):
    """SQLite connection context manager. 자동 close 보장.

    Usage:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(...)
    """
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


def query_df(
    sql: str,
    params: Sequence[Any] = (),
    db_path: str | Path = CACHE_DB,
) -> pd.DataFrame:
    """SQL → DataFrame. 커넥션 자동 관리.

    Usage:
        df = db.query_df(
            "SELECT * FROM ohlcv WHERE ticker = ? AND date >= ?",
            params=("005930", "20260101"),
        )
    """
    with connect(db_path) as conn:
        return pd.read_sql(sql, conn, params=params)


def query_one(
    sql: str,
    params: Sequence[Any] = (),
    db_path: str | Path = CACHE_DB,
) -> Any:
    """단일 값 쿼리. fetchone()[0] 반환, 결과 없으면 None."""
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


@contextmanager
def connect_write(db_path: str | Path = CACHE_DB):
    """쓰기용 SQLite connection. commit 자동 + close 보장.

    성공 시 commit, 예외 시 rollback.

    Usage:
        with db.connect_write() as conn:
            conn.execute("INSERT INTO ohlcv VALUES (...)")
            # commit은 블록 종료 시 자동
    """
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_write(
    sql: str,
    params: Sequence[Any] = (),
    db_path: str | Path = CACHE_DB,
) -> int:
    """단일 INSERT/UPDATE/DELETE. 영향 받은 행 수 반환."""
    with connect_write(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.rowcount


def executemany_write(
    sql: str,
    params_list: Sequence[Sequence[Any]],
    db_path: str | Path = CACHE_DB,
) -> int:
    """배치 INSERT/UPDATE. 영향 받은 행 수 반환."""
    with connect_write(db_path) as conn:
        cur = conn.cursor()
        cur.executemany(sql, params_list)
        return cur.rowcount


def cache_is_fresh(end_date: str) -> bool:
    """KRX 캐시가 end_date 기준으로 최신인지 확인.

    Args:
        end_date: "YYYYMMDD" 형식의 기준일자
    """
    db_path = Path(CACHE_DB)
    if not db_path.exists():
        return False
    try:
        max_date = query_one("SELECT MAX(date) FROM ohlcv")
        if not max_date:
            return False
        dt = datetime.strptime(end_date, "%Y%m%d")
        if dt.weekday() < 5:  # 평일
            prev = dt - timedelta(days=1)
            while prev.weekday() >= 5:
                prev -= timedelta(days=1)
            return max_date >= prev.strftime("%Y%m%d")
        return True  # 주말엔 캐시 허용
    except Exception:
        return False

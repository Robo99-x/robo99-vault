import sys
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import krx_login
krx_login.login_krx()
from pykrx import stock
import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta

from lib import config, db  # noqa: E402

DB_PATH = str(config.CACHE_DB)


def get_screener_list():
    today = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=40)).strftime('%Y%m%d')

    # 1) market cap filter
    df_cap = stock.get_market_cap_by_ticker(today)
    df_cap = df_cap[df_cap['시가총액'] >= 300_000_000_000]

    # 2) today ohlcv
    df_ohlcv = stock.get_market_ohlcv_by_ticker(today, market='ALL')

    # merge and prefilter +5%
    df = df_cap.join(df_ohlcv, rsuffix='_ohlcv')
    df = df[df['등락률'] >= 5.0]
    if df.empty:
        return []

    tickers = list(df.index)

    # 3) sector map
    fdr_krx = fdr.StockListing('KRX')
    fdr_krx = fdr_krx.set_index('Code') if 'Code' in fdr_krx.columns else fdr_krx.set_index('Symbol')

    # 4) avg volume 20d (exclude today) in one query
    with db.connect() as conn:
        placeholders = ','.join(['?'] * len(tickers))
        q = f"""
            SELECT ticker, AVG(volume) AS avg20
            FROM ohlcv
            WHERE ticker IN ({placeholders})
              AND date BETWEEN ? AND ?
              AND date < ?
            GROUP BY ticker
        """
        params = tickers + [start_date, today, today]
        vol_df = pd.read_sql(q, conn, params=params)

    vol_df = vol_df.set_index('ticker')

    results = []
    for t, row in df.iterrows():
        if t not in vol_df.index:
            continue
        avg20 = vol_df.loc[t]['avg20']
        if avg20 is None or avg20 == 0:
            continue
        vol_ratio = row['거래량'] / avg20
        if vol_ratio < 1.5:
            continue
        name = stock.get_market_ticker_name(t)
        sector = fdr_krx.loc[t, 'Sector'] if t in fdr_krx.index and 'Sector' in fdr_krx.columns else '미분류'
        if pd.isna(sector):
            sector = '미분류'

        # RS proxy: 20일 수익률 (오늘 종가 / 20영업일 전 종가)
        rs_proxy = None
        # fetch 21 trading days for RS from DB quickly
        with db.connect() as conn:
            rs_q = "SELECT close FROM ohlcv WHERE ticker=? AND date <= ? ORDER BY date DESC LIMIT 21"
            rs_rows = pd.read_sql(rs_q, conn, params=(t, today))
        if len(rs_rows) >= 21:
            rs_proxy = (row['종가'] / rs_rows['close'].iloc[-1] - 1) * 100
        else:
            rs_proxy = 0.0

        results.append({
            'ticker': t,
            'name': name,
            'close': int(row['종가']),
            'change': float(row['등락률']),
            'vol_ratio': round(vol_ratio, 2),
            'sector': sector,
            'rs_proxy': round(rs_proxy, 2),
            'trade_value': int(row['거래대금'])
        })

    # sort by RS proxy
    results = sorted(results, key=lambda x: x['rs_proxy'], reverse=True)[:40]
    return results


if __name__ == '__main__':
    res = get_screener_list()
    by_sector = {}
    for r in res:
        by_sector.setdefault(r['sector'], []).append(r)

    print("=== 시총 3,000억 이상 | 당일 +5%↑ | 거래량 20일 평균 대비 1.5배↑ | RS 상위 40 ===")
    for sector, lst in by_sector.items():
        print(f"\n[{sector}]")
        for r in lst:
            print(f"- {r['name']} ({r['ticker']}): {r['close']}원 (+{r['change']}%) | 거래량 {r['vol_ratio']}배 | RS(20D) +{r['rs_proxy']}% | 거래대금 {r['trade_value']//100000000}억")

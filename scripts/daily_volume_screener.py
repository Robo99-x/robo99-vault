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
import sqlite3
import os

from lib import config  # noqa: E402

DB_PATH = str(config.CACHE_DB)

def get_screener_list():
    date = datetime.now().strftime('%Y%m%d')
    # 1. Fetch all tickers and market cap
    try:
        df_cap = stock.get_market_cap_by_ticker(date)
    except:
        return []
    
    # Filter cap >= 3000억
    df_cap = df_cap[df_cap['시가총액'] >= 300_000_000_000]
    
    # 2. Fetch OHLCV
    try:
        df_ohlcv = stock.get_market_ohlcv_by_ticker(date, market="ALL")
    except:
        return []
    
    # Merge
    df = df_cap.join(df_ohlcv, rsuffix='_ohlcv')
    
    # Filter by 5% increase
    df = df[df['등락률'] >= 5.0]
    
    if df.empty:
        return []
    
    # Load FDR for Sector info
    fdr_krx = fdr.StockListing("KRX")
    fdr_krx = fdr_krx.set_index('Code') if 'Code' in fdr_krx.columns else fdr_krx.set_index('Symbol')
    
    results = []
    
    conn = sqlite3.connect(DB_PATH)
    start_date = (datetime.now() - timedelta(days=40)).strftime('%Y%m%d')
    
    for ticker, row in df.iterrows():
        try:
            # Query from sqlite to make it super fast
            q = """
                SELECT date, close, volume 
                FROM ohlcv 
                WHERE ticker=? AND date BETWEEN ? AND ? 
                ORDER BY date
            """
            hist = pd.read_sql(q, conn, params=(ticker, start_date, date))
            
            if len(hist) < 20:
                continue
                
            # If today is not in DB, add row['거래량']
            if hist.iloc[-1]['date'] != date:
                # Add today's row manually
                hist = pd.concat([hist, pd.DataFrame([{'date': date, 'close': row['종가'], 'volume': row['거래량']}])], ignore_index=True)
            
            vol_20d_avg = hist['volume'][:-1].tail(20).mean() # Exclude today
            vol_today = row['거래량']
            
            if vol_20d_avg == 0:
                continue
                
            vol_ratio = vol_today / vol_20d_avg
            
            # Condition: Volume is at least 1.5x the 20-day average
            if vol_ratio >= 1.5:
                name = stock.get_market_ticker_name(ticker)
                sector = fdr_krx.loc[ticker, 'Sector'] if ticker in fdr_krx.index and 'Sector' in fdr_krx.columns else "미분류"
                if pd.isna(sector): sector = "미분류"
                
                # Simple RS Proxy: (Today Close / 20d Close) - Relative Strength (1 Month)
                rs_proxy = row['종가'] / hist['close'].iloc[-21] if len(hist) > 20 else 1.0
                
                results.append({
                    'ticker': ticker,
                    'name': name,
                    'close': int(row['종가']),
                    'change': float(row['등락률']),
                    'vol_ratio': round(vol_ratio, 2),
                    'sector': sector,
                    'rs_proxy': round((rs_proxy - 1) * 100, 2), # convert to percentage return
                    'trade_value': int(row['거래대금'])
                })
        except Exception as e:
            continue
            
    conn.close()

    # Sort by RS Proxy descending
    results = sorted(results, key=lambda x: x['rs_proxy'], reverse=True)[:40]
    return results

if __name__ == "__main__":
    res = get_screener_list()
    # Group by Sector for output
    by_sector = {}
    for r in res:
        by_sector.setdefault(r['sector'], []).append(r)
        
    print("=== 시총 3천억 이상 & 당일 5% 이상 상승 & 거래량 20일 평균대비 1.5배 이상 (RS 기준 상위 40선) ===")
    for sector, lst in by_sector.items():
        print(f"\n[{sector}]")
        for r in lst:
            print(f"- {r['name']} ({r['ticker']}): {r['close']}원 (+{r['change']}%) | 볼륨 {r['vol_ratio']}배 | 1M RS: +{r['rs_proxy']}% | 거래대금: {r['trade_value']//100000000}억")

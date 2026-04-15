import krx_login
krx_login.login_krx()
from pykrx import stock
from datetime import datetime
import pandas as pd

market_date = datetime.now().strftime("%Y%m%d")

try:
    df_kospi = stock.get_market_ohlcv_by_ticker(market_date, market="KOSPI")
    df_kosdaq = stock.get_market_ohlcv_by_ticker(market_date, market="KOSDAQ")
    
    kospi_up = len(df_kospi[df_kospi['등락률'] > 0])
    kospi_down = len(df_kospi[df_kospi['등락률'] < 0])
    kosdaq_up = len(df_kosdaq[df_kosdaq['등락률'] > 0])
    kosdaq_down = len(df_kosdaq[df_kosdaq['등락률'] < 0])
    
    # 코스피/코스닥 지수는 직접 계산이 어려우므로 상위 종목 흐름으로 대체 요약
    print("=== 국내 증시 마감 요약 ===")
    print(f"코스피: 상승 {kospi_up}종목 / 하락 {kospi_down}종목")
    print(f"코스닥: 상승 {kosdaq_up}종목 / 하락 {kosdaq_down}종목")
    
    all_df = pd.concat([df_kospi, df_kosdaq])
    top_gainers = all_df.sort_values(by='등락률', ascending=False).head(10)
    print("\n[상승률 TOP 10]")
    for ticker, row in top_gainers.iterrows():
        name = stock.get_market_ticker_name(ticker)
        print(f"{name}({ticker}): {row['종가']}원 ({row['등락률']}%) - 거래대금: {row['거래대금']//100000000}억")
        
    top_value = all_df.sort_values(by='거래대금', ascending=False).head(5)
    print("\n[거래대금 TOP 5]")
    for ticker, row in top_value.iterrows():
        name = stock.get_market_ticker_name(ticker)
        print(f"{name}({ticker}): {row['종가']}원 ({row['등락률']}%) - 거래대금: {row['거래대금']//100000000}억")
        
except Exception as e:
    print(f"Error fetching data: {e}")

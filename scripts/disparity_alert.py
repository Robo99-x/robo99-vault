"""
국내 지수 이격도 텔레그램 텍스트 알림
매일 07:30 KST 실행
"""
import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta
import zoneinfo

KST = zoneinfo.ZoneInfo('Asia/Seoul')
today = datetime.now(KST).strftime('%Y-%m-%d')

start_date = (datetime.now(KST) - timedelta(days=400)).strftime('%Y-%m-%d')

def get_index(ticker):
    df = yf.download(ticker, start=start_date, progress=False)
    df = df[['Close']].rename(columns={'Close': 'close'})
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.dropna()

WINDOWS = [5, 20, 60]

def add_disparity(df):
    for w in WINDOWS:
        ma = df['close'].rolling(w).mean()
        df[f'd{w}'] = (df['close'] / ma * 100).round(2)
    return df

def signal(v):
    if v > 105: return '🔴과열'
    if v > 103: return '🟠주의'
    if v < 95:  return '🟢침체'
    if v < 97:  return '🔵주의'
    return '⚪중립'

def fmt_index(df, name):
    r = df.iloc[-1]
    close = float(r['close'].iloc[0]) if hasattr(r['close'], 'iloc') else float(r['close'])
    lines = [f"[ {name} ]  {close:,.2f}"]
    for w in WINDOWS:
        raw = r[f'd{w}']
        v = float(raw.iloc[0]) if hasattr(raw, 'iloc') else float(raw)
        lines.append(f"  {w:2d}일  {v:6.2f}%  {signal(v)}")
    return '\n'.join(lines)

kospi  = add_disparity(get_index('^KS11'))
kosdaq = add_disparity(get_index('^KQ11'))

msg = f"""📊 국내 지수 이격도  {today}

{fmt_index(kospi,  'KOSPI')}

{fmt_index(kosdaq, 'KOSDAQ')}

─────────────────
기준: 103%↑ 과열 / 97%↓ 침체
"""

# 텔레그램 Bot API 직접 호출
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8710110844:AAFXPfxbTUaT21W0wQvQMSxeW_pUIbWInL0')
CHAT_ID = '1883449676'

if TOKEN:
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    resp = requests.post(url, json={'chat_id': CHAT_ID, 'text': msg})
    if resp.ok:
        print("전송 완료")
    else:
        print(f"전송 실패: {resp.text}")
else:
    # 토큰 없으면 stdout 출력 (schedule agent가 MCP로 전송)
    print("TELEGRAM_OUTPUT:" + msg)

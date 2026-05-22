"""
국내 지수 이격도 차트 생성
KOSPI / KOSDAQ 기준 5일, 20일, 60일 이격도
"""
import sys
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

start_date = (datetime.today() - timedelta(days=400)).strftime('%Y-%m-%d')
six_months_ago = (datetime.today() - timedelta(days=180)).strftime('%Y-%m-%d')

print("데이터 수집 중...")

def get_index(ticker):
    df = yf.download(ticker, start=start_date, progress=False)
    df = df[['Close']].rename(columns={'Close': 'close'})
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None)
    return df.dropna()

kospi = get_index('^KS11')
kosdaq = get_index('^KQ11')

WINDOWS = [5, 20, 60]

def add_disparity(df):
    for w in WINDOWS:
        ma = df['close'].rolling(w).mean()
        df[f'disp_{w}'] = (df['close'] / ma * 100).round(2)
    return df

kospi = add_disparity(kospi)
kosdaq = add_disparity(kosdaq)

kp = kospi[kospi.index >= six_months_ago]
kd = kosdaq[kosdaq.index >= six_months_ago]

# ── 그래프 ──────────────────────────────────────────────────────────────────
BG = '#0d1117'
PANEL = '#161b22'
GRID = '#21262d'
TEXT = '#c9d1d9'
MUTED = '#8b949e'
RED = '#f85149'
C = {5: '#58a6ff', 20: '#f0883e', 60: '#3fb950'}

fig = plt.figure(figsize=(14, 20), facecolor=BG)
fig.suptitle(f'국내 지수 이격도  ({datetime.today().strftime("%Y-%m-%d")} 기준)',
             color=TEXT, fontsize=15, y=0.99)

gs = fig.add_gridspec(4, 1, hspace=0.45)
axes = [fig.add_subplot(gs[i]) for i in range(4)]

def style_ax(ax, title):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color=TEXT, fontsize=12, loc='left', pad=6)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.yaxis.label.set_color(MUTED)
    ax.grid(True, color=GRID, linewidth=0.5, linestyle='--')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    fig.autofmt_xdate(rotation=0, ha='center')

# KOSPI 가격
style_ax(axes[0], 'KOSPI 지수')
axes[0].plot(kp.index, kp['close'], color=TEXT, linewidth=1.2)
axes[0].set_ylabel('포인트', color=MUTED, fontsize=9)

# KOSPI 이격도
style_ax(axes[1], 'KOSPI 이격도')
for w in WINDOWS:
    axes[1].plot(kp.index, kp[f'disp_{w}'], color=C[w], linewidth=1.2, label=f'{w}일')
axes[1].axhline(100, color=RED, linewidth=0.9, linestyle='--', alpha=0.8, label='기준(100)')
axes[1].axhline(103, color='#f0883e', linewidth=0.5, linestyle=':', alpha=0.6)
axes[1].axhline(97,  color='#3fb950', linewidth=0.5, linestyle=':', alpha=0.6)
axes[1].set_ylabel('이격도 (%)', color=MUTED, fontsize=9)
axes[1].legend(loc='upper left', facecolor=PANEL, edgecolor=GRID,
               labelcolor=TEXT, fontsize=8, framealpha=0.8)

# KOSDAQ 가격
style_ax(axes[2], 'KOSDAQ 지수')
axes[2].plot(kd.index, kd['close'], color=TEXT, linewidth=1.2)
axes[2].set_ylabel('포인트', color=MUTED, fontsize=9)

# KOSDAQ 이격도
style_ax(axes[3], 'KOSDAQ 이격도')
for w in WINDOWS:
    axes[3].plot(kd.index, kd[f'disp_{w}'], color=C[w], linewidth=1.2, label=f'{w}일')
axes[3].axhline(100, color=RED, linewidth=0.9, linestyle='--', alpha=0.8, label='기준(100)')
axes[3].axhline(103, color='#f0883e', linewidth=0.5, linestyle=':', alpha=0.6)
axes[3].axhline(97,  color='#3fb950', linewidth=0.5, linestyle=':', alpha=0.6)
axes[3].set_ylabel('이격도 (%)', color=MUTED, fontsize=9)
axes[3].legend(loc='upper left', facecolor=PANEL, edgecolor=GRID,
               labelcolor=TEXT, fontsize=8, framealpha=0.8)

out = '/tmp/disparity_chart.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
plt.close()

# ── 현재값 출력 ──────────────────────────────────────────────────────────────
def fmt(df, name):
    r = df.iloc[-1]
    date_str = df.index[-1].strftime('%Y-%m-%d')
    close = float(r['close'])
    lines = [f"[{name}] {date_str}  현재가: {close:,.2f}"]
    for w in WINDOWS:
        v = float(r[f'disp_{w}'])
        signal = '▲과열' if v > 103 else ('▼침체' if v < 97 else '◆중립')
        lines.append(f"  {w:2d}일 MA 이격도: {v:.2f}%  {signal}")
    return '\n'.join(lines)

print(fmt(kospi, 'KOSPI'))
print()
print(fmt(kosdaq, 'KOSDAQ'))
print(f"\n차트 저장: {out}")

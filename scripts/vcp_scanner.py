import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
import json
from pathlib import Path
from scipy.signal import find_peaks

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import krx_login

# KRX 로그인 패치 적용
krx_login.login_krx()

from pykrx import stock

from lib import config, db, telegram  # noqa: E402

CACHE_DB = str(config.CACHE_DB)
CACHE_PATH = str(config.ALERTS / "ticker_cache.json")

def get_volume_multiplier():
    """현재 시간에 비례하여 오늘 예상되는 총 거래량 할증 계수(Multiplier)를 반환합니다."""
    now = datetime.now()
    if now.hour < 9 or (now.hour >= 15 and now.minute >= 30):
        return 1.0 # 장 시작 전이거나 마감 이후면 그대로
        
    elapsed_minutes = (now.hour - 9) * 60 + now.minute
    if elapsed_minutes <= 0: return 1.0
    
    # 한국장(6.5시간, 390분) U자형 거래량 고려 할증
    if elapsed_minutes <= 60:
        return 3.3
    elif elapsed_minutes <= 120:
        return 2.0
    elif elapsed_minutes <= 240:
        return 1.5
    elif elapsed_minutes <= 300:
        return 1.2
    else:
        return 1.05

def fetch_data(ticker, start_date, end_date):
    try:
        df = db.query_df(
            "SELECT date, open, high, low, close, volume FROM ohlcv WHERE ticker = ? AND date >= ? ORDER BY date",
            params=(ticker, start_date),
        )
        if df.empty: return None
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        # 거래정지나 휴장일로 인해 가격이 0으로 찍힌 결측치 행 제거 (VCP 낙폭 100% 오류 방지)
        df = df[(df['close'] > 0) & (df['high'] > 0) & (df['low'] > 0)]
        
        return df
    except Exception as e:
        return None

def detect_vcp(df, multiplier):
    """
    미너비니 VCP 알고리즘 적용
    1. Stage 2 (장기 추세)
    2. 수축 배열 (Contractions) - scipy의 find_peaks 활용
    3. 거래량 고갈 & 돌파 (Volume Multiplier 적용)
    """
    if len(df) < 120:
        return False, {}
    
    close = df['close']
    vol = df['volume']
    highs = df['high'].values
    lows = df['low'].values
    
    curr_price = close.iloc[-1]
    
    # 1. 50일선 필터 (Stage2 최소 조건: 우상향)
    ma50 = close.rolling(50).mean()
    if curr_price < ma50.iloc[-1]:
        return False, {}
        
    # 2. 국소 고점(Peak) 추출 (최소 15영업일 간격)
    # prominence(돌출도)를 주가 평균의 5% 이상으로 설정하여 찌그러진 노이즈 필터링
    peaks, _ = find_peaks(highs, distance=15, prominence=highs.mean() * 0.05)
    
    if len(peaks) < 2:
        return False, {}
        
    # 파동 깊이(Depth) 계산
    depths = []
    for i in range(len(peaks)):
        peak_idx = peaks[i]
        next_peak_idx = peaks[i+1] if i+1 < len(peaks) else len(highs) - 1
        
        if peak_idx >= next_peak_idx:
            continue
            
        segment_low = lows[peak_idx:next_peak_idx].min()
        peak_price = highs[peak_idx]
        depth = (peak_price - segment_low) / peak_price
        depths.append(depth)
        
    if len(depths) < 2:
        return False, {}
        
    # VCP 조건: 가장 최근 파동의 깊이가 그 이전 파동보다 작아야 함 (수축)
    recent_depths = depths[-3:] # 최근 최대 3번의 파동
    if len(recent_depths) >= 2:
        if recent_depths[-1] > recent_depths[-2] * 1.1: 
            # 10% 이상 낙폭이 커졌다면 수축(Contraction) 실패
            return False, {}
            
    # 피벗(Pivot) 가격: 마지막 고점
    pivot_price = highs[peaks[-1]]
    
    # 3. 거래량 돌파 판별 (시간대비 할증 적용)
    # 만약 현재가 오전이면, multiplier를 곱해 오늘의 '예상 총 거래량'을 구함
    projected_vol = vol.iloc[-1] * multiplier
    vol_50_avg = vol.rolling(50).mean().iloc[-2] if len(vol) > 1 else 1
    
    if vol_50_avg == 0:
        return False, {}
        
    vol_ratio = projected_vol / vol_50_avg
    
    # 트리거 조건: 
    # - 주가가 피벗 포인트에 근접했거나 돌파 (피벗의 95% 이상)
    # - 시간 할증 반영 거래량이 50일 평균 대비 1.5배 이상 터짐
    if curr_price >= pivot_price * 0.95 and vol_ratio >= 1.5:
        return True, {
            "pivot": int(pivot_price),
            "projected_vol_ratio": round(vol_ratio, 1),
            "contractions": len(recent_depths),
            "last_depth": round(recent_depths[-1] * 100, 1),
            "vol_multiplier_used": round(multiplier, 2)
        }
        
    return False, {}

def main():
    multiplier = get_volume_multiplier()
    
    output_lines = []
    output_lines.append(f"====================================")
    output_lines.append(f"🚀 VCP Scanner (Volatility Contraction)")
    output_lines.append(f"🕒 Run Time: {datetime.now().strftime('%H:%M')}")
    output_lines.append(f"📊 Volume Multiplier: {multiplier:.2f}x (시간할증 계수)")
    output_lines.append(f"====================================")
    
    start_date = (datetime.now() - timedelta(days=250)).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")
    
    # 시총 상위 500개 유니버스 불러오기
    tickers = []
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            data = json.load(f)
            tickers = data.get("top_tickers", [])[:500]
            
    if not tickers:
        output_lines.append("유니버스 캐시가 없습니다. 스캐너를 종료합니다.")
        print("\n".join(output_lines))
        return

    # 오늘 라이브 데이터 가져오기 (오전장 실시간 등락 반영을 위함)
    today_live_df = None
    try:
        today_live_df = stock.get_market_ohlcv_by_ticker(end_date, market="ALL")
    except Exception as e:
        pass

    results = []
    for t in tickers:
        df = fetch_data(t, start_date, end_date)
        if df is not None and not df.empty:
            # 실시간 오늘 데이터가 DB에 없다면 임시로 Append
            if today_live_df is not None and t in today_live_df.index:
                last_dt = df.index[-1]
                if last_dt.strftime("%Y%m%d") != end_date:
                    live_row = today_live_df.loc[t]
                    if pd.notna(live_row["종가"]) and live_row["종가"] > 0:
                        new_idx = pd.to_datetime(end_date)
                        df.loc[new_idx] = {
                            "open": live_row["시가"],
                            "high": live_row["고가"],
                            "low": live_row["저가"],
                            "close": live_row["종가"],
                            "volume": live_row["거래량"]
                        }

            is_vcp, info = detect_vcp(df, multiplier)
            if is_vcp:
                try:
                    name = stock.get_market_ticker_name(t)
                except:
                    name = t
                info['ticker'] = t
                info['name'] = name
                info['price'] = int(df['close'].iloc[-1])
                change = 0
                prev_close = df['close'].iloc[-2]
                if prev_close > 0:
                    change = (info['price'] - prev_close) / prev_close * 100
                info['change'] = round(change, 2)
                results.append(info)
                
    # 상승률 순 정렬
    results = sorted(results, key=lambda x: x['change'], reverse=True)
    
    output_lines.append(f"\n✅ VCP 돌파 임박/진행 종목: {len(results)}개 발견\n")
    for r in results[:15]:
        change_sign = "+" if r['change'] > 0 else ""
        output_lines.append(f"🔥 [{r['ticker']}] **{r['name']}**: {r['price']:,}원 ({change_sign}{r['change']:.2f}%)")
        output_lines.append(f"  └ 🎯 피벗: {r['pivot']:,}원 | 📊 예상거래량: {r['projected_vol_ratio']}배 | 📉 VCP수축: {r['contractions']}T (최근낙폭 {r['last_depth']:.1f}%)")
        output_lines.append("")
        
    msg = "\n".join(output_lines)
    print(msg)
    
    # Send via telegram if requested
    if os.environ.get("VCP_AUTO_SEND", "0") == "1":
        try:
            telegram.send(msg)
        except Exception as e:
            print(f"Telegram send failed: {e}")

if __name__ == "__main__":
    main()

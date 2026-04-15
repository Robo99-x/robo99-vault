import pandas as pd
from datetime import datetime, timedelta
import json
import os
import sys
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import FinanceDataReader as fdr
from pykrx import stock
import krx_login
krx_login.login_krx()

from lib import config, db  # noqa: E402

CACHE_PATH = str(config.ALERTS / "ticker_cache.json")
CACHE_DB = str(config.CACHE_DB)


def load_top_tickers(end_date: str, top_n: int = 500):
    """Step1: 빠른 유니버스 구성 (FDR KRX listing 기반)"""
    if os.environ.get("STAGE2_TEST") == "1":
        return ["005930", "000660", "267260", "005380"][:top_n]
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                data = json.load(f)
            if data.get("date") == end_date and data.get("top_tickers"):
                return data["top_tickers"][:top_n]
        except Exception:
            pass

    try:
        listing = fdr.StockListing("KRX")
        listing = listing[listing["Market"].isin(["KOSPI", "KOSDAQ"])].copy()
        listing["MarketCap"] = pd.to_numeric(listing["MarketCap"], errors="coerce").fillna(0)
        code_col = "Code" if "Code" in listing.columns else ("Symbol" if "Symbol" in listing.columns else None)
        if not code_col:
            raise ValueError("No Code/Symbol column in FDR listing")
        top_tickers = (
            listing.sort_values(by="MarketCap", ascending=False)
            .head(top_n)[code_col].tolist()
        )
        if top_tickers:
            with open(CACHE_PATH, "w") as f:
                json.dump({"date": end_date, "top_tickers": top_tickers}, f)
            return top_tickers
    except Exception:
        pass

    # fallback: pykrx market cap (최근 영업일 탐색)
    try:
        from datetime import datetime, timedelta
        dt = datetime.strptime(end_date, "%Y%m%d")
        for i in range(7):
            d = (dt - timedelta(days=i)).strftime("%Y%m%d")
            df_cap = stock.get_market_cap_by_ticker(d)
            if df_cap is not None and len(df_cap) > 0:
                top_tickers = df_cap.sort_values(by='시가총액', ascending=False).index[:top_n].tolist()
                with open(CACHE_PATH, "w") as f:
                    json.dump({"date": d, "top_tickers": top_tickers}, f)
                return top_tickers
    except Exception:
        pass

    # last resort: use any cached tickers
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                data = json.load(f)
            if data.get("top_tickers"):
                return data["top_tickers"][:top_n]
        except Exception:
            pass

    # plan B: minimal hardcoded tickers for pipeline test
    return ["005930", "000660", "267260", "005380"][:top_n]


def fetch_price_fdr(ticker: str, start_date: str, end_date: str):
    df = fdr.DataReader(ticker, start_date, end_date)
    if df is None or df.empty:
        return None
    # normalize columns
    df = df.rename(columns={
        "Open": "시가",
        "High": "고가",
        "Low": "저가",
        "Close": "종가",
        "Volume": "거래량",
    })
    return df


# cache_is_fresh: lib.db로 위임
cache_is_fresh = db.cache_is_fresh


def fetch_price_cache(ticker: str, start_date: str, end_date: str):
    if not cache_is_fresh(end_date):
        return None
    try:
        df = db.query_df(
            """
            SELECT date, open, high, low, close, volume
            FROM ohlcv
            WHERE ticker = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            params=(ticker, start_date, end_date),
        )
        if df.empty:
            return None
        df = df.rename(columns={
            "date": "날짜",
            "open": "시가",
            "high": "고가",
            "low": "저가",
            "close": "종가",
            "volume": "거래량",
        })
        df["날짜"] = pd.to_datetime(df["날짜"])
        df = df.set_index("날짜")
        return df
    except Exception:
        return None


def get_stage2_candidates():
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    candidates = []

    top_tickers = load_top_tickers(end_date, top_n=500)
    print(f"Scanning {len(top_tickers)} stocks...")

    today_live_df = None
    try:
        today_live_df = stock.get_market_ohlcv_by_ticker(end_date, market="ALL")
        if today_live_df is not None and not today_live_df.empty:
            print(f"INFO: Fetched live data for {end_date} (len={len(today_live_df)})")
    except Exception as e:
        print(f"WARN: Live data fetch failed: {e}")

    for ticker in top_tickers:
        try:
            # 1) try cache
            df = fetch_price_cache(ticker, start_date, end_date)
            used_cache = True
            if df is None or len(df) < 200:
                # 2) fallback to live (FDR)
                used_cache = False
                try:
                    df = fetch_price_fdr(ticker, start_date, end_date)
                except Exception:
                    df = None
            if df is None or len(df) < 200:
                if used_cache is False:
                    print("WARN: KRX/FDR 응답 지연으로 최신 데이터를 수집할 수 없습니다. 캐시가 없어서 스킵합니다.")
                continue

            # Append live data if missing
            if today_live_df is not None and ticker in today_live_df.index:
                last_dt = df.index[-1]
                if last_dt.strftime("%Y%m%d") != end_date:
                    live_row = today_live_df.loc[ticker]
                    if pd.notna(live_row["종가"]) and live_row["종가"] > 0:
                        new_idx = pd.to_datetime(end_date)
                        df.loc[new_idx] = {
                            "시가": live_row["시가"],
                            "고가": live_row["고가"],
                            "저가": live_row["저가"],
                            "종가": live_row["종가"],
                            "거래량": live_row["거래량"]
                        }

            if used_cache:
                pass

            close = df["종가"]
            ma50 = close.rolling(window=50).mean()
            ma150 = close.rolling(window=150).mean()
            ma200 = close.rolling(window=200).mean()

            curr_price = close.iloc[-1]
            curr_ma50 = ma50.iloc[-1]
            curr_ma150 = ma150.iloc[-1]
            curr_ma200 = ma200.iloc[-1]

            ma200_prev = ma200.iloc[-20] if len(ma200) > 20 else ma200.iloc[0]

            high_52w = close.max()
            low_52w = close.min()

            # 거래량 조건 (오전 제외, 오후 1.5배)
            vol = df["거래량"]
            vol20 = vol.rolling(window=20).mean()
            vol_ratio = vol.iloc[-1] / vol20.iloc[-1] if vol20.iloc[-1] else 0
            is_morning = datetime.now().hour < 12
            vol_threshold = 1.5
            cond_vol = True if is_morning else (vol_ratio >= vol_threshold)

            # 터틀 트레이딩
            high_20d = close.rolling(window=20).max().iloc[-1]
            high_55d = close.rolling(window=55).max().iloc[-1]
            turtle_signal = "S2" if curr_price >= high_55d else ("S1" if curr_price >= high_20d else "대기")
            cond_turtle = turtle_signal in ["S1", "S2"]

            # 미너비니 Trend Template
            cond1 = curr_price > curr_ma150 and curr_price > curr_ma200
            cond2 = curr_ma150 > curr_ma200
            cond3 = curr_ma200 > ma200_prev
            cond4 = curr_ma50 > curr_ma150 and curr_ma50 > curr_ma200
            cond5 = curr_price > curr_ma50
            cond6 = curr_price > low_52w * 1.25
            cond7 = curr_price > high_52w * 0.75

            if all([cond1, cond2, cond3, cond4, cond5, cond6, cond7, cond_vol, cond_turtle]):
                candidates.append({
                    "ticker": ticker,
                    "price": int(curr_price),
                    "change": round((curr_price - close.iloc[-2]) / close.iloc[-2] * 100, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "turtle": turtle_signal,
                })
        except Exception:
            continue

    # Step2: pykrx 정밀 검증(시총 등) — 후보만 호출
    if candidates:
        try:
            df_cap = stock.get_market_cap_by_ticker(end_date)
            cap_map = df_cap["시가총액"].to_dict()
            for c in candidates:
                c["market_cap"] = int(cap_map.get(c["ticker"], 0))
                c["name"] = stock.get_market_ticker_name(c["ticker"]) if c["ticker"] in cap_map else c["ticker"]
        except Exception:
            pass

    return candidates


def write_batches(results, out_dir=None):
    if out_dir is None:
        out_dir = str(config.ALERTS)
    os.makedirs(out_dir, exist_ok=True)
    # sort by change desc for A list
    results_sorted = sorted(results, key=lambda x: x.get("change", 0), reverse=True)
    a_list = results_sorted[:10]
    b_list = results_sorted[10:]

    with open(os.path.join(out_dir, "stage2_candidates.json"), "w") as f:
        json.dump(results_sorted, f, ensure_ascii=False)

    def fmt_line(r):
        return f"[{r.get('ticker')}] {r.get('name','')} {r.get('price')}원 ({r.get('change')}%) vol:{r.get('vol_ratio')} turtle:{r.get('turtle')}"

    with open(os.path.join(out_dir, "stage2_A.txt"), "w") as f:
        f.write("\n".join([fmt_line(r) for r in a_list]))
    with open(os.path.join(out_dir, "stage2_B.txt"), "w") as f:
        f.write("\n".join([fmt_line(r) for r in b_list]))


def get_watchlist_tickers():
    """watchlist.md에서 KRX 종목코드 추출 (6자리 숫자 패턴)"""
    import re
    watchlist_path = config.BASE / "watchlist.md"
    tickers = []
    if not watchlist_path.exists():
        return tickers
    text = watchlist_path.read_text(encoding="utf-8")
    # [[종목명(123456)]] 패턴에서 코드 추출
    tickers += re.findall(r'\[\[.*?\((\d{6})\)\]\]', text)
    # 순수 6자리 숫자 코드 (괄호 없이)
    tickers += re.findall(r'\b(\d{6})\b', text)
    return list(set(tickers))


def get_full_universe_scan(top_n: int = 1200):
    """--full 모드: 전 종목 조건별 True/False 저장 (AND 필터 없음)

    출력: alerts/universe_scan.json
    각 종목 필드:
      ticker, name, price, change, vol_ratio, market_cap,
      turtle (S2/S1/대기),
      cond_ma (cond1+2+3+4+5 모두 True),
      cond_52w (cond6+7 모두 True),
      cond_vol, cond_turtle,
      cond_all (전체 통과 여부),
      conditions: {c1..c7, vol, turtle 각각 True/False}
    """
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    out_dir = str(config.ALERTS)

    # 유니버스: top_n + 워치리스트 강제 포함
    base_tickers = load_top_tickers(end_date, top_n=top_n)
    watchlist_tickers = get_watchlist_tickers()
    all_tickers = list(dict.fromkeys(base_tickers + watchlist_tickers))  # 중복 제거, 순서 유지
    print(f"[FULL] 스캔 대상: {len(all_tickers)}종목 (top{top_n} + 워치리스트 {len(watchlist_tickers)}개)")

    today_live_df = None
    try:
        today_live_df = stock.get_market_ohlcv_by_ticker(end_date, market="ALL")
    except Exception:
        pass

    results = []
    skipped = 0

    for ticker in all_tickers:
        try:
            df = fetch_price_cache(ticker, start_date, end_date)
            if df is None or len(df) < 50:
                try:
                    df = fetch_price_fdr(ticker, start_date, end_date)
                except Exception:
                    df = None
            if df is None or len(df) < 50:
                skipped += 1
                continue

            if today_live_df is not None and ticker in today_live_df.index:
                last_dt = df.index[-1]
                if last_dt.strftime("%Y%m%d") != end_date:
                    live_row = today_live_df.loc[ticker]
                    if pd.notna(live_row["종가"]) and live_row["종가"] > 0:
                        new_idx = pd.to_datetime(end_date)
                        df.loc[new_idx] = {
                            "시가": live_row["시가"], "고가": live_row["고가"],
                            "저가": live_row["저가"], "종가": live_row["종가"],
                            "거래량": live_row["거래량"]
                        }

            close = df["종가"]
            if len(close) < 50:
                skipped += 1
                continue

            ma50  = close.rolling(50).mean()
            ma150 = close.rolling(150).mean()
            ma200 = close.rolling(200).mean()

            curr_price  = close.iloc[-1]
            curr_ma50   = ma50.iloc[-1]
            curr_ma150  = ma150.iloc[-1]
            curr_ma200  = ma200.iloc[-1]
            ma200_prev  = ma200.iloc[-20] if len(ma200) > 20 else ma200.iloc[0]
            high_52w    = close.max()
            low_52w     = close.min()

            vol     = df["거래량"]
            vol20   = vol.rolling(20).mean()
            vol_ratio = vol.iloc[-1] / vol20.iloc[-1] if (vol20.iloc[-1] and vol20.iloc[-1] > 0) else 0
            is_morning = datetime.now().hour < 12
            cond_vol = True if is_morning else (vol_ratio >= 1.5)

            high_20d = close.rolling(20).max().iloc[-1]
            high_55d = close.rolling(55).max().iloc[-1]
            turtle   = "S2" if curr_price >= high_55d else ("S1" if curr_price >= high_20d else "대기")
            cond_turtle = turtle in ["S1", "S2"]

            c1 = bool(curr_price > curr_ma150 and curr_price > curr_ma200)
            c2 = bool(curr_ma150 > curr_ma200)
            c3 = bool(curr_ma200 > ma200_prev)
            c4 = bool(curr_ma50 > curr_ma150 and curr_ma50 > curr_ma200)
            c5 = bool(curr_price > curr_ma50)
            c6 = bool(curr_price > low_52w * 1.25)
            c7 = bool(curr_price > high_52w * 0.75)

            change = round((curr_price - close.iloc[-2]) / close.iloc[-2] * 100, 2) if len(close) > 1 else 0.0

            results.append({
                "ticker":     ticker,
                "name":       "",  # 후처리로 채움
                "price":      int(curr_price),
                "change":     change,
                "vol_ratio":  round(vol_ratio, 2),
                "market_cap": 0,
                "turtle":     turtle,
                "cond_ma":    all([c1, c2, c3, c4, c5]),
                "cond_52w":   all([c6, c7]),
                "cond_vol":   cond_vol,
                "cond_turtle": cond_turtle,
                "cond_all":   all([c1,c2,c3,c4,c5,c6,c7,cond_vol,cond_turtle]),
                "cond_count": sum([c1,c2,c3,c4,c5,c6,c7,cond_vol,cond_turtle]),
                "conditions": {"c1":c1,"c2":c2,"c3":c3,"c4":c4,"c5":c5,"c6":c6,"c7":c7,
                               "vol":cond_vol,"turtle":cond_turtle},
                "in_watchlist": ticker in watchlist_tickers,
            })
        except Exception:
            skipped += 1
            continue

    print(f"[FULL] 스캔 완료: {len(results)}종목, 스킵: {skipped}")

    # 시총 + 종목명 일괄 조회
    try:
        df_cap = stock.get_market_cap_by_ticker(end_date)
        cap_map = df_cap["시가총액"].to_dict()
        for r in results:
            r["market_cap"] = int(cap_map.get(r["ticker"], 0))
            r["name"] = stock.get_market_ticker_name(r["ticker"])
    except Exception:
        pass

    # cond_count 내림차순 정렬 (조건 많이 통과한 순)
    results.sort(key=lambda x: (-x["cond_count"], -x.get("market_cap", 0)))

    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "universe_size": len(all_tickers),
        "scanned": len(results),
        "passed_all": sum(1 for r in results if r["cond_all"]),
        "stocks": results,
    }
    out_path = os.path.join(out_dir, "universe_scan.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[FULL] 저장 완료: {out_path} ({len(results)}종목)")
    return results


if __name__ == "__main__":
    import sys
    if "--full" in sys.argv:
        top_n = 1200
        for arg in sys.argv:
            if arg.startswith("--top="):
                try:
                    top_n = int(arg.split("=")[1])
                except ValueError:
                    pass
        get_full_universe_scan(top_n=top_n)
    else:
        results = get_stage2_candidates()
        if not results:
            print("조건에 맞는 종목이 없습니다.")
        else:
            write_batches(results)
        for res in results:
            print(f"[{res.get('ticker')}] {res.get('name','')}: {res.get('price')}원 ({res.get('change')}%)")

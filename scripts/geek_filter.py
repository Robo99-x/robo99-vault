#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pykrx import stock
import krx_login

krx_login.login_krx()

from lib import config  # noqa: E402

IN_PATH = str(config.ALERTS / "stage2_candidates.json")
OUT_PATH = str(config.ALERTS / "stage2_geek_filtered.json")
RS_PATH = str(config.ALERTS / "rs_rankings.json")
RS_MIN_PCT = 50  # RS 하위 50% 종목은 "RS하위" 태그


def _pick_col(cols, keywords):
    for k in keywords:
        for c in cols:
            if k in c:
                return c
    return None


def get_flow_score(ticker):
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
    try:
        try:
            df = stock.get_market_trading_value_by_date(start, end, ticker)
        except Exception:
            # fallback to trading volume by investor when value feed breaks
            df = stock.get_market_trading_volume_by_date(start, end, ticker)
        if df is None or len(df) == 0:
            return 0, None, None, None
        # use last 5 trading days
        recent = df.tail(5)
        last_date = recent.index[-1].strftime("%Y%m%d") if len(recent.index) > 0 else None
        cols = list(recent.columns)
        f_col = _pick_col(cols, ["외국인"])
        i_col = _pick_col(cols, ["기관합계", "기관"])
        if not f_col or not i_col:
            return 0, None, None, last_date
        foreign = recent[f_col].sum()
        inst = recent[i_col].sum()
        score = 0
        if foreign < 0: score += 1
        if inst < 0: score += 1
        return score, int(foreign), int(inst), last_date
    except Exception:
        return 0, None, None, None


def load_rs_rankings():
    """rs_ranking.py가 생성한 JSON 로드. 없으면 빈 dict 반환."""
    if not os.path.exists(RS_PATH):
        return {}
    try:
        with open(RS_PATH, "r") as f:
            data = json.load(f)
        return data.get("rankings", {})
    except Exception:
        return {}


def main():
    if not os.path.exists(IN_PATH):
        print("No candidates file.")
        return
    with open(IN_PATH, "r") as f:
        candidates = json.load(f)

    rs_map = load_rs_rankings()
    rs_available = len(rs_map) > 0
    if not rs_available:
        print("WARN: rs_rankings.json 없음. RS 필터 미적용. rs_ranking.py 먼저 실행하세요.")

    out = []
    for c in candidates:
        ticker = c.get("ticker")
        risk_score = 0

        # [1] 수급 리스크 (외국인/기관 5일 순매도)
        flow_score, foreign, inst, last_date = get_flow_score(ticker)
        risk_score += flow_score

        # [2] 태그 결정 (버그 수정: 제외 기준을 2로 수정)
        tag = "OK"
        if foreign is None or inst is None:
            tag = "미확인"
        elif risk_score >= 2:
            tag = "제외"   # 외국인+기관 동시 순매도 → 제외
        elif risk_score == 1:
            tag = "주의"   # 둘 중 하나만 순매도 → 주의

        # [3] RS 백분위 추가
        rs_info = rs_map.get(ticker, {})
        rs_pct = rs_info.get("rs_pct", None)
        rs_score = rs_info.get("rs_score", None)

        rs_tag = None
        if rs_pct is not None:
            if rs_pct < RS_MIN_PCT:
                rs_tag = "RS하위"  # RS 하위 50% → 별도 표시
        else:
            rs_tag = "RS미확인"

        out.append({
            **c,
            "risk_score": risk_score,
            "foreign_5d": foreign,
            "inst_5d": inst,
            "last_flow_date": last_date,
            "tag": tag,
            "rs_pct": rs_pct,
            "rs_score": rs_score,
            "rs_tag": rs_tag,
        })

    # RS 상위 종목 우선 정렬 (rs_pct 내림차순, None은 후순위)
    out.sort(key=lambda x: (x.get("rs_pct") is not None, x.get("rs_pct") or 0), reverse=True)

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, ensure_ascii=False)

    excluded = sum(1 for x in out if x.get("tag") == "제외")
    rs_low = sum(1 for x in out if x.get("rs_tag") == "RS하위")
    print(f"saved {OUT_PATH} ({len(out)} items | 제외:{excluded} | RS하위:{rs_low})")


if __name__ == "__main__":
    main()

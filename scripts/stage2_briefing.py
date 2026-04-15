#!/usr/bin/env python3
import json
import os
import sys
import hashlib
from datetime import datetime
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import FinanceDataReader as fdr
from pykrx import stock as krx_stock

from lib import config, telegram  # noqa: E402

IN_PATH = str(config.ALERTS / "stage2_geek_filtered.json")
OUT_PATH = str(config.ALERTS / "stage2_briefing.txt")
SENT_LOG = str(config.ALERTS / "stage2_sent_hashes.json")

BASE = config.BASE


def load_sector_map():
    try:
        listing = fdr.StockListing("KRX")
        listing = listing.set_index("Code")
        return listing["Sector"].to_dict()
    except Exception:
        return {}


def _load_sent():
    if not os.path.exists(SENT_LOG):
        return []
    try:
        return json.loads(Path(SENT_LOG).read_text())[-200:]
    except Exception:
        return []


def _save_sent(h):
    arr = _load_sent()
    arr.append(h)
    Path(SENT_LOG).write_text(json.dumps(arr[-200:], ensure_ascii=False, indent=2))


def _send_once(text: str):
    """lib.telegram.send로 위임하되, 텍스트 해시 기반 중복 전송 방지."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    sent = set(_load_sent())
    if h in sent:
        return False
    try:
        telegram.send(text)
        _save_sent(h)
        return True
    except Exception:
        return False


def turtle_reason(signal: str):
    if signal == "S2":
        return "S2(55일 고점 돌파·가속)"
    if signal == "S1":
        return "S1(20일 고점 돌파)"
    return "대기"


def main():
    if not os.path.exists(IN_PATH):
        print("No geek filtered file.")
        return

    with open(IN_PATH, "r") as f:
        items = json.load(f)

    if not items:
        print("No items.")
        return

    sector_map = load_sector_map()

    # A리스트: "제외" 태그 제거 후 RS 백분위 우선, 동점이면 등락률 순
    items_filtered = [x for x in items if x.get("tag") != "제외"]
    items_sorted = sorted(
        items_filtered,
        key=lambda x: (x.get("rs_pct") or 0, x.get("change", 0)),
        reverse=True
    )
    a_list = items_sorted[:10]

    # ensure name filled (fallback to ticker)
    for it in a_list:
        if not it.get("name") or it.get("name") == it.get("ticker"):
            try:
                it["name"] = krx_stock.get_market_ticker_name(it.get("ticker")) or it.get("ticker")
            except Exception:
                try:
                    it["name"] = fdr.StockListing("KRX").set_index("Code").get("Name", {}).get(it.get("ticker"), it.get("ticker"))
                except Exception:
                    it["name"] = it.get("ticker")

    # group by sector
    by_sector = {}
    for it in a_list:
        sector = sector_map.get(it.get("ticker"), "미분류") or "미분류"
        by_sector.setdefault(sector, []).append(it)

    # top 3 sectors by count
    top_sectors = sorted(by_sector.items(), key=lambda x: len(x[1]), reverse=True)[:3]

    # title
    now = datetime.now()
    ampm = "오전" if now.hour < 12 else "오후"
    title = f"📊 [{now.strftime('%m/%d')} {ampm}] Stage2 루틴(디테일)"
    lead = "종목명 기준으로 요약합니다. 현재가·등락·거래량비·터틀·리스크까지 함께 확인하세요."

    lines = [title, lead, ""]
    
    global_last_date = "미상"

    for i, (sector, lst) in enumerate(top_sectors, start=1):
        lines.append(f"[{sector}] (수급/추세 동행 확인 필요)")
        # pick up to 10
        for it in lst[:10]:
            name = it.get("name", it.get("ticker"))
            price = f"{it.get('price', 0):,}"
            change = f"{it.get('change', 0):.2f}%"
            if not change.startswith("-") and it.get('change', 0) > 0:
                change = f"+{change}"
            volr = f"{it.get('vol_ratio', 0):.1f}배"
            turtle = it.get("turtle")
            reason = turtle_reason(turtle)
            risk = it.get("tag", "미확인")
            
            # extract global last date if available
            ld = it.get("last_flow_date")
            if ld and global_last_date == "미상":
                global_last_date = ld
            
            # flow check
            f_5d = it.get("foreign_5d")
            i_5d = it.get("inst_5d")
            flow_text = ""
            if f_5d is not None and i_5d is not None:
                # convert to 100M won (억) if value, but fallback could be volume.
                # Just show the formatted numbers roughly
                f_억 = f_5d / 1_0000_0000
                i_억 = i_5d / 1_0000_0000
                flow_text = f" | 외인5D: {f_억:,.0f}억 / 기관5D: {i_억:,.0f}억"
            
            # 시각적으로 개선된 VCP 스캐너 폼과 유사하게 출력
            lines.append(
                f"🔥 [{it.get('ticker')}] **{name}**: {price}원 ({change})"
            )
            rs_pct = it.get("rs_pct")
            rs_tag = it.get("rs_tag", "")
            rs_text = f"RS {rs_pct:.0f}%" if rs_pct is not None else "RS미확인"
            if rs_tag == "RS하위":
                rs_text += "⚠️"
            lines.append(
                f"  └ 🎯 터틀: {reason} | 📊 거래량: {volr} | 🛡️ 리스크: {risk} | 📈 {rs_text}{flow_text}"
            )
            lines.append("")

    lines.append("💡 전략: 돌파 확인 후 분할 접근. 리스크 태그가 ‘주의/제외’면 후순위 처리.")
    lines.append(f"📅 수급(리스크) 기준일: {global_last_date}")

    msg = "\n".join(lines)
    with open(OUT_PATH, "w") as f:
        f.write(msg)

    # auto-send detailed briefing once (idempotent)
    # NOTE: default OFF to avoid duplicate delivery with cron announce.
    if os.environ.get("STAGE2_AUTO_SEND", "0") == "1":
        _send_once(msg)

    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    main()

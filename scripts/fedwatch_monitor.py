#!/usr/bin/env python3
"""
fedwatch_monitor.py — CME FedWatch 연내 금리인하 기대 모니터링

30-day Fed Funds 선물(ZQ)에서 연내 인하 기대를 추적하고
  - 매일 07:55 KST: 정기 브리핑 (무조건 전송)
  - 변화 감지: Dec 기준 ±10bp 이상 시 즉시 알림

실행:
  cd ~/robo99_hq/scripts && uv run python fedwatch_monitor.py [--daily] [--force]
  스케줄러에서 자동 실행
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.config import BASE, TG_CHAT_ID
from lib import telegram as _tg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("fedwatch")

KST = 9 * 3600
SNAPSHOT_FILE = BASE / "30_ops" / "fedwatch_snapshot.json"

# 추적 계약 (월 코드 → 이름)
ZQ_CONTRACTS = {
    "ZQM26.CBT": "Jun",
    "ZQN26.CBT": "Jul",
    "ZQQ26.CBT": "Aug",
    "ZQU26.CBT": "Sep",
    "ZQV26.CBT": "Oct",
    "ZQX26.CBT": "Nov",
    "ZQZ26.CBT": "Dec",
}

# 알림 임계치
ALERT_BP = 10  # Dec ±10bp 이상 즉시 알림


def _fetch_zq_curve() -> dict[str, float] | None:
    """Yahoo Finance에서 ZQ 선물 → {month: implied_rate}."""
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0"}
        curve: dict[str, float] = {}
        for ticker, month in ZQ_CONTRACTS.items():
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=12)
            data = r.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                continue
            closes = [c for c in result[0].get("indicators", {}).get("quote", [{}])[0].get("close", []) if c]
            if closes:
                curve[month] = round(100.0 - closes[-1], 4)
        return curve if len(curve) >= 4 else None
    except Exception as e:
        log.error(f"ZQ 조회 실패: {e}")
        return None


def _load_snapshot() -> dict | None:
    if SNAPSHOT_FILE.exists():
        try:
            return json.loads(SNAPSHOT_FILE.read_text())
        except Exception:
            return None
    return None


def _save_snapshot(curve: dict[str, float]) -> None:
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + KST)
    snap = {"curve": curve, "updated_at": ts.strftime("%Y-%m-%dT%H:%M:%S KST")}
    SNAPSHOT_FILE.write_text(json.dumps(snap, ensure_ascii=False, indent=2))


def _expected_cuts(ref_rate: float, dec_rate: float) -> float:
    """연내 예상 인하 횟수. 양수 = 인하, 음수 = 인상."""
    return round((ref_rate - dec_rate) / 0.25, 2)


def _build_message(curve: dict[str, float], prev_curve: dict[str, float] | None, mode: str = "change") -> str:
    """텔레그램 메시지 생성.
    mode: 'daily' = 정기 브리핑 / 'change' = 변화 알림
    """
    ts = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + KST)
    ref = curve.get("Jun") or curve.get("Jul", 3.625)  # 근월물 = 현재 금리 근사치
    dec = curve.get("Dec")

    cuts_now = _expected_cuts(ref, dec) if dec else 0.0
    cuts_prev = _expected_cuts(ref, prev_curve.get("Dec")) if prev_curve and prev_curve.get("Dec") else None

    # 방향성 판단
    if cuts_prev is not None:
        delta = cuts_now - cuts_prev
        if delta >= 0.15:
            direction = "🟢 DOVISH SHIFT"
            portfolio_hint = "성장주·장기채 비중 확대 고려"
        elif delta <= -0.15:
            direction = "🔴 HAWKISH SHIFT"
            portfolio_hint = "방어주·단기채·달러 비중 주목"
        else:
            direction = "🟡 중립 (변화 미미)"
            portfolio_hint = "현 포트폴리오 유지"
    else:
        direction = ""
        portfolio_hint = ""

    prefix = "📊 FedWatch 정기 브리핑" if mode == "daily" else "🔔 FedWatch 인하기대 변화"
    lines = [
        f"{prefix} ({ts.strftime('%m/%d %H:%M')} KST)",
        "",
        f"연내 예상 인하: {cuts_now:.2f}회",
    ]

    if cuts_prev is not None:
        delta = cuts_now - cuts_prev
        arrow = "↑" if delta > 0 else "↓"
        lines[2] += f" ({arrow}{abs(delta):.2f}회, {delta * 25:.0f}bp)"

    if dec:
        dec_line = f"Dec 암시 금리: {dec:.3f}%"
        if prev_curve and prev_curve.get("Dec"):
            delta_bp = (dec - prev_curve["Dec"]) * 100
            if abs(delta_bp) >= 1:
                dec_line += f" ({'+' if delta_bp > 0 else ''}{delta_bp:.1f}bp)"
        lines.append(dec_line)

    lines.append("")

    # 월별 커브
    for month, rate in curve.items():
        change = ""
        if prev_curve and month in prev_curve:
            dbp = (rate - prev_curve[month]) * 100
            if abs(dbp) >= 1:
                change = f" ({'+' if dbp > 0 else ''}{dbp:.1f}bp)"
        lines.append(f"  {month}: {rate:.3f}%{change}")

    if direction:
        lines += ["", f"방향: {direction}"]
    if portfolio_hint:
        lines.append(f"포트폴리오: {portfolio_hint}")

    return "\n".join(lines)


def run(daily: bool = False, force: bool = False) -> None:
    log.info(f"FedWatch 실행 (daily={daily}, force={force})")

    curve = _fetch_zq_curve()
    if not curve:
        log.warning("ZQ 데이터 조회 실패")
        return

    log.info(f"커브: {curve}")
    prev = _load_snapshot()
    prev_curve = prev.get("curve") if prev else None

    # 알림 여부 결정
    should_notify = force or daily
    if not should_notify and prev_curve:
        dec_now = curve.get("Dec")
        dec_prev = prev_curve.get("Dec")
        if dec_now and dec_prev:
            delta_bp = abs((dec_now - dec_prev) * 100)
            if delta_bp >= ALERT_BP:
                should_notify = True
                log.info(f"Dec 변화 {delta_bp:.1f}bp → 즉시 알림")

    _save_snapshot(curve)

    if should_notify:
        mode = "daily" if daily else "change"
        msg = _build_message(curve, prev_curve, mode)
        ok = _tg.send(msg, chat_id=TG_CHAT_ID)
        log.info(f"알림 전송: {ok}")
    else:
        cuts = _expected_cuts(curve.get("Jun", 3.625), curve.get("Dec", 3.75))
        log.info(f"변화 미미 — 알림 생략 (예상 인하: {cuts:.2f}회)")


if __name__ == "__main__":
    import argparse, os as _os
    p = argparse.ArgumentParser()
    p.add_argument("--daily", action="store_true", help="정기 브리핑 모드 (무조건 전송)")
    p.add_argument("--force", action="store_true", help="강제 알림")
    args = p.parse_args()
    # 스케줄러에서 env var로 모드 전달 가능
    daily = args.daily or _os.environ.get("FEDWATCH_MODE") == "daily"
    force = args.force
    run(daily=daily, force=force)

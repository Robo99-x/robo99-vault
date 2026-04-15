"""Weekly market-fit upgrade routine for Stage2 scanner.

매주 1회 실행 (토요일 08:00):
  1. 오늘 stage2_geek_filtered.json 을 날짜별 아카이브에 저장
  2. N 영업일 전 스캔 결과의 사후 성과(히트레이트) 계산
  3. 최근 market_snapshot 으로 시장 레짐 감지 (VIX + 지수 추세)
  4. 레짐 + 히트레이트 기반 파라미터 조정 권고 생성
  5. Telegram 리포트 발송 + 감사 로그 기록
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib import config, db, telegram  # noqa: E402

LOG_PATH = config.ALERTS / "weekly_upgrade.log"
ARCHIVE_DIR = config.ALERTS / "stage2_archive"

# ── 파라미터 기준값 (현재 stage2_scanner.py 설정과 동일) ─────────────
PARAM_DEFAULTS = {
    "vol_ratio_min": 1.5,
    "turtle_window": 55,
    "gain_threshold_pct": 3.0,  # 히트 판정 기준 수익률
    "hit_rate_ok": 50.0,        # 이 이상이면 파라미터 유지
    "hit_rate_warn": 30.0,      # 이 이하면 강화 권고
}


# ── 1. 스캔 결과 아카이브 ──────────────────────────────────────────────

def archive_scan_results() -> Path | None:
    """오늘 stage2_geek_filtered.json → ARCHIVE_DIR/stage2_geek_YYYY-MM-DD.json"""
    src = config.ALERTS / "stage2_geek_filtered.json"
    if not src.exists():
        return None

    ARCHIVE_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    dst = ARCHIVE_DIR / f"stage2_geek_{today}.json"

    if dst.exists():
        return dst  # 이미 저장됨

    dst.write_text(src.read_text())
    return dst


# ── 2. 히트레이트 계산 ────────────────────────────────────────────────

def calc_hit_rate(
    lookback_days: int = 5,
    gain_threshold_pct: float = PARAM_DEFAULTS["gain_threshold_pct"],
) -> dict:
    """N 영업일 전 아카이브 스캔 결과의 사후 성과 계산.

    Returns:
        status: ok | insufficient_history | no_archive
        hit_rate: 히트율 (%)
        details: 상위 5종목 성과
    """
    if not ARCHIVE_DIR.exists():
        return {"status": "no_archive", "hit_rate": None, "files_found": 0}

    archives = sorted(ARCHIVE_DIR.glob("stage2_geek_*.json"))
    if not archives:
        return {"status": "no_archive", "hit_rate": None, "files_found": 0}

    # lookback_days * 1.5 달력일 이전 파일 대상
    cutoff = (datetime.now() - timedelta(days=lookback_days * 1.5)).strftime("%Y-%m-%d")
    old_files = [f for f in archives if f.stem.replace("stage2_geek_", "") <= cutoff]

    if not old_files:
        return {
            "status": "insufficient_history",
            "hit_rate": None,
            "files_found": len(archives),
            "oldest": archives[0].stem.replace("stage2_geek_", "") if archives else None,
        }

    old_file = old_files[-1]
    scan_date_str = old_file.stem.replace("stage2_geek_", "").replace("-", "")
    today_str = datetime.now().strftime("%Y%m%d")

    candidates = json.loads(old_file.read_text())
    if not candidates:
        return {"status": "empty_archive", "hit_rate": None}

    hits = 0
    evaluated = 0
    details = []
    rows = []

    for c in candidates:
        ticker = c.get("ticker", "")
        try:
            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT date, close FROM ohlcv "
                    "WHERE ticker=? AND date>=? AND date<=? ORDER BY date",
                    (ticker, scan_date_str, today_str),
                ).fetchall()

            if len(rows) < 2:
                continue

            entry_price = rows[0][1]
            current_price = rows[-1][1]
            if entry_price <= 0:
                continue

            gain_pct = (current_price - entry_price) / entry_price * 100
            is_hit = gain_pct >= gain_threshold_pct
            hits += is_hit
            evaluated += 1
            details.append(
                {
                    "ticker": ticker,
                    "name": c.get("name", ticker),
                    "entry": entry_price,
                    "current": current_price,
                    "gain_pct": round(gain_pct, 2),
                    "hit": is_hit,
                }
            )
        except Exception:
            continue

    hit_rate = hits / evaluated * 100 if evaluated > 0 else None
    details.sort(key=lambda x: x["gain_pct"], reverse=True)

    return {
        "status": "ok",
        "scan_date": old_file.stem.replace("stage2_geek_", ""),
        "gain_threshold_pct": gain_threshold_pct,
        "evaluated": evaluated,
        "hits": hits,
        "hit_rate": round(hit_rate, 1) if hit_rate is not None else None,
        "trading_days": len(rows) - 1 if rows else 0,
        "details": details[:5],
    }


# ── 3. 시장 레짐 감지 ─────────────────────────────────────────────────

def load_market_snapshots(n: int = 10) -> list[dict]:
    """최근 n 개 market_snapshot_YYYYMMDD.json 로드."""
    files = sorted(config.ALERTS.glob("market_snapshot_*.json"), reverse=True)[:n]
    result = []
    for f in files:
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            continue
    return result


def detect_market_regime(snapshots: list[dict]) -> dict:
    """VIX 평균 + S&P500 10일 추세로 레짐 분류.

    Regimes:
        calm    — VIX < 20
        caution — VIX 20-30
        fear    — VIX > 30
    """
    if not snapshots:
        return {"regime": "unknown", "avg_vix": None, "trend": "unknown", "sp500_trend_pct": 0.0}

    vix_vals, sp_vals = [], []
    for s in snapshots:
        indices = s.get("indices", {})
        vix = (indices.get("VIX") or {}).get("price")
        sp = (indices.get("S&P 500") or {}).get("price")
        if vix:
            vix_vals.append(vix)
        if sp:
            sp_vals.append(sp)

    avg_vix = sum(vix_vals) / len(vix_vals) if vix_vals else None

    # 지수 추세: 최신 vs 가장 오래된 스냅샷
    trend_pct = 0.0
    if len(sp_vals) >= 2:
        trend_pct = (sp_vals[0] - sp_vals[-1]) / sp_vals[-1] * 100

    if avg_vix and avg_vix > 30:
        regime = "fear"
    elif avg_vix and avg_vix > 20:
        regime = "caution"
    else:
        regime = "calm"

    if trend_pct > 2:
        trend = "uptrend"
    elif trend_pct < -2:
        trend = "downtrend"
    else:
        trend = "sideways"

    return {
        "regime": regime,
        "avg_vix": round(avg_vix, 2) if avg_vix else None,
        "trend": trend,
        "sp500_trend_pct": round(trend_pct, 2),
        "snapshots_used": len(snapshots),
    }


# ── 4. 파라미터 권고 ──────────────────────────────────────────────────

def recommend_params(regime: dict, hit_rate_result: dict) -> list[str]:
    """레짐 + 히트레이트 기반 파라미터 조정 권고 목록 반환."""
    recs = []

    # 레짐 기반
    r = regime.get("regime", "unknown")
    if r == "fear":
        recs.append("⚠️ VIX 30↑ 공포 구간: vol_ratio_min 1.5→2.0 상향 권고")
        recs.append("⚠️ geek_filter risk_score 임계값 강화 검토")
    elif r == "caution":
        recs.append("🟡 VIX 20-30 주의 구간: 현재 파라미터 유지")
    else:
        recs.append("✅ VIX 안정 (< 20): 현재 파라미터 적정")

    trend = regime.get("trend", "unknown")
    if trend == "downtrend":
        recs.append("📉 지수 하락 추세: S1(20일) 신뢰도 하락 — S2(55일) 위주 권고")
    elif trend == "uptrend":
        recs.append("📈 지수 상승 추세: stage2_relaxed 병행 활용 고려")

    # 히트레이트 기반
    hr = hit_rate_result.get("hit_rate")
    ok_thresh = PARAM_DEFAULTS["hit_rate_ok"]
    warn_thresh = PARAM_DEFAULTS["hit_rate_warn"]

    if hr is None:
        recs.append("⏳ 히트레이트 데이터 미축적 — 다음 주 분석 예정")
    elif hr < warn_thresh:
        recs.append(f"❌ 히트레이트 {hr}% ({warn_thresh}% 미만): vol_ratio↑ + risk_score↑ 강화 시급")
    elif hr < ok_thresh:
        recs.append(f"🟡 히트레이트 {hr}% ({warn_thresh}-{ok_thresh}%): 소폭 강화 검토")
    else:
        recs.append(f"✅ 히트레이트 {hr}% ({ok_thresh}%↑): 현재 파라미터 유지")

    return recs


# ── 5. 리포트 조립 ────────────────────────────────────────────────────

def build_report(
    regime: dict,
    hit_rate_result: dict,
    recs: list[str],
    archived_path: Path | None,
) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 주간 스캐너 업그레이드 리포트 ({now_str})", ""]

    # 시장 레짐
    regime_emoji = {"calm": "🟢", "caution": "🟡", "fear": "🔴"}.get(regime["regime"], "⚪")
    lines.append(f"{regime_emoji} 시장 레짐: {regime['regime'].upper()}")
    vix = regime.get("avg_vix")
    if vix:
        lines.append(
            f"  VIX 평균 {vix} | 추세 {regime['trend']}"
            f" ({regime['sp500_trend_pct']:+.1f}%, {regime['snapshots_used']}일 기준)"
        )
    lines.append("")

    # 히트레이트
    status = hit_rate_result.get("status")
    hr = hit_rate_result.get("hit_rate")
    if status == "ok" and hr is not None:
        hr_emoji = "✅" if hr >= PARAM_DEFAULTS["hit_rate_ok"] else (
            "🟡" if hr >= PARAM_DEFAULTS["hit_rate_warn"] else "❌"
        )
        lines.append(
            f"{hr_emoji} 히트레이트: {hr}%"
            f" ({hit_rate_result['hits']}/{hit_rate_result['evaluated']}종목,"
            f" +{hit_rate_result['gain_threshold_pct']}% 기준,"
            f" {hit_rate_result['trading_days']}영업일 경과)"
        )
        lines.append(f"  분석 기준: {hit_rate_result['scan_date']} 스캔")
        top = hit_rate_result.get("details", [])[:3]
        if top:
            lines.append("  상위 성과:")
            for d in top:
                mark = "✓" if d["hit"] else "✗"
                lines.append(f"    {mark} {d['name']}({d['ticker']}): {d['gain_pct']:+.1f}%")
    elif status == "insufficient_history":
        oldest = hit_rate_result.get("oldest", "?")
        found = hit_rate_result.get("files_found", 0)
        lines.append(f"⏳ 히트레이트: 이력 축적 중 ({found}일 분, 최초 {oldest})")
    else:
        lines.append("⏳ 히트레이트: 아카이브 없음 — 오늘부터 수집 시작")
    lines.append("")

    # 권고사항
    lines.append("권고사항:")
    for rec in recs:
        lines.append(f"  {rec}")

    if archived_path:
        lines.append(f"\n📁 오늘 스캔 아카이브: {archived_path.name}")

    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────

def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entries = [f"\n[{now_str}] === 주간 업그레이드 시작 ==="]

    # 1. 오늘 스캔 결과 아카이브
    archived = archive_scan_results()
    log_entries.append(f"아카이브: {archived or '스킵 (파일 없음)'}")

    # 2. 시장 레짐 감지
    snapshots = load_market_snapshots(n=10)
    regime = detect_market_regime(snapshots)
    log_entries.append(f"레짐: {regime}")

    # 3. 히트레이트 계산
    hit_rate_result = calc_hit_rate(
        lookback_days=5,
        gain_threshold_pct=PARAM_DEFAULTS["gain_threshold_pct"],
    )
    log_entries.append(f"히트레이트: {hit_rate_result}")

    # 4. 파라미터 권고
    recs = recommend_params(regime, hit_rate_result)

    # 5. 리포트 생성 + Telegram 발송
    report = build_report(regime, hit_rate_result, recs, archived)
    print(report)

    try:
        telegram.send(report)
        log_entries.append("Telegram 발송 완료")
    except Exception as e:
        log_entries.append(f"Telegram 발송 실패: {e}")
        print(f"[경고] Telegram 발송 실패: {e}")

    log_entries.append("완료")
    with open(LOG_PATH, "a") as f:
        f.write("\n".join(log_entries) + "\n")


if __name__ == "__main__":
    main()

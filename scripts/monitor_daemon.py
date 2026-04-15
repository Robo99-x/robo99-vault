#!/usr/bin/env python3
"""
monitor_daemon.py — 시장 모니터링 데몬

토큰 0으로 시장 조건 체크 → 텔레그램 직접 발송.
systemd user service 또는 직접 실행.
"""

import json, logging, os, signal, sys, hashlib, importlib.util
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib import telegram as _tg  # noqa: E402
from lib.config import TG_CHAT_ID as _DEFAULT_CHAT  # noqa: E402

# ── 경로 ─────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent  # workspace/
MONITOR = BASE / "monitor"
ALERTS_FILE = MONITOR / "alerts.json"
RULES_DIR = MONITOR / "rules"
NEWS_DIR = MONITOR / "news"
LOG_DIR = BASE / "alerts"

LOG_DIR.mkdir(parents=True, exist_ok=True)
MONITOR.mkdir(parents=True, exist_ok=True)
RULES_DIR.mkdir(parents=True, exist_ok=True)
NEWS_DIR.mkdir(parents=True, exist_ok=True)

# ── 로깅 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_DIR / "daemon.log", encoding="utf-8")]
)
log = logging.getLogger("monitor")


def send_tg(text, target="all"):
    """lib.telegram.send 위임. target 매개변수는 호환성 유지 (현재 모두 기본 채널로 전송)."""
    try:
        ok = _tg.send(text, chat_id=_DEFAULT_CHAT)
        if not ok:
            log.warning("텔레그램 전송 실패")
    except Exception as e:
        log.error(f"TG 실패: {e}")


def _load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


# ── 중국 ─────────────────────────────────────────────
def check_china():
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        hit = df[(df["总市值"].fillna(0) >= 5.3e9) & (df["涨跌幅"].fillna(0).abs() >= 8.0)]
        return [f"{'🔴' if r['涨跌幅']<0 else '🟢'} 🇨🇳 {r['名称']}({r['代码']}) {r['涨跌幅']:+.1f}%"
                for _, r in hit.iterrows()]
    except Exception as e:
        log.error(f"중국: {e}")
        return []


# ── 일본 ─────────────────────────────────────────────
JP_FILE = MONITOR / "jp_large_caps.json"
_JP_DEFAULT = [
    "7203.T", "6758.T", "9984.T", "6861.T", "8306.T", "6501.T", "7267.T",
    "4502.T", "6902.T", "9432.T", "8058.T", "6301.T", "7741.T", "4063.T",
    "9433.T", "8035.T", "6098.T", "4661.T", "6367.T", "3382.T", "7974.T",
    "4543.T", "2914.T", "8766.T", "6594.T", "4568.T", "9983.T", "6954.T",
]

def check_japan():
    try:
        import yfinance as yf
        tickers = json.loads(JP_FILE.read_text()) if JP_FILE.exists() else _JP_DEFAULT
        data = yf.download(tickers, period="2d", group_by="ticker", threads=True, progress=False)
        alerts = []
        for t in tickers:
            try:
                h = data[t]["Close"].dropna()
                if len(h) >= 2:
                    prev, last = float(h.iloc[-2]), float(h.iloc[-1])
                    pct = ((last - prev) / prev) * 100
                    if abs(pct) >= 8.0:
                        alerts.append(f"{'🔴' if pct<0 else '🟢'} 🇯🇵 {t} {pct:+.1f}%")
            except Exception:
                continue
        return alerts
    except Exception as e:
        log.error(f"일본: {e}")
        return []


# ── 환율 ─────────────────────────────────────────────
def check_fx():
    try:
        import yfinance as yf
        fx_list = _load(ALERTS_FILE, {}).get("fx_alerts", [])
        alerts = []
        for fa in fx_list:
            pair, thr = fa["pair"], fa["threshold"]
            sym = {"USDJPY": "JPY=X", "USDKRW": "KRW=X"}.get(pair, f"{pair}=X")
            try:
                h = yf.Ticker(sym).history(period="2d")
                if len(h) >= 2:
                    prev, last = float(h["Close"].iloc[-2]), float(h["Close"].iloc[-1])
                    pct = ((last - prev) / prev) * 100
                    if abs(pct) >= thr:
                        alerts.append(f"{'📈' if pct>0 else '📉'} 💱 {pair} {pct:+.2f}%")
            except Exception:
                continue
        return alerts
    except Exception as e:
        log.error(f"환율: {e}")
        return []


# ── 커스텀 종목 ──────────────────────────────────────
def check_stocks():
    try:
        import yfinance as yf
        stocks = _load(ALERTS_FILE, {}).get("stock_alerts", [])
        alerts = []
        for sa in stocks:
            t, thr, mkt = sa["ticker"], sa["threshold"], sa["market"]
            d = sa.get("direction", "both")
            sym = t
            if mkt == "jp" and not t.endswith(".T"):
                sym = f"{t}.T"
            elif mkt == "cn":
                sym = f"{t}.SS" if t.startswith("6") else f"{t}.SZ"
            try:
                h = yf.Ticker(sym).history(period="2d")
                if len(h) >= 2:
                    prev, last = float(h["Close"].iloc[-2]), float(h["Close"].iloc[-1])
                    pct = ((last - prev) / prev) * 100
                    ok = (d == "both" and abs(pct) >= thr) or (d == "up" and pct >= thr) or (d == "down" and pct <= -thr)
                    if ok:
                        flag = {"kr": "🇰🇷", "jp": "🇯🇵", "cn": "🇨🇳", "us": "🇺🇸"}.get(mkt, "")
                        alerts.append(f"{'🟢' if pct>0 else '🔴'} {flag} {sa['ticker']} {pct:+.1f}%")
            except Exception:
                continue
        return alerts
    except Exception as e:
        log.error(f"종목: {e}")
        return []


# ── 커스텀 룰 ────────────────────────────────────────
def run_rules():
    alerts = []
    for f in sorted(RULES_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "check"):
                r = mod.check()
                if r:
                    alerts.extend(r if isinstance(r, list) else [r])
        except Exception as e:
            log.error(f"룰 {f.name}: {e}")
    return alerts


# ── 뉴스 RSS ────────────────────────────────────────
def check_news():
    feeds_f = NEWS_DIR / "feeds.json"
    kw_f = NEWS_DIR / "keywords.json"
    seen_f = NEWS_DIR / "seen.json"
    if not feeds_f.exists() or not kw_f.exists():
        return []
    try:
        import feedparser
        feeds = json.loads(feeds_f.read_text())
        kws = json.loads(kw_f.read_text()).get("alert_keywords", [])
        seen = set(json.loads(seen_f.read_text())) if seen_f.exists() else set()
        if not kws:
            return []
        alerts, new_seen = [], set()
        for fc in feeds.get("feeds", []):
            fm = fc["id"].split("_")[0]
            for url in fc.get("urls", []):
                try:
                    for e in feedparser.parse(url).entries[:15]:
                        nid = hashlib.md5(e.get("link", "").encode()).hexdigest()
                        if nid in seen:
                            continue
                        txt = f"{e.get('title', '')} {e.get('summary', '')}".lower()
                        for kw in kws:
                            if kw["market"] not in ("all", fm):
                                continue
                            if kw["term"].lower() in txt:
                                alerts.append({"kw": kw["term"], "title": e.get("title", ""),
                                               "link": e.get("link", ""), "src": fc.get("name", ""),
                                               "to": kw.get("requester", "all")})
                                new_seen.add(nid)
                                break
                except Exception:
                    continue
        seen.update(new_seen)
        seen_f.write_text(json.dumps(list(seen)[-5000:]))
        return alerts
    except ImportError:
        log.warning("feedparser 미설치")
        return []
    except Exception as e:
        log.error(f"뉴스: {e}")
        return []


# ── 스케줄러 ─────────────────────────────────────────
def market_tick():
    log.info("시장 체크")
    all_a = check_china() + check_japan() + check_fx() + check_stocks() + run_rules()
    if all_a:
        send_tg("🚨 <b>시장 알림</b>\n\n" + "\n".join(all_a))
        log.info(f"{len(all_a)}건 발송")
        (LOG_DIR / f"alert_{datetime.now():%Y%m%d_%H%M}.json").write_text(
            json.dumps(all_a, ensure_ascii=False, indent=2))
    else:
        log.info("이상 없음")


def news_tick():
    log.info("뉴스 체크")
    for a in check_news():
        send_tg(f"📰 <b>{a['src']}</b> | {a['kw']}\n\n{a['title']}\n\n🔗 {a['link']}", a["to"])


def main():
    log.info("데몬 시작")
    sched = BlockingScheduler()
    sched.add_job(market_tick, "interval", minutes=5, id="market", max_instances=1, misfire_grace_time=60)
    sched.add_job(news_tick, "interval", minutes=15, id="news", max_instances=1, misfire_grace_time=120)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: (sched.shutdown(wait=False), sys.exit(0)))

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("종료")


if __name__ == "__main__":
    main()

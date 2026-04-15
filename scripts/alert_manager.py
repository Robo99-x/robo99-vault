#!/usr/bin/env python3
"""
alert_manager.py — 알림 등록/조회/삭제

  python scripts/alert_manager.py add-stock --ticker 6758.T --threshold 8 --market jp
  python scripts/alert_manager.py add-fx --pair USDJPY --threshold 3
  python scripts/alert_manager.py add-news --term "부양책" --market cn
  python scripts/alert_manager.py list
  python scripts/alert_manager.py remove --id <id>
"""

import argparse, json, uuid, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent  # workspace/
ALERTS_FILE = BASE / "monitor" / "alerts.json"
KEYWORDS_FILE = BASE / "monitor" / "news" / "keywords.json"


def _load(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def add_stock(args):
    data = _load(ALERTS_FILE, {"stock_alerts": [], "fx_alerts": []})
    a = {
        "id": uuid.uuid4().hex[:8],
        "ticker": args.ticker,
        "threshold": args.threshold,
        "market": args.market,
        "direction": args.direction,
        "requester": args.requester,
        "created": datetime.now().isoformat(),
    }
    data.setdefault("stock_alerts", []).append(a)
    _save(ALERTS_FILE, data)
    print(f"✅ 종목 알림: {a['ticker']} ±{a['threshold']}% ({a['market']}) [ID: {a['id']}]")


def add_fx(args):
    data = _load(ALERTS_FILE, {"stock_alerts": [], "fx_alerts": []})
    a = {
        "id": uuid.uuid4().hex[:8],
        "pair": args.pair.upper(),
        "threshold": args.threshold,
        "requester": args.requester,
        "created": datetime.now().isoformat(),
    }
    data.setdefault("fx_alerts", []).append(a)
    _save(ALERTS_FILE, data)
    print(f"✅ 환율 알림: {a['pair']} ±{a['threshold']}% [ID: {a['id']}]")


def add_news(args):
    data = _load(KEYWORDS_FILE, {"alert_keywords": []})
    a = {
        "id": uuid.uuid4().hex[:8],
        "term": args.term,
        "market": args.market,
        "requester": args.requester,
        "created": datetime.now().isoformat(),
    }
    data["alert_keywords"].append(a)
    _save(KEYWORDS_FILE, data)
    print(f'✅ 뉴스 키워드: "{a["term"]}" ({a["market"]}) [ID: {a["id"]}]')


def list_all(_args):
    data = _load(ALERTS_FILE, {})
    news = _load(KEYWORDS_FILE, {})

    print("=" * 50)
    print("📊 등록된 알림")
    print("=" * 50)

    for s in data.get("stock_alerts", []):
        d = {"up": "↑", "down": "↓", "both": "↕"}.get(s.get("direction", "both"), "↕")
        print(f"  📈 [{s['id']}] {s['ticker']} {d}{s['threshold']}% ({s['market']})")

    for f in data.get("fx_alerts", []):
        print(f"  💱 [{f['id']}] {f['pair']} ±{f['threshold']}%")

    for k in news.get("alert_keywords", []):
        print(f'  📰 [{k["id"]}] "{k["term"]}" ({k["market"]})')

    total = len(data.get("stock_alerts", [])) + len(data.get("fx_alerts", [])) + len(news.get("alert_keywords", []))
    if total == 0:
        print("  (없음)")
    print()


def remove(args):
    aid = args.id
    for path, keys in [(ALERTS_FILE, ["stock_alerts", "fx_alerts"]),
                        (KEYWORDS_FILE, ["alert_keywords"])]:
        data = _load(path, {})
        for k in keys:
            before = len(data.get(k, []))
            data[k] = [x for x in data.get(k, []) if x["id"] != aid]
            if len(data[k]) < before:
                _save(path, data)
                print(f"🗑️ 삭제: {aid}")
                return
    print(f"❌ 못 찾음: {aid}")
    sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("add-stock")
    s.add_argument("--ticker", required=True)
    s.add_argument("--threshold", type=float, required=True)
    s.add_argument("--market", required=True, choices=["kr", "jp", "cn", "us"])
    s.add_argument("--direction", default="both", choices=["up", "down", "both"])
    s.add_argument("--requester", default="default")
    s.set_defaults(func=add_stock)

    f = sub.add_parser("add-fx")
    f.add_argument("--pair", required=True)
    f.add_argument("--threshold", type=float, required=True)
    f.add_argument("--requester", default="default")
    f.set_defaults(func=add_fx)

    n = sub.add_parser("add-news")
    n.add_argument("--term", required=True)
    n.add_argument("--market", default="all", choices=["all", "kr", "us", "jp", "cn"])
    n.add_argument("--requester", default="default")
    n.set_defaults(func=add_news)

    sub.add_parser("list").set_defaults(func=list_all)

    r = sub.add_parser("remove")
    r.add_argument("--id", required=True)
    r.set_defaults(func=remove)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()

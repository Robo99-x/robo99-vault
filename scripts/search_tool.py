#!/usr/bin/env python3
"""
search_tool.py — SearXNG 통합 검색

  python scripts/search_tool.py "코스피 상승 원인"
  python scripts/search_tool.py --mode news "NVDA earnings"
  python scripts/search_tool.py --lang ja "日経平均 急落"
"""

import argparse, json, os, re
from pathlib import Path
import requests

SEARXNG = os.environ.get("SEARXNG_URL", "http://localhost:8888")
TIMEOUT = 15


def _html_strip(t):
    return re.sub(r"<[^>]+>", "", t).replace("&amp;", "&").replace("&quot;", '"')


def searxng(query, categories="general", lang="en", n=5):
    try:
        r = requests.get(f"{SEARXNG}/search", params={
            "q": query, "format": "json", "categories": categories,
            "language": lang, "pageno": 1,
        }, timeout=TIMEOUT)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", ""), "engine": x.get("engine", "")}
                for x in r.json().get("results", [])[:n]]
    except Exception as e:
        return [{"error": str(e)}]


def _has_ko(t):
    return any("\uac00" <= c <= "\ud7a3" for c in t)

LANG_MAP = {"ko": "ko", "ja": "ja", "zh": "zh", "cn": "zh", "en": "en", "us": "en"}


def smart_search(query, mode="auto", lang="auto", n=5):
    is_ko = lang == "ko" or (lang == "auto" and _has_ko(query))
    cats = "news" if mode == "news" else "general"
    sl = LANG_MAP.get(lang, "ko" if is_ko else "en")

    result = {"query": query, "lang": sl, "sources": []}

    if is_ko:
        result["searxng"] = searxng(query, cats, "ko", 3)
        result["sources"].append("searxng")
    else:
        result["searxng"] = searxng(query, cats, sl, n)
        result["sources"].append("searxng")

    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--mode", default="auto", choices=["auto", "news", "web"])
    p.add_argument("--lang", default="auto")
    p.add_argument("--max", type=int, default=5)
    a = p.parse_args()
    print(json.dumps(smart_search(a.query, a.mode, a.lang, a.max), ensure_ascii=False, indent=2))

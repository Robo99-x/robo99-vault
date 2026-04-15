#!/usr/bin/env python3
"""
update_themes.py — 네이버 테마맵 갱신 (주 1회 권장)
출력: ~/robo99_hq/alerts/cache/theme_map.json
"""
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import requests
from bs4 import BeautifulSoup

from lib import config  # noqa: E402

URL = "https://finance.naver.com/sise/theme.naver"
HEADERS = {"User-Agent": "Mozilla/5.0"}
OUTPUT_PATH = config.ALERTS / "cache" / "theme_map.json"


def get_themes():
    themes = []
    for p in range(1, 8):
        page_url = f"{URL}?&page={p}"
        r = requests.get(page_url, headers=HEADERS, timeout=10)
        s = BeautifulSoup(r.text, "html.parser")
        for a in s.select("td.col_type1 a"):
            th_name = a.text.strip()
            th_link = "https://finance.naver.com" + a["href"]
            themes.append((th_name, th_link))
    return themes


def get_theme_stocks(theme_url):
    res = requests.get(theme_url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    stocks = []
    for a in soup.select("div.name_area > a"):
        if "code=" in a["href"]:
            code = a["href"].split("code=")[1]
            stocks.append(code)
    return stocks


def main():
    themes = get_themes()
    print(f"테마 {len(themes)}개 발견, 종목 매핑 중...")

    ticker_to_themes = {}
    for th_name, th_link in themes:
        codes = get_theme_stocks(th_link)
        for c in codes:
            if c not in ticker_to_themes:
                ticker_to_themes[c] = []
            if len(ticker_to_themes[c]) < 3:
                ticker_to_themes[c].append(th_name)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(ticker_to_themes, f, ensure_ascii=False)

    print(f"테마맵 저장 완료: {len(ticker_to_themes)}종목 ({OUTPUT_PATH})")


if __name__ == "__main__":
    main()

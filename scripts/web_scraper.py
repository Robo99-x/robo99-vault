#!/usr/bin/env python3
import sys
import requests
from bs4 import BeautifulSoup


def main():
    if len(sys.argv) < 2:
        print("Usage: web_scraper.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(2)

    soup = BeautifulSoup(r.text, "lxml")

    # remove scripts/styles
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # try to focus on article content if available
    article = soup.find("article")
    text = article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)

    # basic cleanup: collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    print("\n".join(lines))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""웹페이지 본문 추출. python scripts/fetch_page.py "URL" """

import sys, requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def fetch(url, max_chars=5000):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            t.decompose()
        body = soup.find("article") or soup.find("main") or soup.body
        if not body:
            return "본문 추출 실패"
        text = "\n".join(l.strip() for l in body.get_text("\n", strip=True).splitlines() if l.strip())
        return text[:max_chars] + "\n\n... (생략)" if len(text) > max_chars else text
    except Exception as e:
        return f"로드 실패: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/fetch_page.py <URL>")
        sys.exit(1)
    print(fetch(sys.argv[1]))

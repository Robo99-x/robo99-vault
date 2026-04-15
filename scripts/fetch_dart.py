import requests
from bs4 import BeautifulSoup

url = "https://finance.naver.com/item/main.naver?code=010170"
headers = {"User-Agent": "Mozilla/5.0"}
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, 'html.parser')

print("=== 공시 ===")
for tr in soup.select('.sub_section tr'):
    txt = tr.text.strip().replace('\n', ' ')
    if '상장' in txt or '유상증자' in txt or '증자' in txt:
        print(txt)

print("=== 뉴스 ===")
for ul in soup.select('.news_area ul'):
    print(ul.text.strip())

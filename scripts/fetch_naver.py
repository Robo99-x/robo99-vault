import requests
from bs4 import BeautifulSoup
import re

url = "https://search.naver.com/search.naver?where=news&query=%EB%8C%80%ED%95%9C%EA%B4%91%ED%86%B5%EC%8B%A0+%EC%9C%A0%EC%83%81%EC%A6%9D%EC%9E%90+%EC%8B%A0%EC%A3%BC+%EC%83%81%EC%9E%A5&sm=tab_opt&sort=0&photo=0&field=0&pd=3&ds=2025.01.01&de=2026.03.11&docid=&related=0&mynews=0&office_type=0&office_section_code=0&news_office_checked=&nso=so%3Ar%2Cp%3Afrom20250101to20260311"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, 'html.parser')

for t in soup.select('.news_tit'):
    print(t.text)
    
for d in soup.select('.api_txt_lines.dsc_txt_wrap'):
    print(d.text)
    print("---")

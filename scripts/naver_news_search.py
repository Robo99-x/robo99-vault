import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

query = "대한광통신 유상증자 신주"
url = f"https://search.naver.com/search.naver?where=news&query={urllib.parse.quote(query)}&sm=tab_opt&sort=1&photo=0&field=0&pd=0&ds=&de=&docid=&related=0&mynews=0&office_type=0&office_section_code=0&news_office_checked=&nso=so%3Add%2Cp%3Aall"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read()
    soup = BeautifulSoup(html, 'html.parser')
    titles = soup.select('.news_tit')
    for t in titles:
        print(t.text)
except Exception as e:
    print(e)

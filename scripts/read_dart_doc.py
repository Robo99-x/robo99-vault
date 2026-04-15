import OpenDartReader
import json

API_KEY = "40cc0bcff273ba5d802e8cf68ef8411d8f29bd60"
dart = OpenDartReader(API_KEY)

# 2026-02-23 증권신고서(지분증권)의 첨부문서 또는 본문 파싱 시도 (간단히 URL만 추출)
xml_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260223002571"
print(xml_url)

# 기재정정 주요사항보고서(유상증자결정)
xml_url2 = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260223002079"
print(xml_url2)

# OpenDartReader를 이용한 공시 문서 다운로드 (xml)
xml_text = dart.document('20260223002079')
# 문서 내용 중 "신주의 상장 예정일" 주변 텍스트 출력
import re
lines = xml_text.split('\n')
for i, line in enumerate(lines):
    if '상장 예정일' in line or '신주의 상장' in line or '상장예정일' in line:
        start = max(0, i-2)
        end = min(len(lines), i+3)
        print("--- Match ---")
        print("\n".join(lines[start:end]))

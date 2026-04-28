#!/usr/bin/env python3
"""
텔레그램 overlapping report 전송
ACTIVE watchlist 종목이 geek screening에 나타나는 경우를 보고
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib import telegram

# ACTIVE watchlist와 screening의 겹침
overlap_msg = """🎯 Watchlist × Screening 겹침 보고 (2026-04-28)

**발견된 ACTIVE 종목:**

1️⃣ 009150 삼성전기
   이벤트: MLCC 판가 인상 (다음 촉매: 4월 판가 실제 적용)
   Screening: RS 96.6, Risk 1, 외국인 순매수
   → 단기 주목 시점

2️⃣ 006260 LS
   이벤트: FCC 구리→광섬유 규제 폐지 (다음 촉매: AT&T·Verizon 공사 발주)
   Screening: RS 86.4, Risk 1, 기관 순매수
   → 중기 인프라 모멘텀

📊 추가 확인 필요:
- 씨엠티엑스 (TSMC 2나노)
- 한스바이오메드 (스킨부스터 경쟁)
- 두산 (원자력 테마)
"""

result = telegram.send(overlap_msg, chat_id="1883449676")
if result:
    print("✓ 텔레그램 전송 성공")
    sys.exit(0)
else:
    print("✗ 텔레그램 전송 실패")
    sys.exit(1)

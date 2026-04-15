# 이벤트 카드 워크플로우

## 자동 처리 규칙

형님이 뉴스/공시를 붙여넣으면:
1. `events/YYYY-MM-DD_제목.md` 생성 (10섹션 포맷)
2. 관련 `tickers/종목명.md` 업데이트 (없으면 신규 생성)
3. 관련 `themes/테마명.md` 업데이트 (없으면 신규 생성)
4. `watchlist.md` ACTIVE 섹션에 추가

---

## 이벤트 카드 표준 포맷 (10섹션)

```
# [Event] 제목
- Date: YYYY-MM-DD
- Event Type: 실적/공시/매크로/정책/수급/기타
- Source: 출처
- Tickers: 관련 종목
- Themes: 관련 테마
- Status: ACTIVE/CLOSED

## 1. What Changed
변한 것이 무엇인가 (사실만)

## 2. Surprise vs Expectation
시장 예상 대비 서프라이즈 방향

## 3. Direct Impact
직접 영향 종목/섹터

## 4. Second Order Impact
2차 파급 효과

## 5. Time Horizon
효과 지속 기간 (단기/중기/장기)

## 6. Novelty
새로운 정보인가, 확인인가

## 7. Prior Cases
유사 선례 및 당시 시장 반응

## 8. Invalidators
이 분석이 틀리는 조건

## 9. Confidence
확신도 (High/Medium/Low) + 이유

## 10. Action Relevance
포트폴리오 액션 필요 여부 및 우선순위
```

---
name: trade_research
description: Event-centered trading research assistant for my workflow
user-invocable: true
---

# 스킬의 역할
- 뉴스, 공시, 리포트 PDF, 내 메모를 이벤트 카드로 구조화한다.
- 관련 theme note / ticker note / daily memory를 함께 업데이트한다.
- 중복 뉴스는 병합한다.
- 요약보다 실전 relevance를 우선한다.
- 장마감 복기와 주간 복기를 지원한다.

# 스킬이 지원해야 할 모드
- premarket
- ingest
- pdf
- close_review
- weekly_review

# 각 모드 규칙

## 1. premarket
- 밤사이 이벤트를 중요도별로 정리
- watchlist A/B/C 분류
- 직접/간접 영향
- intraday 체크포인트
- 무효화 조건

## 2. ingest
- 입력된 뉴스/공시/메모를 이벤트 카드화
- 기존 이벤트와 중복 여부 먼저 판단
- 관련 theme / ticker note 업데이트
- intraday relevance 3줄 설명

## 3. pdf
- PDF를 리포트 요약이 아니라 매매 참고자료로 정리
- 새 사실 / 컨센서스와 다른 부분 / 직접수혜 / 간접수혜 / 리스크 / 오해 포인트 분리

## 4. close_review
- 오늘 이벤트 vs 실제 가격반응 비교
- 내 해석 오류를 분류
- 반복 실수를 MEMORY.md에 누적
- 다음 번 대응 플레이북 문장 생성

## 5. weekly_review
- 이번 주 강했던 패턴 / 약했던 패턴
- 자주 틀리는 이벤트 타입
- 다음 주 집중할 3개 패턴만 추려주기

# 모든 출력 형식
- 5줄 이내 실전 요약
- 구조화된 본문
- 업데이트한 파일 목록
- 더 좋은 판단을 위한 후속질문 3개

# Event Card 수동 프로모션 규칙

draft → confirmed 승격 절차.

## 트리거

형님이 명시적으로 아래 중 하나를 요청한 경우에만 실행합니다.
- "이 draft 확정해"
- "이 이벤트 카드 확정해"
- "confirmed 처리해"

자동 승격 없음. 명시적 요청 없으면 draft 상태 유지.

---

## 승격 절차 (7단계)

**1. 대상 draft 파일 확인**
형님이 지정한 draft 파일 Read.
지정 없으면 10_events_drafts/에서 가장 최근 파일 확인 후 형님에게 확인 요청.

**2. YAML 스키마 오류 수정**
- needs_review: true → false 로 변경 예정
- possible_duplicate_of 필드 확인 (중복 의심 시 형님에게 보고)
- 필수 필드 누락 여부 확인: date, source_file, entities, catalyst_type

**3. 본문 품질 확인**
- 확인된 사실 섹션: 원문 근거 없는 추론 포함 여부 점검
- 사건 / 해석 / 확인할 것 구분 유지 여부 확인
- 문제 발견 시 수정 후 진행 (또는 형님에게 보고 후 판단)

**4. needs_review → false 변경**

**5. status 결정**
- watch: 모니터링 필요하나 당장 액션 없음 (기본값)
- new: 새로운 중요 이벤트로 즉시 검토 필요

**6. 파일 이동**
draft 파일을 10_events_drafts/ → 10_events/YYYY/MM/DD/ 로 이동.
파일명에서 `.draft` 제거: `2026-04-29-삼성전기-MLCC.md`

```bash
mkdir -p ~/robo99_hq/10_events/YYYY/MM/DD
# 이동 후 원본 삭제 (trash 사용)
```

**7. raw 파일 표시**
원본 00_inbox raw 파일의 frontmatter에 아래 추가:
```yaml
processed: true
event_card_created: true
event_card_path: "10_events/YYYY/MM/DD/파일명.md"
```

---

## 이번 단계에서 하지 않는 것

- tickers/ 업데이트
- themes/ 업데이트
- views/ 업데이트
- active 종목 선정
- 기존 이벤트 자동 병합

→ 위 항목은 다음 단계에서 별도 구현 예정.

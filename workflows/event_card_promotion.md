# Event Card Gate 1 — 수동 Confirm 절차

draft → confirmed 승격. 파일 이동 없음. frontmatter 업데이트만.

## 트리거

형님이 명시적으로 아래 중 하나를 요청한 경우에만 실행:
- "이 draft 확정해"
- "이 이벤트 카드 확정해"
- "confirmed 처리해"

## 승격 절차

**1. 대상 파일 확인**
형님이 지정한 파일 Read.
미지정 시 20_wiki/events/에서 status:draft 중 가장 최근 파일 확인 후 형님에게 확인 요청.

**2. schema_version 확인**
schema_version: 1 이 아니면 처리 중단.

**3. Preflight 확인**
- source_file 존재 및 실제 파일 있음
- risk_hypothesis 비어있지 않음
- invalidates_if 비어있지 않음 (확정 단계에서는 필수)

invalidates_if 비어있으면 → 형님에게 "invalidates_if를 작성해주세요" 요청 후 중단.

**4. 내용 검토 (형님)**
- 확인된 사실 섹션: 원문 근거 없는 추론 포함 여부
- risk_hypothesis가 실질적으로 작성됐는지 (형식 채우기 수준 여부)

**5. frontmatter 업데이트**
```yaml
status: confirmed
```

**6. log.md append**
```
## [YYYY-MM-DDTHH:MM KST] CONFIRM {파일명} → confirmed
```

**7. 완료 보고**
```
Gate 1 완료: status: confirmed

파일: 20_wiki/events/YYYY/MM/DD/파일명.md
다음 단계:
  "이 이벤트 [종목]에 반영해" → Gate 2 (integrated)
  "이 이벤트 thesis 무관" → skipped + skip_reason 필요
```

---

# Event Card Gate 2 — Thesis 편입 또는 Skip

confirmed → integrated 또는 skipped.

## 트리거

- "이 이벤트 [종목]에 반영해" → integrated
- "이 이벤트 thesis 무관" / "skip해" → skipped

## integrated 절차

**1. 대상 파일 확인**
status: confirmed인 파일 Read.

**2. 20_wiki/tickers/{종목코드}.md 읽기**
해당 종목의 Working Thesis 확인.

**3. 이벤트를 ticker 파일에 반영**
tickers 파일에 이벤트 요약 + 날짜 + 링크 추가.
(thesis 변경 여부는 형님 판단)

**4. frontmatter 업데이트**
```yaml
status: integrated
integration_notes: "20_wiki/tickers/005930.md에 반영 완료"
```

**5. log.md append**
```
## [YYYY-MM-DDTHH:MM KST] INTEGRATE {파일명} → integrated / 20_wiki/tickers/005930.md 반영
```

## skipped 절차

**1. skip_reason 필수**
형님에게 "왜 thesis 무관인지" 1줄 요청.

**2. frontmatter 업데이트**
```yaml
status: skipped
skip_reason: "형님이 제공한 이유"
```

**3. log.md append**
```
## [YYYY-MM-DDTHH:MM KST] SKIP {파일명} → skipped / {skip_reason}
```

---

# 이 단계에서 하지 않는 것

- tickers/themes/views 자동 일괄 수정
- confirmed 자동화
- legacy archive 수정
- 기존 events/ 파일 수정

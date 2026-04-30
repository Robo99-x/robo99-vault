# CIO Context Pack 생성 워크플로우

CIO 모드 활성화 시 브리핑 시작 전에 이 워크플로우를 실행한다.

## 생성 조건

- CIO 모드 트리거 시마다 실행
- 단일 종목 리서치 → ticker-based pack
- 복수 종목 / 포트폴리오 / 매크로 질문 → session-based pack

## 파일 경로

- 단일 종목: `30_ops/cio_context/{ticker}_{YYYYMMDDTHHMMSS}.md`
- 세션:      `30_ops/cio_context/{YYYYMMDDTHHMMSS}_cio_session.md`

타임스탬프는 KST 기준. 파일명에는 콜론(:) 사용 금지 — `T` 구분자 + `HHMMSS` 형식.

## 포함 내용 (단일 종목 기준)

### 1. Ticker Wiki 페이지

- 우선순위: `20_wiki/tickers/{종목코드}.md` → `tickers/{파일명}` (legacy fallback)
- 둘 다 없으면: `"No wiki page found for {ticker}"` 로 표기
- legacy 사용 시 헤더에 `(legacy fallback)` 명시

### 2. 최근 이벤트 (MATERIAL: YES — confirmed/integrated only)

- 우선순위: `20_wiki/events/` 에서 `status: confirmed` 또는 `status: integrated` + frontmatter `entities` 에 해당 종목 포함
- 없으면: `events/` 레거시에서 종목명/코드로 검색
- 최대 5건, 최신순 (frontmatter `date` 또는 파일 mtime 기준)

### 3. Draft 이벤트 (MATERIAL: NO)

- `20_wiki/events/` 에서 `status: draft` + 해당 종목 포함
- 최대 3건
- 헤더에 `"⚠️ MATERIAL: NO — 미확정 draft, 판단 근거로 사용 불가"` 명시

### 4. 관련 Reviews

- `reviews/` 에서 파일명 또는 frontmatter `tickers` 에 해당 종목코드 포함
- 최대 3건, 최신순
- 결론(frontmatter `conclusion`) 1줄 요약 포함

### 5. 관련 Themes

- `20_wiki/themes/` → `themes/` (fallback) 에서 해당 종목 관련 파일
- 최대 2건

## 세션 모드 (복수 종목 / 매크로)

- 위 5개 섹션을 각 종목별 sub-section으로 반복
- 매크로 전용일 경우: Ticker Wiki / Events 섹션은 생략하고 Themes + Reviews만 수집

## Context Pack 포맷

```markdown
---
generated_at: YYYY-MM-DDTHH:MM KST
ticker: {종목코드}
type: ticker_session | multi_session | macro_session
material_events: {confirmed/integrated 이벤트 수}
draft_events: {draft 이벤트 수}
---

# CIO Context: {종목명} ({종목코드})

## Ticker Wiki
{ticker 파일 내용 전문 또는 "No wiki page found"}

## 확정 이벤트 (MATERIAL: YES)
{최근 confirmed/integrated 이벤트 요약 목록 — 파일경로 + 1줄 요약}

## 미확정 Draft (MATERIAL: NO)
⚠️ 아래 내용은 미확정 draft입니다. CIO 판단 근거로 사용 불가. 참고만.
{draft 이벤트 요약 목록}

## 관련 Reviews
{최근 CIO 리뷰 파일 링크 및 결론 요약}

## 관련 Themes
{관련 테마 요약}
```

## log.md append

context pack 생성 후 반드시 `~/robo99_hq/log.md` 에 append:

```
## [YYYY-MM-DDTHH:MM KST] CIO_SESSION {pack 파일명} / ticker:{종목코드}
```

세션 모드인 경우 `ticker:` 대신 `tickers:{코드1,코드2,...}` 또는 `scope:macro` 사용.

## 사용 규칙 (CIO 측)

1. 생성된 context pack을 Read 한 뒤 분석 시작
2. **MATERIAL: YES 이벤트만** CIO Score 계산 근거로 사용
3. **MATERIAL: NO draft**는 참고만 허용, 판단 근거로 사용 금지
4. context pack 없이 브리핑 시작 금지 (legacy만 있어도 pack 생성 필수)

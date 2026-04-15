# tickers/.state/

이 폴더는 **entity_syncer.py** 가 자동으로 채우고 갱신하는 *종목 상태 yaml 파일* 들이 보관되는 곳이다.

## 규칙

1. **사람이 직접 편집하지 말 것**. entity_syncer가 매일 launchd로 깨어나 갱신한다.
2. 사람이 작성하는 종목 *분석 노트* 는 부모 폴더 `tickers/<코드>-<이름>.md` 에 둔다.
3. 옵시디언 dataview 가 두 파일(사람의 .md + 기계의 .yaml)을 한 화면에 합쳐서 보여준다.

## 분리 이유 — git 충돌 방지

같은 노트 안에 사람과 기계가 같이 쓰면 git 머지 충돌이 매일 난다.
파일 단위로 영역을 분리하면 같은 종목에 대해 사람·데몬이 동시에 작업해도 git이 자동 머지한다.

## 스키마 (`<코드>-<이름>.yaml`)

```yaml
ticker: "005930"
name: 삼성전자
status: monitoring        # monitoring | entered | hold | retired | dormant
status_since: 2026-04-08
thesis: ""                # 사람이 결재 시 채움 (CIO write-back)
themes: [HBM-공급부족, 파운드리-회복]
catalysts_pending: []     # 예: [2026-04-25 1Q실적]
invalidation: ""          # CIO 결재 시 채움
last_seen: 2026-04-08     # 마지막으로 어떤 산출물에 등장한 날짜
last_briefed: 2026-04-08  # 마지막으로 premarket 브리핑에 포함된 날짜
last_review: 2026-04-08
next_review: 2026-04-15
appearances:              # 어디에 등장했는지 백링크 (entity_syncer가 채움)
  - {date: 2026-04-08, kind: theme_briefing, ref: alerts/theme_briefing_2026-04-08.md}
  - {date: 2026-04-08, kind: cio_review, ref: reviews/2026-04-08_005930_000660_CIO.md}
```

## 상태 전이 규칙 (entity_syncer가 적용)

- `monitoring` → `dormant`: 30일+ 어떤 산출물에도 등장하지 않음
- `entered` → `hold`: CIO가 hold 결재
- `*` → `retired`: invalidation 조건 충족 또는 CIO 결재
- `dormant` → `monitoring`: 새 산출물에 다시 등장

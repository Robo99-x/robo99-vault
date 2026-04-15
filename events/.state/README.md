# events/.state/

이 폴더는 **entity_syncer.py** 가 자동으로 갱신하는 *이벤트 생애주기 yaml 파일* 들이다.

## 규칙

1. **사람이 직접 편집하지 말 것**.
2. 사람이 작성하는 이벤트 *분석 본문* 은 부모 폴더 `events/YYYY-MM-DD_이름.md` 에 두며, 그 파일의 frontmatter는 *생성 시점의 정적 메타데이터* 만 담는다 (date, event_type, tickers, themes 등).
3. 시간에 따라 변하는 동적 상태(phase, last_reviewed 등)는 이 .state/ 의 yaml 에 둔다.

## 분리 이유

이벤트 본문(`events/<날짜>_*.md`)은 사람이 1회 작성하고 거의 안 건드리는 *불변 분석*. phase 같은 동적 필드는 entity_syncer가 매일 갱신.
같은 파일에 두면 매일 git diff에 본문 전체가 lock 걸린 것처럼 보여서 사람의 작업이 묻힌다.

## 스키마 (`<날짜>_<이름>.yaml`)

```yaml
event_id: 2026-03-17_Murata_MLCC_Price_Hike
event_date: 2026-03-17
phase: active             # active | fading | resolved | invalidated
expires_on: 2026-09-17    # event_date + Time Horizon (또는 default 180일)
last_reviewed: 2026-04-08
last_catalyst: 2026-04-03 # 본문 또는 후속 산출물에서 발견된 마지막 관련 사건
linked_tickers_seen:      # entity_syncer가 매일 산출물에서 이 이벤트의 종목들을 봤는지 추적
  - {ticker: 삼성전기, last_seen: 2026-04-08}
  - {ticker: 삼화콘덴서, last_seen: 2026-04-06}
notes: ""
```

## phase 자동 전이 규칙

- `active` → `fading`: `last_catalyst` 이후 30일 경과 + 이 이벤트의 어느 ticker도 14일+ 산출물에 등장하지 않음
- `fading` → `resolved`: `expires_on < today`
- `*` → `invalidated`: 본문 invalidators 섹션의 트리거가 충족된 경우 (사람 또는 LLM이 명시적으로 표시)
- `resolved`/`invalidated` 이벤트는 매일 brief 생성 시 *제외* 된다 (사용자가 호소했던 "오래된 뉴스 반복" 의 차단)

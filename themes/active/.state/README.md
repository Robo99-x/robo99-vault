# themes/active/.state/

활성 시장 테마(예: MLCC, CPO, SMR, 관세-실물자산 등)의 *동적 상태* yaml 보관소.

`themes/principles/` 의 16개 버핏 챕터는 *영구 지식*이라 .state 가 없다.

## 스키마 (`<테마이름>.yaml`)

```yaml
theme: MLCC
phase: active             # emerging | active | fading | resolved
first_seen: 2025-11-12
peak: 2026-02-20
last_catalyst: 2026-04-03
expires_if: "은 가격 -15% 또는 SK하이닉스 capa 증설 발표"
related_tickers: [삼성전기, 삼화콘덴서, 아모텍, 대주전자재료]
related_events:
  - 2026-03-17_Murata_MLCC_Price_Hike
appearance_count_30d: 8   # 지난 30일간 산출물에 몇 번 등장했는지
```

## 자동 전이

- `emerging` → `active`: 7일 내 3회 이상 산출물 등장
- `active` → `fading`: 14일간 산출물 등장 0회
- `fading` → `resolved`: 30일 + invalidator 충족

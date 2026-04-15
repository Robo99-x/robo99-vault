# Dataview 쿼리 모음

> Obsidian에서 Dataview 플러그인 설치 후 사용 가능.
> 각 코드 블록을 ```dataview 로 감싸면 동적 테이블로 렌더링됨.

---

## 1. 전체 워치리스트 (conviction 순)

```dataview
TABLE sector, conviction, last_notable, status
FROM "tickers"
WHERE file.name != "_TEMPLATE"
SORT conviction DESC
```

---

## 2. 최근 특징주 (Notable Days 기준)

```dataview
TABLE last_notable, sector, tags
FROM "tickers"
WHERE last_notable != "" AND file.name != "_TEMPLATE"
SORT last_notable DESC
LIMIT 20
```

---

## 3. 섹터별 종목 분류

```dataview
TABLE file.link AS 종목, conviction, last_notable
FROM "tickers"
WHERE file.name != "_TEMPLATE"
GROUP BY sector
```

---

## 4. ACTIVE 이벤트 카드

```dataview
TABLE date, tickers, themes
FROM "events"
WHERE status = "ACTIVE" AND file.name != "_TEMPLATE"
SORT date DESC
```

---

## 5. AI 분석 히스토리

```dataview
TABLE date, tickers, agents, conclusion
FROM "reviews"
WHERE file.name != "_TEMPLATE"
SORT date DESC
LIMIT 30
```

---

## 6. 테마별 연결 종목

```dataview
TABLE file.inlinks AS 연결종목
FROM "themes"
WHERE file.name != "_TEMPLATE"
```

---

## 7. 이번 주 이벤트

```dataview
TABLE date, tickers, themes
FROM "events"
WHERE date >= date(today) - dur(7 days)
SORT date DESC
```

---
name: market-search
description: 한미일중 증시 뉴스 및 시장 정보 검색
user-invocable: true
---

# 시장 뉴스/정보 검색

시장 뉴스, "왜 올랐어/내렸어" 류의 질문에 사용.

## 검색
```bash
cd scripts

# 자동 라우팅
uv run python search_tool.py "코스피 상승 원인"

# 뉴스 전용
uv run python search_tool.py --mode news "NVDA earnings"

# 언어 강제
uv run python search_tool.py --lang ja "日経平均 急落"
```

## 페이지 본문
```bash
cd scripts && uv run python fetch_page.py "https://example.com/article"
```

## 시나리오

| 질문 | 검색 |
|------|------|
| 코스피 왜 올랐어? | `search_tool.py "코스피 상승 원인"` |
| 일본 증시 뉴스 | `search_tool.py --mode news --lang ja "日経平均"` |
| NVDA 실적? | `search_tool.py --mode news "NVDA earnings results"` |
| 중국 부양책? | `search_tool.py --mode news "中国 刺激策"` |

## 답변 규칙

0. 상위 검색 결과 2~3개는 항상 fetch_page.py로 본문 내용 파악
1. 검색 결과를 **한국어로 요약**
2. 출처 URL 1~2개 첨부
3. 숫자(지수, 등락률) 반드시 포함
4. "시장 영향" 한 줄 추가

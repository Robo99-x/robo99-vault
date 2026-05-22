---
purpose: 모든 작업 세션 목록 (날짜 내림차순)
---

# 📔 작업 일지 INDEX

> 휴식 후 복귀 시 [`PROGRESS.md`](../PROGRESS.md) 먼저 보고, 세부 컨텍스트가 필요하면 여기로.

---

## 2026

### 5월
- **[2026-05-22 — 워크플로우 리뷰 + 채널 멘션 자동화 + 일일 요약 진단](2026/05/2026-05-22_워크플로우-리뷰-와-채널-멘션-자동화.md)**
  - 시스템 전체 워크플로우 리뷰, 문제점 5가지 진단
  - watchlist .state 15개 시드 (UNRESOLVED_ALIAS 해소)
  - theme_screener 0건 시 Claude 스킵 (타임아웃 낭비 제거)
  - 수급 특징주 섹션 (entity_syncer 포맷 변경)
  - **compile_channel_mentions.py 신규** — Karpathy 방식 raw→wiki backlink
  - 채널 수집 시스템 audit + 수동 일일 요약 Telegram 발송 (5/22 14건)

---

## 작성 규칙

- 파일명: `YYYY-MM-DD_제목-짧게.md`
- 한 세션 = 한 파일 (긴 세션은 분할 가능)
- frontmatter 필수: `date`, `title`, `tags`, `status`
- 세션 끝나면 INDEX.md에 한 줄 추가 + 핵심 bullet 2~4개

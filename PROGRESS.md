---
last_updated: 2026-05-22
maintainer: 로보99 + 형님
purpose: 휴식 후 복귀 시 이 파일 하나로 전체 컨텍스트 회복
---

# 🐭 robo99_hq — Progress Dashboard

> **이 파일만 보면 "어디까지 했고 다음에 뭐 하면 되는지" 다 보인다.**
> 세부 작업 일지는 [`50_journal/`](50_journal/INDEX.md) 참고.

---

## 🎯 원래 목표 (왜 이걸 만들었나)

형님의 **투자 의사결정을 보조하는 2계층 AI 시스템** 구축.

1. **Commander (1층):** 일상·시스템 운영·라우팅
2. **CIO (2층):** 투자 판단 — 트리거 스코어 ≥6에서만 활성화
   - 옵티머스 (드러켄밀러: 거시·모멘텀)
   - Geek (퀀트: 리스크·수급)
   - 오라클 (버핏: 해자·펀더멘털)

**핵심 가치:**
- 매일 자동 데이터 수집·스크리닝·브리핑 → Telegram
- 뉴스/공시 ingest → Event Card 워크플로우 (Gate 1/2)
- 종목별 wiki가 living document — 모든 raw 데이터가 한 곳으로 수렴
- 형님이 잊어버려도 시스템이 기억함

---

## 🗺️ 전체 워크플로우 (한 페이지 요약)

### 데이터 흐름
```
[외부 소스]
  ├─ Telegram 메시지 (형님이 붙여넣음)
  ├─ 텔레그램 채널 (meritz_tech, cahier_de_market — 자동 수집)
  ├─ KRX 시장 데이터 (pykrx + FinanceDataReader)
  └─ 미장 데이터 (yfinance)

       ↓

[Raw Layer] 00_inbox/, 40_consensus/raw/, alerts/*.json

       ↓ (LLM compile)

[Wiki Layer] 20_wiki/{events,tickers,themes,views}/  ← 형님이 읽는 곳
            + tickers/*.md (legacy, 실제 사용 중)

       ↓ (CIO 분석)

[Output] reviews/YYYY-MM-DD_*_CIO.md + Telegram 브리핑
```

### 스케줄 (KST, scheduler_daemon.py)
| 시간 | 작업 | 결과물 |
|------|------|--------|
| 07:02 (화-토) | 미장 마감 리포트 | `alerts/report_YYYYMMDD.md` |
| 08:00 (월-금) | 프리마켓 브리핑 | `alerts/premarket_briefing_YYYY-MM-DD.md` |
| 09:20 (월-금) | 오전 스크리닝 (rs/stage2/geek) | `alerts/stage2_geek_filtered.json` |
| 14:00 (월-금) | 장중 스크리닝 (stage2/geek) | (위 파일 재생성) |
| 15:40 (월-금) | 테마 스크리너 + 그룹핑 | `alerts/theme_briefing_YYYY-MM-DD.md` |
| 23:00 (매일) | 시스템 자가 점검 | Telegram 요약 |
| 23:10 (매일) | git vault push | (원격 백업) |
| 토 08:00 | 주간 hit-rate / 레짐 업그레이드 | (히트율 분석) |

### 2게이트 워크플로우 (이벤트 처리)
```
Raw 입력 → 00_inbox/  (불변, 원본 보존)
   ↓ /event-card-draft
Draft 생성 → 20_wiki/events/.../draft.md  (status: draft)
   ↓ 형님 "확정해"
Gate 1 통과 → status: confirmed  (사실 확인 끝)
   ↓ 형님 "thesis에 편입해" / "skip"
Gate 2 통과 → status: integrated  (ticker/theme 파일 업데이트)
              또는 skipped (skip_reason 기록)
```

---

## ✅ 완료한 것 (크게)

### 인프라 기반 (이전 세션들)
- [x] scheduler_daemon.py + APScheduler 기반 단일 데몬
- [x] vault_writer.py — schema 검증 → atomic write → Telegram
- [x] 4레이어 디렉토리 구조 (`00_inbox/`, `20_wiki/`, `30_ops/`, `40_consensus/`)
- [x] CIO 모드 + Optimus/Geek 에이전트
- [x] entity_syncer — theme_briefing → ticker .state 동기화
- [x] 2게이트 워크플로우 (INGEST/DRAFT/CONFIRM/INTEGRATE 로그)
- [x] 채널 자동 수집 (consensus_monitor — meritz_tech, cahier_de_market)
- [x] 주간 Exit Review (월요일 자동 실행)

### 2026-05-22 세션 (워크플로우 리뷰 + 정합성 보강)
- [x] 워크플로우 전체 리뷰 + 문제점 5가지 진단
- [x] watchlist `.state` 시드 15개 (UNRESOLVED_ALIAS 15→0)
- [x] theme_screener 0건 시 Claude 호출 스킵 (타임아웃 낭비 제거)
- [x] `## 수급 특징주` 섹션 — 테마 스크리너 날짜별 한 줄 누적
- [x] **`compile_channel_mentions.py`** — Karpathy 방식 raw→wiki backlink 첫 단계
- [x] **PROGRESS.md + 50_journal/** — 진행 추적 시스템 (지금 보고 있는 파일)
- [x] 채널 수집 시스템 audit — 2채널 66건 raw 정상, 그러나 digest 발송 안 됨 확인
- [x] **수동 채널 일일 요약 → Telegram 발송 (14건 분석, 5/22)** — 자동화 방향 검증

---

## 🔄 진행 중

없음 (다음 작업 대기 상태).

---

## 📋 다음 할 일 (우선순위순)

### P1 — 작고 즉시 가치 있음
- [ ] **`consensus_digest.py` LLM 교체 + Telegram 발송** (오늘 수동으로 한 요약을 매일 18:00 자동화)
- [ ] 누락된 종목 .md 생성: 삼성전자(9건 멘션), 샘씨엔에스(252990), 덕산네오룩스, 이녹스첨단소재
- [ ] `compile_channel_mentions.py` 스케줄러 통합 (매일 23:30)
- [ ] **채널 확장** — `consensus_monitor.py` CHANNELS dict에 추가 채널 등록 (현재 monitor 데몬은 더 많은 채널 활동 감지 중)

### P2 — 중간 규모
- [ ] **컨센서스/이벤트 변화 추적** — 종목별 의견 시계열, 다중 채널 동시 언급 spike detection
- [ ] LLM 기반 `compile_overview.py` — 채널 멘션을 합성해서 `## 기업개요` 자동 생성
- [ ] Oracle 에이전트 트리거 조건 명시화 (CLAUDE.md 라우팅 테이블)
- [ ] `stage2_geek_filtered.json` 날짜별 아카이브 (히스토리 보존)
- [ ] raw 파일 `processed: false` 마커 활용 (digest 후 true 전환, 중복 처리 방지)

### P3 — 장기 구조 개선
- [ ] `20_wiki/tickers/` 마이그레이션 (현재 `tickers/`가 실 사용)
- [ ] 양방향 backlink — raw 파일에 "이 글이 언급한 종목" 인덱스
- [ ] `20_wiki/tickers/INDEX.md` Karpathy 스타일 인덱스 자동 유지
- [ ] CIO reviews → 종목 thesis/conviction 자동 누적

---

## 🚨 알려진 이슈

- 일부 종목 .md 파일이 `tickers/`에 없음 (예: 삼성전자) — 매뉴얼 생성 필요
- CIO reviews/ 파일 누적 부족으로 entity_syncer가 thesis/conviction 필드 못 채움
- 23:00 시스템 자가 점검이 가끔 600초 타임아웃 (Claude CLI 오버헤드)
- vault push가 가끔 Telegram API timeout (network)

---

## 🔗 최근 세션 로그

- [2026-05-22 — 워크플로우 리뷰 + 채널 멘션 자동화](50_journal/2026/05/2026-05-22_워크플로우-리뷰-와-채널-멘션-자동화.md)

[전체 세션 목록 →](50_journal/INDEX.md)

---

## 📁 주요 디렉토리 빠른 참조

| 경로 | 용도 |
|------|------|
| `~/robo99_hq/agents/` | Commander, CIO, Optimus, Geek, Oracle 페르소나 정의 |
| `~/robo99_hq/scripts/` | scheduler_daemon, entity_syncer, screener 등 |
| `~/robo99_hq/workflows/` | event_card, cio_brief 등 워크플로우 명세 |
| `~/robo99_hq/00_inbox/` | Raw 원본 (불변) |
| `~/robo99_hq/20_wiki/` | Canonical wiki (events/tickers/themes/views) |
| `~/robo99_hq/30_ops/` | 운영 기록 (cio_context, retrospectives) |
| `~/robo99_hq/40_consensus/` | 채널 자동 수집 (meritz_tech 등) |
| `~/robo99_hq/50_journal/` | 작업 일지 (이 파일이 가리키는 곳) |
| `~/robo99_hq/tickers/` | Legacy 종목 .md (실 사용 중, 점진 마이그레이션 예정) |
| `~/robo99_hq/reviews/` | CIO 분석 리포트 |
| `~/robo99_hq/alerts/` | 일별 스크리너 출력, 브리핑 |
| `~/robo99_hq/log.md` | 시스템 이벤트 append-only 로그 |
| `~/CLAUDE.md` | 로보99 정체성 + 라우팅 규칙 + 워크플로우 |

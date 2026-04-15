# robo99_hq — 아키텍처 리뷰 요청 (2026-04-08)

## TL;DR

개인 투자용 멀티에이전트 시스템(`robo99_hq`)이 어느 정도 돌아가고 있지만,
**"어제와 똑같은 장전 브리핑이 매일 온다"** 는 증상을 추적해보니 근본 원인이
**엔티티 동기화 계층의 부재** 였습니다. 세 개의 데이터 흐름(자동화 스크립트 /
사람이 작성한 이벤트 노트 / 에이전트 리뷰)이 `tickers/` 라는 엔티티에 수렴하지
않고 각자 다른 폴더에 쌓여왔습니다.

이번 주에 아래 구조 변경을 진행 중이고, 1차 구현(entity_syncer + prompt 패치)
까지 마쳤습니다. **설계 방향 · 데이터 모델 · 운영 리스크** 세 축에서 피드백을
받고 싶습니다.

---

## 1. 시스템 개요

### 1.1 목적
- 한국/미국 주식 투자 의사결정을 보조하는 개인용 지식베이스 + 자동화
- Obsidian 볼트의 `[[wikilink]]` 신경망을 장기 기억으로 삼고, 스크립트/에이전트가
  여기에 쓰고 읽는다

### 1.2 실행 환경
- **Mac mini** (24/7): 백엔드, 스크립트, 스케줄러 데몬
- **Windows PC** (장중 사용): Obsidian 볼트 편집, 대시보드 열람
- 두 머신 동기화: **git + GitHub private repo** (`Robo99-x/robo99-vault`, Obsidian Git 플러그인)

### 1.3 에이전트 계층
```
Commander (1차 라우팅)
 ├─ Commander Staff (architect / developer / validator / ops-designer / dashboard)
 └─ Investment HQ
      └─ CIO
           ├─ Optimus  (fundamentals)
           ├─ Geek     (technical / screener)
           └─ Oracle   (macro / theme)
```
- 투자 쿼리: 트리거 스코어 ≥6 → Investment HQ
- 개발 쿼리: 복잡도 HIGH → Commander Staff
- LLM 호출은 **Claude CLI** (`run_claude(prompt, task_name)`) 래퍼로 스크립트에서 투입

### 1.4 자동화 루프 (스케줄러 데몬, `launchd`→`nohup` 로 구동)
| 시각(KST) | 작업 | 산출물 |
|---|---|---|
| 07:02 화~토 | 미장 마감 리포트 | `alerts/report_*.md` |
| 08:30 평일 | **장전 브리핑** | Telegram + `alerts/premarket_briefing_*.md` |
| 09:20 평일 | 장초반 스크리닝(RS/Stage2/Geek/VCP) | `alerts/*.json` + Telegram |
| 14:00 평일 | 장중 스크리닝 재실행 | 동상 |
| 15:40 평일 | **장마감 특징주 테마별 분류** | Telegram + `alerts/theme_briefing_*.md` |
| 23:00 매일 | 시스템 자가 점검(로그 분석 + watchlist sync) | `alerts/watchlist_sync.json` |

---

## 2. 드러난 문제

### 2.1 증상
1. 매일 아침 08:30 장전 브리핑 내용이 **전일과 거의 동일** (같은 watchlist,
   같은 A/B/C 분류, 오버나잇 뉴스만 미묘하게 다름)
2. 한 번 식별된 특징주/이벤트가 며칠 뒤 **중복 재분석**
3. Obsidian 에서 `[[삼성전자]]` 눌러도 해당 종목의 과거 기록 궤적이 **연결되지 않음**
   (`tickers/` 폴더가 거의 비어 있음)

### 2.2 진단 (루트 코즈)
데이터 흐름이 세 갈래로 쌓이는데 **엔티티에 수렴시키는 주체가 없음**:

```
Flow A — 자동화 스크립트
  theme_volume_screener.py → alerts/theme_screener.json
  stage2_scanner.py        → alerts/stage2_*.json
  rs_ranking.py            → alerts/rs_*.json

Flow B — 사람 작성 (Obsidian 편집)
  events/*.md              (사건 카드)
  themes/active/*.md       (테마 노트)
  watchlist.md             (실수 관리)

Flow C — 에이전트 산출물
  reviews/YYYY-MM-DD_*_CIO.md   (CIO 검토 결과)
  alerts/premarket_briefing_*.md
  alerts/theme_briefing_*.md

→ tickers/  : 거의 비어 있음 (수렴 지점 부재)
```

특히 `job_premarket()` 의 prompt 가 **`watchlist.md` + 당일 스크리너 JSON 만 읽고
매번 처음부터 재분류** 하기 때문에, 전날 자신이 뭐라고 말했는지 **구조적으로 알지
못함**. "어제와 같은 내용" 은 버그가 아니라 설계 결과물이었음.

### 2.3 병렬 문제 — git remote 오염
기존 `.git` 이 `juliuschun/eco-moat-ai.git` 을 origin 으로 물고 있었고, 80+개 파일이
deleted 로 스테이징된 상태. 첫 push 전에 발견해 다행이지만, 재초기화 필요.

---

## 3. 설계 원칙 (이번 라운드에 채택)

### 3.1 "Claude 에게 시키지 말고, Claude 가 시킬 것"
- 데이터 수집/집계/상태 전이는 **결정적(deterministic) 스크립트**
- LLM 은 **판단/서술** 구간에서만 호출
- 에스컬레이션 게이트:
  ```
  shouldAskClaude(event):
    if ruleEngine.canHandle(event): return false
    if responseCache.has(hash(event.symptoms)): return false
    if recentEscalations.has(event.type): return false
    return true
  ```
  → `entity_syncer.py` 는 이 원칙에 따라 PyYAML + 정규식만으로 작성, LLM 호출 0.

### 3.2 "사람 영역 vs 기계 영역" 파일 분리
git 충돌을 구조적으로 없애기 위해 각 도메인 폴더를 두 층으로 나눔:

| 영역 | 포맷 | 누가 쓰는가 |
|---|---|---|
| `tickers/삼성전자.md` (사람 영역) | Markdown + [[wikilink]] | Obsidian 에서 사람이 편집 |
| `tickers/.state/005930-삼성전자.yaml` (기계 영역) | YAML frontmatter | `entity_syncer.py` 만 쓴다 |

같은 문법으로 `events/.state/*.yaml`, `themes/active/.state/*.yaml` 도 운영.
git 관점에서는 다른 파일이므로 merge conflict 가 원천 차단됨.

### 3.3 3-엔티티 데이터 모델 + phase 라이프사이클
```yaml
# tickers/.state/005930-삼성전자.yaml
ticker: "005930"
name: 삼성전자
status: monitoring        # monitoring | entered | hold | retired | dormant
status_since: 2026-04-08
thesis: ""                # CIO write-back
themes: [HBM-공급부족]
catalysts_pending: []
invalidation: ""
last_seen: 2026-04-08
last_briefed: 2026-04-08
next_review: 2026-04-15
appearances:
  - {date: 2026-04-08, kind: screener, ref: alerts/theme_screener.json}
  - {date: 2026-04-08, kind: cio_review, ref: reviews/2026-04-08_005930_CIO.md}
```

```yaml
# events/.state/2026-03-17_Murata_MLCC_Price_Hike.yaml
event_id: 2026-03-17_Murata_MLCC_Price_Hike
event_date: 2026-03-17
phase: active             # active | fading | resolved | invalidated
expires_on: 2026-09-17
last_reviewed: 2026-04-08
last_catalyst: 2026-04-03
linked_tickers_seen:
  - {ticker: 삼성전기, last_seen: 2026-04-07}
```

**phase 자동 전이 규칙** (스크립트가 집행):
- `active → fading`: 마지막 카탈리스트 후 30일 경과 AND 연결 종목들의 `last_seen` 이 전부 14일 이상 오래됨
- `fading → resolved`: `expires_on` 초과
- `* → invalidated`: 본문 frontmatter `status: INVALIDATED` 감지 시 즉시

### 3.4 엔티티 우선 + 쓰기 의무 (Prompt 레벨)
모든 브리핑 prompt 가 다음 순서를 강제:
1. **먼저** `tickers/.state/*.yaml` 을 읽어 현재 상태 파악
2. **전일** `alerts/*briefing_*.md` 를 읽어 어제 뭐라고 말했는지 인지
3. **Delta only** 원칙으로 새 브리핑 작성 (변동없음 종목은 한 줄에 뭉쳐서)
4. 모든 종목명은 `[[wikilink]]` 로 감싸기 (엔티티 동기화의 필수 조건)
5. 저장 파일에 YAML frontmatter 강제 (`themes:`, `tickers:` 배열)

→ 다음날 `entity_syncer` 가 그 frontmatter 를 파싱해서 `.state` 갱신 → 다음다음날
prompt 가 그 `.state` 를 읽음. **닫힌 루프** 성립.

---

## 4. 1차 구현 현황 (2026-04-08)

### 4.1 완료
- [x] `events/*.md` 13개, `themes/active/*.md` 6개 frontmatter 통일 마이그레이션
- [x] `tickers/.state/`, `events/.state/`, `themes/active/.state/` 스키마 README 정의
- [x] **`scripts/entity_syncer.py`** 신규 (450 라인, 순수 Python + PyYAML, LLM 0)
  - (a) theme_briefing.md + theme_screener.json → ticker `.state` 갱신
  - (b) 최근 7일 CIO reviews → ticker `.state` 의 status/thesis/invalidation/next_review 갱신
  - (c) events `.state` phase 자동 전이
  - (d) themes/active `.state` 갱신
  - 일일 리포트 `alerts/entity_syncer_report_*.md`
- [x] `scripts/run_entity_syncer.sh` (uv ephemeral `--with pyyaml` 래퍼, launchd 공용)
- [x] **Baseline 검증 완료**: `ticker 33 / 신규 33 / event 전이 0 / theme 6`
  - 33종목 전부 `028050-삼성E&A.yaml` 형태로 코드+이름 정규화 성공
- [x] **`scheduler_daemon.py` prompt 2개 패치**
  - `job_premarket()` — 엔티티 선독 + Delta-only + wikilink 강제 + `premarket_briefing_*.md` 저장
  - `job_theme_screener()` — wikilink 강제 + frontmatter 강제 + 테마명 재사용 지시
- [x] 스케줄러 재시작 완료 (새 prompt 적용 상태로 가동 중)

### 4.2 진행 예정
- [ ] `agents/commander.md` — "entity-first 읽기 + write-back 의무" 문구 추가
- [ ] `agents/investment/cio.md` — 리뷰 전 ticker `.state` 읽기, 리뷰 후 상태 기록 의무
- [ ] `com.robo99.entity_syncer.plist` — launchd 등록 (매일 23:30 자동화)
- [ ] git 재초기화 + `Robo99-x/robo99-vault` 로 origin 교체 후 초기 push
- [ ] Windows Obsidian + Obsidian Git 플러그인 셋업 가이드 (CRLF, pull 전략)
- [ ] 운영 가이드 (사람 영역 vs 기계 영역, 충돌 처리)
- [ ] (보너스) `hq_dashboard.py` 에 `.state` 컬럼 노출

### 4.3 검증 계획
- **D+1 (2026-04-09 08:30)**: 실제 장전 브리핑이 어제와 **다른** 내용으로 나오는지, wikilink 가 붙는지 눈으로 확인
- **D+1 (15:40)**: theme_briefing 에 frontmatter 가 제대로 찍히는지 파일 확인
- **D+2 (08:30)**: entity_syncer 가 간밤에 돌고 난 뒤 prompt 가 "재등장" 태그를 실제로 붙이는지 — 이게 **닫힌 루프의 진짜 증명**

---

## 5. CTO 에게 묻고 싶은 질문

### 5.1 설계/아키텍처
1. **사람 영역 vs 기계 영역 분리** — git 충돌 회피에는 확실히 유효한데, 대신
   "진실의 원천(SoT)" 이 둘로 쪼개지는 대가를 치릅니다. 장기적으로 스키마 드리프트
   (`.md` frontmatter ↔ `.state` yaml 필드 불일치) 를 어떻게 방어하시겠습니까?
   스키마 검증기를 넣을지, 아니면 `.state` 를 아예 생성물(derived) 로만 취급해
   언제든 재생성 가능하게 할지.
2. **Prompt-level 의무 강제** — "모든 종목명을 `[[wikilink]]` 로 감싸라" 를 prompt 에
   적었지만 LLM 이 반드시 지킨다는 보장은 없습니다. 후처리 파서에서 wikilink 없는
   종목명을 감지하고 리트라이/보정하는 안전망을 두는 게 옳을까요, 아니면 entity_syncer
   가 알아서 넓게 긁도록(현재 방식) 두는 게 실용적일까요?
3. **phase 전이 규칙의 경직성** — `30일 + 14일` 같은 상수를 하드코딩했는데, 섹터/이벤트
   유형마다 사이클이 다릅니다(예: 정책 이벤트 vs 실적 이벤트). 이벤트 타입별로 파라미터를
   분리해야 할지, 그냥 전역 디폴트 + 개별 파일에서 override 로 갈지.

### 5.2 데이터 모델
4. **3-엔티티(티커/이벤트/테마)로 충분한가** — 섹터, 매크로 레짐, 포지션(엔트리 로트별)
   은 의도적으로 뺐습니다. 개인 투자 스케일에서 이게 합리적인 절약일지, 아니면
   "포지션" 만이라도 미리 엔티티로 승격하는 게 나을지.
5. **`appearances` 로그의 재형검토** — 현재는 각 ticker `.state` 의 `appearances` 에
   최근 50건을 인라인 저장합니다. 검색은 편하지만 이벤트 소싱 관점에서는 안티패턴에
   가깝습니다. 별도 append-only 로그(`tickers/.state/_events.jsonl`)로 빼야 할까요?

### 5.3 운영
6. **동기화 타이밍** — entity_syncer 를 23:30 에 1회 돌리는데, 장중(09:20 / 14:00)
   스크리닝 결과는 그날 밤까지 `.state` 에 반영되지 않습니다. 장중 실시간 동기화를
   추가하는 게 가치가 있을지, 아니면 "판단은 다음날" 이라는 리듬이 오히려 건강한지.
7. **git 브랜치 전략** — 현재는 단일 main 에 Mac/Windows 양쪽에서 push 하는 구조.
   사람 영역/기계 영역이 파일 단위로 분리돼 있어 이론상 충돌은 없지만, 실무적으로
   `origin/main` race condition 이 한 번은 터질 것 같습니다. 볼트 동기화에 보통 어떤
   브랜치 전략을 권하시는지.
8. **LLM 호출 예산** — 현재 `run_claude` 호출이 하루 약 8회 (미장/장전/장초/장중/장마/
   자가점검 + 장전 watchlist 교차 + CIO 온디맨드). 닫힌 루프가 완성되면 "변동없음" 이
   많아져서 자연스럽게 줄어들 것으로 기대하는데, 반대로 `.state` 읽는 단계에서 토큰이
   더 드는 것도 사실입니다. 이 트레이드오프를 어떻게 보시는지.

### 5.4 리스크
9. **Claude CLI 가 파일을 **잘못** 쓸 위험** — prompt 에 "저장 경로" 를 박아서 쓰게
   하는 방식인데, 경로 타이포/권한 이슈로 엉뚱한 파일을 덮어쓸 가능성이 있습니다.
   스크립트가 파일 쓰기를 **대신** 하고 LLM 은 stdout 에만 뱉게 하는 설계로 바꿔야
   할지.
10. **관측성** — 지금은 `alerts/scheduler.log` + `alerts/logs/entity_syncer_*.log` 뿐이고
    대시보드(Streamlit) 는 읽기 전용. 엔티티 동기화가 조용히 실패해도(예: 정규식 매칭 0건)
    며칠 뒤에야 "브리핑이 다시 똑같아졌네" 로 뒤늦게 발견될 수 있습니다. 어떤 수준의 헬스체크
    /알림이 최소 기준일까요.

---

## 6. 부록 — 핵심 파일 위치

| 항목 | 경로 |
|---|---|
| 마스터 아키텍처 | `SYSTEM.md`, `infra/ARCHITECTURE.md` |
| 스케줄러 | `scripts/scheduler_daemon.py` |
| 엔티티 동기화 | `scripts/entity_syncer.py`, `scripts/run_entity_syncer.sh` |
| Commander 정의 | `agents/commander.md` |
| CIO 정의 | `agents/investment/cio.md` |
| 브리핑 포맷 | `workflows/cio_brief.md` |
| 상태 스키마 | `tickers/.state/README.md`, `events/.state/README.md`, `themes/active/.state/README.md` |
| 대시보드 | `hq_dashboard.py` (Streamlit, :8502) |
| 스크리너 | `scripts/theme_volume_screener.py`, `scripts/rs_ranking.py`, `scripts/stage2_scanner.py`, `scripts/geek_filter.py`, `scripts/vcp_scanner.py` |

---

*문서 작성: 2026-04-08, 다음 갱신: D+2 검증 결과 반영 예정*

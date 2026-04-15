# Robo99 전체 시스템 구조

> 이 파일이 전체 시스템의 지도다. 새 대화를 시작할 때 항상 여기서부터.

---

## 2계층 구조

```
┌─────────────────────────────────────────────────────────────┐
│  1계층: COMMANDER (총사령관)                                  │
│                                                              │
│  모든 대화를 먼저 받아 분류하고, 시스템 전체를 관리한다.        │
│                                                              │
│  • 운영 인프라   — 텔레그램, 스케줄러, 스크립트, 모니터링      │
│  • 라우팅        — 일상 / 투자 / 시스템 / 개발·구현 분류      │
│  • 시스템 설계   — 에이전트·워크플로우·폴더 구조 개선          │
│  • 메모리 관리   — memory/, events/, tickers/, themes/       │
│                                                              │
│  → agents/commander.md                                      │
│  → infra/ARCHITECTURE.md  (인프라 상세 설계)                 │
└──────────┬───────────────────────────────┬──────────────────┘
           │                               │
           │ 복잡도 HIGH                    │ 투자 트리거 ≥ 6
           │ 개발·구현·수정 작업            │
           ▼                               ▼
┌──────────────────────────┐
│  COMMANDER STAFF         │
│  (개발 파이프라인)        │
│                          │
│  architect → developer   │
│  → validator             │
│  → ops-designer          │
│  → dashboard (선택)      │
│                          │
│  활성화: 복잡도 HIGH     │
│  → agents/commander.md   │
│    「Staff 파이프라인」   │
└──────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  2계층: INVESTMENT HQ (투자 본부)                            │
│                                                              │
│  CIO가 총괄하고, 3명의 워커가 병렬로 분석한다.               │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐        │
│  │  OPTIMUS    │  │    GEEK     │  │   ORACLE     │        │
│  │ 드러켄밀러  │  │ 냉철한 퀀트 │  │  워렌 버핏   │        │
│  │             │  │             │  │              │        │
│  │ 거시/모멘텀 │  │ 수치/리스크 │  │ 해자/퀄리티  │        │
│  │ Conviction  │  │ RiskScore   │  │ BUY/PASS     │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘        │
│         └────────────────┼────────────────┘                 │
│                          ▼                                   │
│                   CIO 최종 결론                              │
│         Score = 옵티머스×0.6 + Geek×0.4                     │
│         비중 = Score × 2% (최대 20%)                         │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  BACKTESTER — 전략 검증 2인 체제                   │       │
│  │                                                    │       │
│  │  Validator (검증자)                                │       │
│  │  → Research Contract 고정 → 백테스트 → 성과 리포트 │       │
│  │                                                    │       │
│  │  Falsification Agent (반증자)                      │       │
│  │  → 반증 실험 7종 강제 → 취약점 → 배포 반대 사유   │       │
│  │                                                    │       │
│  │  최종: Reject / Research More /                    │       │
│  │        Paper Trade / Limited Deploy                │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  → agents/optimus.md / geek.md / oracle.md / backtester.md  │
│  → workflows/cio_brief.md                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 라우팅 흐름

```
형님 메시지 수신
      │
      ▼
Commander 판단
      │
      ├─ 투자 트리거 ≥ 6 ──→ 2계층 투자 본부 활성화
      │                       옵티머스 + Geek 병렬 호출
      │                       (Oracle은 "해자 분석" 명시 시)
      │
      ├─ 개발·구현·수정 ───→ 복잡도 평가
      │      │
      │      ├─ HIGH ────────→ Commander Staff 파이프라인 활성화
      │      │                  architect → developer → validator → ops-designer
      │      │                  (→ agents/commander.md 「Staff 파이프라인」 참조)
      │      │
      │      └─ LOW ─────────→ Commander 직접 처리
      │
      ├─ 시스템/설계 질문 ──→ Commander 직접 처리
      │                       infra/ 참조
      │
      └─ 일상/일반 질문 ───→ 빠른 직접 답변
                              워커 호출 없음 (할당량 절약)
```

---

## 폴더 구조

```
robo99_hq/                     ← 전체 본부 (모든 것이 여기에)
│
├── SYSTEM.md                  ← 지금 이 파일 (전체 지도)
│
├── agents/
│   ├── commander.md           ← 1계층: 시스템 총괄 (오케스트레이터)
│   ├── commander-staff/       ← Commander 직속 서브에이전트
│   │   ├── architect.md       설계자 (무엇을 만들 것인가)
│   │   ├── developer.md       개발자 (설계를 코드로)
│   │   ├── validator.md       검증자 (편견 없는 품질 판단)
│   │   ├── ops-designer.md    운영 설계자 (배포·모니터링·롤백)
│   │   └── dashboard.md       대시보드 에이전트 (투자 데이터 시각화)
│   └── investment/            ← 2계층: 투자 본부
│       ├── cio.md             투자 총괄 (Commander가 활성화)
│       ├── optimus.md         드러켄밀러 (거시/모멘텀)
│       ├── geek.md            퀀트 리서처 (수치/리스크)
│       ├── oracle.md          워렌 버핏 (해자/펀더멘털)
│       └── backtester.md      전략 검증 (과거 데이터 백테스트)
│
├── infra/                     ← 1계층 인프라 설계 문서
│   └── ARCHITECTURE.md        시스템 설계 상세
│
├── workflows/
│   └── cio_brief.md           CIO 결재 포맷 (Score 계산 + 실행 전술)
│
├── scripts/                   ← 로컬 실행 스크립트 (토큰 0)
│   ├── start_robo99.sh        Claude Code tmux 세션 시작
│   ├── telegram_watchdog.sh   텔레그램 연결 감시 (5분마다)
│   ├── monitor_daemon.py      시장 모니터링 데몬
│   ├── scheduler_daemon.py    스케줄러
│   ├── stage2_scanner.py      Stage2 종목 스캐너
│   ├── geek_filter.py         Geek 퀀트 필터
│   └── ...
│
├── memory/                    ← 대화 기억·학습
├── events/                    ← 시장 이벤트 카드
├── tickers/                   ← 종목 파일
├── themes/                    ← 테마 분석
├── reviews/                   ← CIO 투자 리뷰
├── alerts/                    ← 스캔 결과 (Stage2, RS랭킹 등)
└── eco-moat-ai/               ← Oracle 지식베이스 (버핏 편지 49년)
```

---

## ClaudeCode/ 와의 관계

```
~/ClaudeCode/          ← Claude Code CLI 실행 위치 (기술적 역할만)
├── .claude/           설정 파일
└── claude-plugins-official/  플러그인 캐시

~/robo99_hq/           ← 진짜 본부 (모든 설계·운영·투자가 여기)
└── (이 파일이 있는 곳)
```

`ClaudeCode/`는 Claude Code가 부팅되는 장소일 뿐.
에이전트·스크립트·문서·투자 데이터는 전부 `robo99_hq/`에서 관리한다.

---

## 인프라 요약 (Commander 관할)

Commander가 운영하는 기술 인프라 전체 설계는 `infra/ARCHITECTURE.md`에 문서화되어 있다.

```
핵심 설계 원칙
├── Local-First: 수치·수급·스캔은 스크립트(토큰 0), Claude는 판단만
├── 실행 환경: tmux + Claude Code CLI (--channels plugin:telegram)
├── 스케줄링: launchd (macOS 네이티브, crontab 대체)
├── 런타임: Bun (빠른 TypeScript 실행)
└── 텔레그램 봇: Grammy 프레임워크 (infra/telegram-bot/)

Commander 인프라 책임 범위
├── 텔레그램 MCP 연결 안정성
├── 스케줄러 상태 모니터링 (직접 실행/중지 금지 → 「스케줄러 격리 규칙」 참조)
├── 시장 모니터링 데몬
└── tmux 세션 생명주기
```

상세 설계 → `infra/ARCHITECTURE.md`

---

## Commander Staff 워크플로우

작업이 Commander에게 들어오면 staff가 순서대로 처리한다:

```
Commander (작업 수신·판단)
      │
      ▼
  architect ──→ 설계 결정서 (무엇을 어떻게 구조화할지)
      │
      ▼
  developer ──→ 구현 결과물 (코드, 실행 가능한 상태)
      │
      ▼
  validator ──→ 검증 보고서 (PASS / FAIL)
      │
      ▼
  ops-designer ──→ 운영 플랜 + 배포 완료
      │
      ▼ (투자 데이터 관련 시)
  dashboard ──→ 시각화 갱신
```

각 단계는 이전 단계의 **결과물만** 받는다. 과정은 격리된다.
→ 컨텍스트 오염 없음. 각 에이전트는 자신의 판단에만 집중.

---

## 핵심 원칙

1. **할당량은 판단에만** — 스크립트·수치·수급은 로컬(토큰 0). Claude는 판단·해석·전략에만.
2. **컨텍스트는 격리한다** — 각 서브에이전트는 자신의 입력만 본다. 오염이 없다.
3. **Commander가 복잡도를 숨긴다** — 형님은 단순하게 말하면 됨. 라우팅은 Commander 몫.
4. **투자 본부는 독립적** — Commander가 활성화하기 전까지 2계층은 침묵.
5. **하나의 본부** — 설계·운영·투자 문서는 전부 `robo99_hq/`에 통합.

---

## 스케줄러 격리 규칙 (CRITICAL)

`scheduler_daemon.py`와 `monitor_daemon.py`는 **독립 데몬**으로 운영된다.
Commander를 포함한 어떤 에이전트도 이 데몬들을 직접 실행·중지·수정해서는 안 된다.

### 절대 금지 (DO NOT)

- `python scheduler_daemon.py` 또는 `uv run python scheduler_daemon.py` 직접 실행
- `python monitor_daemon.py` 직접 실행
- `~/robo99_hq/alerts/` 하위 파일을 직접 수정·삭제
- `~/robo99_hq/tickers/.state/*.yaml` 파일을 직접 수정
- `~/robo99_hq/alerts/cache/krx_cache.sqlite` 에 직접 쓰기

### 허용 (OK)

- `~/robo99_hq/alerts/` 하위 파일을 **읽기** (분석·보고용)
- `~/robo99_hq/tickers/.state/*.yaml`을 **읽기** (브리핑 컨텍스트용)
- `~/robo99_hq/scripts/start_scheduler.sh` 상태 확인 안내
- 스케줄러 문제 발생 시 형님에게 `bash ~/robo99_hq/scripts/start_scheduler.sh --bg` 실행을 **안내**

### 이유

스케줄러는 `start_scheduler.sh`로만 시작해야 한다.
이 스크립트는 `uv run --with pyyaml --with requests --with apscheduler --with pytz`로
필요한 모든 의존성을 격리된 환경에서 보장한다.
다른 Python 환경에서 직접 실행하면 import 실패, 파일 핸들 충돌,
텔레그램 미전송 등의 장애가 발생한다 (2026-04-13 장애 참조).

### 파일 소유권

```
우리 데몬 전용 (쓰기 금지)        읽기만 가능 (양쪽)
─────────────────────────        ─────────────────
alerts/*.md                      watchlist.md
alerts/*.json                    SYSTEM.md
alerts/cache/                    agents/*.md
tickers/.state/*.yaml            tickers/*.md (마크다운)
themes/.state/*.yaml             themes/active/*.md
state_events/*.jsonl             docs/
alerts/.scheduler.lock
```

# Robo99 Agent Operations System - Architecture Design

> 자율적으로 사고하고, 진단하고, 스스로 발전하는 에이전트 운영 프레임워크

---

## 0. 토큰 최적화 전략 (핵심 설계 원칙)

### 비용 구조 이해

이 시스템은 Claude Max 플랜 ($100~$200/월) 내에서 Claude Code CLI가 동작한다.
별도 API 과금이 아니라 **플랜 내 토큰 할당량**을 소비하는 구조다.
따라서 최적화의 목적은 "돈 절약"이 아니라 다음 두 가지다:

1. **할당량 보존**: 플랜 할당량을 아껴서 정작 중요한 작업(사용자 대화, 기능 개발)에 집중 배분
2. **레이트 리밋 회피**: 불필요한 호출로 리밋에 걸려서 진짜 필요할 때 못 쓰는 상황 방지

### 설계 원칙: Claude에게 시키지 말고, Claude가 시킬 것

```
 ❌ 나쁜 설계: 모든 이벤트마다 Claude를 호출
    30초 Health Check → Claude "이거 괜찮아?" → Claude "응 괜찮아"
    → 하루 2,880번 의미없는 할당량 소모

 ✅ 좋은 설계: Claude는 지휘관, 실무는 로컬 도구가 수행
    30초 Health Check → 쉘 스크립트가 수치 수집 → SQLite 저장
    → 이상 감지 시에만 Claude에게 "이런 상황인데 어떻게 할까?" 보고
    → Claude는 판단과 의사결정에만 할당량 사용
```

### 2계층 처리 모델

복잡한 3계층 대신, 실용적인 2계층으로 단순화한다.

```
┌─────────────────────────────────────────────────────────┐
│                    이벤트/요청 발생                        │
└────────────────────────┬────────────────────────────────┘
                         ▼
              ┌─────────────────────┐
              │  LOCAL LAYER        │  ← 할당량 소비 0
              │  (쉘 + Bun + SQLite)│
              │                     │
              │  수행하는 일:        │  99%의 작업을 여기서 처리
              │  • Health check     │
              │  • 메트릭 수집/저장  │
              │  • 로그 파싱/분류    │
              │  • 룰 기반 진단     │
              │  • 임계치 판정      │
              │  • 프로세스 재시작   │
              │  • 텔레그램 정적 응답│
              │  • 과거 패턴 매칭    │
              │                     │
              │  넘기는 기준:        │
              │  • 룰에 없는 미지의 에러│
              │  • 사용자가 자연어로 질문│
              │  • 기능 제안 요청 시  │
              └──────────┬──────────┘
                         │ 로컬에서 해결 불가할 때만
                         ▼
              ┌─────────────────────┐
              │  CLAUDE LAYER       │  ← 할당량 소비
              │  (Claude Code CLI)  │
              │                     │
              │  • 미지의 에러 분석  │  하루 수 회 수준
              │  • 기능 제안 생성    │
              │  • 복잡한 의사결정   │
              │  • 사용자 자연어 대화 │
              └─────────────────────┘
```

### 할당량 소비 추정

| 컴포넌트 | 빈도 | Claude 호출 | 이유 |
|----------|------|------------|------|
| Health Check | 30초마다 | **0회** | 순수 쉘 스크립트 |
| 메트릭 수집/저장 | 30초마다 | **0회** | Bun + SQLite |
| 룰 기반 진단 | 5분마다 | **0회** | 로컬 패턴 매칭 |
| 알려진 에러 복구 | 필요 시 | **0회** | 템플릿 기반 자동 실행 |
| 텔레그램 /status 등 | 요청 시 | **0회** | DB 조회 → 포맷 → 응답 |
| **미지의 에러 분석** | 하루 ~2회 | **2회** | Claude 추론 필요 |
| **기능 제안** | 하루 1회 | **1회** | Claude 창의력 필요 |
| **사용자 자연어** | 하루 ~10회 | **10회** | 대화 본연의 기능 |
| **합계** | | **~13회/일** | 플랜 할당량 여유 충분 |

### 에스컬레이션 게이트

```typescript
// Claude 호출 전 반드시 통과하는 게이트
function shouldAskClaude(event: SystemEvent): boolean {
  // 1. 룰 엔진으로 해결 가능하면 로컬 처리
  if (ruleEngine.canHandle(event)) return false;
  // 2. 동일 패턴이 최근에 Claude로부터 답변 받았으면 캐시 사용
  if (responseCache.has(hash(event.symptoms))) return false;
  // 3. 최근 1시간 내 같은 이벤트면 디바운싱
  if (recentEscalations.has(event.type)) return false;
  return true;
}
```

### 핵심: 텔레그램 명령어별 처리 계층

```
/status        → LOCAL (DB 조회 → 포맷)
/metrics       → LOCAL (SQLite 집계 → 포맷)
/logs          → LOCAL (로그 파일 읽기 → 포맷)
/errors        → LOCAL (분류 DB 조회)
/recover       → LOCAL (룰 기반 복구 실행)
/restart       → LOCAL (tmux 재시작 스크립트)
/config        → LOCAL (설정 파일 읽기/쓰기)
/help          → LOCAL (정적 텍스트)
─────────────────────────────────────────
/ask <질문>    → CLAUDE (자연어 추론 필요)
/suggest       → CLAUDE (기능 제안 생성)
/diagnose      → CLAUDE (복잡한 진단, 룰에 없는 경우)
```

**결과: 10개 명령어 중 8개는 Claude 할당량을 전혀 쓰지 않는다.**

---

## 1. 현재 상태 분석

### AS-IS 구조
```
~/ClaudeCode/
├── scripts/
│   ├── start_robo99.sh          # tmux 세션 시작/재접속
│   └── telegram_watchdog.sh     # 5분마다 alive/dead 체크
├── telegram-bot/
│   └── index.ts                 # echo 수준의 기본 봇
└── .claude/settings.local.json  # 권한 설정
```

### 주요 한계점
- **모니터링**: alive/dead 이진 체크만 존재. 응답 품질, 에러 분류, 성능 추이 없음
- **복구**: tmux 세션 재시작이 유일한 복구 수단. 근본 원인 분석 없음
- **텔레그램**: echo 봇 수준. 운영 대시보드 기능 전무
- **자율성**: 에이전트가 스스로 판단하는 메커니즘 없음

---

## 2. TO-BE 아키텍처

### 시스템 컴포넌트 다이어그램
```
┌─────────────────────────────────────────────────────────────┐
│                 ROBO99 AGENT OPERATIONS SYSTEM               │
│                                                              │
│  ┌─────────────┐        ┌──────────────────┐                │
│  │ CORE RUNTIME│        │ MONITORING CORE  │                │
│  │             │───────▶│                  │                │
│  │ Claude Code │        │ Metrics          │                │
│  │ Telegram    │        │ Error Classifier │                │
│  │ TMux/Bun    │        │ Performance      │                │
│  └─────────────┘        └────────┬─────────┘                │
│                                  │                          │
│         ┌────────────────────────┼──────────────────┐       │
│         ▼                        ▼                  ▼       │
│  ┌──────────────┐    ┌────────────────┐   ┌──────────────┐ │
│  │ SELF-DIAGNOSIS│    │ DATA PIPELINE  │   │  TELEGRAM    │ │
│  │              │    │                │   │  DASHBOARD   │ │
│  │ Symptom Det. │    │ Event Queue    │   │              │ │
│  │ Root Cause   │    │ SQLite Store   │   │ /status      │ │
│  │ Pattern Match│    │ Log Rotation   │   │ /metrics     │ │
│  └──────┬───────┘    └────────────────┘   │ /logs        │ │
│         │                                  │ /recover     │ │
│         ▼                                  │ /features    │ │
│  ┌──────────────┐    ┌────────────────┐   └──────────────┘ │
│  │ AUTO-RECOVERY│    │ FEATURE ENGINE │                     │
│  │              │    │                │                     │
│  │ Plan → Exec  │    │ Suggest        │                     │
│  │ Validate     │    │ Propose        │                     │
│  │ Rollback     │    │ Implement      │                     │
│  └──────────────┘    │ Test & Deploy  │                     │
│                       └────────────────┘                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │              CONFIG & STORAGE LAYER                       ││
│  │  agents.config.ts │ health.db │ logs/ │ features/        ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 데이터 흐름
```
Agent Runtime ──(30초)──▶ Health Checker ──▶ Metrics Collector
                                                    │
                                          ┌─────────┴─────────┐
                                          ▼                   ▼
                                    Error Classifier    Performance
                                          │              Analyzer
                                          ▼                   │
                                    Event Queue ◀─────────────┘
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                         SQLite DB   Alert Engine  Diagnosis
                                          │         Loop
                                          ▼           │
                                    Telegram ◀────────┘
                                    Notification      │
                                                      ▼
                                              Recovery / Feature
                                                  Engine
```

---

## 3. TO-BE 폴더 구조

```
~/ClaudeCode/
├── src/
│   ├── core/
│   │   ├── agent-manager.ts          # 중앙 오케스트레이터
│   │   ├── config.ts                 # 설정 로더
│   │   ├── types.ts                  # 공유 타입/인터페이스
│   │   └── logger.ts                 # 구조화된 로깅
│   │
│   ├── monitoring/
│   │   ├── index.ts                  # 모니터링 오케스트레이터
│   │   ├── health-checker.ts         # 에이전트 헬스체크
│   │   ├── metrics-collector.ts      # 메트릭 수집/집계
│   │   ├── error-classifier.ts       # 에러 자동 분류
│   │   ├── performance-analyzer.ts   # 성능 추이 분석
│   │   └── alert-engine.ts           # 알림 생성/발송
│   │
│   ├── diagnosis/
│   │   ├── index.ts                  # 진단 오케스트레이터
│   │   ├── symptom-detector.ts       # 증상 패턴 인식
│   │   ├── root-cause-analyzer.ts    # 근본 원인 분석
│   │   ├── history-analyzer.ts       # 과거 사례 연관 분석
│   │   └── knowledge-base.ts         # 학습된 패턴 DB
│   │
│   ├── recovery/
│   │   ├── index.ts                  # 복구 오케스트레이터
│   │   ├── planner.ts                # 복구 계획 수립
│   │   ├── executor.ts               # 복구 실행
│   │   ├── validator.ts              # 복구 성공 검증
│   │   ├── rollback.ts               # 롤백 매니저
│   │   └── rules.ts                  # 복구 의사결정 트리
│   │
│   ├── features/
│   │   ├── index.ts                  # 기능 엔진
│   │   ├── suggestion-engine.ts      # 개선 제안 생성
│   │   ├── proposal-generator.ts     # 구현 제안서 작성
│   │   ├── implementor.ts            # 자동 구현
│   │   └── test-runner.ts            # 검증 실행
│   │
│   ├── telegram/
│   │   ├── index.ts                  # 봇 오케스트레이터
│   │   ├── handlers/
│   │   │   ├── status.ts             # /status 명령
│   │   │   ├── metrics.ts            # /metrics 명령
│   │   │   ├── logs.ts               # /logs 조회
│   │   │   ├── recovery.ts           # /recover 복구 트리거
│   │   │   ├── features.ts           # /features 기능 관리
│   │   │   └── admin.ts              # /admin 관리자 명령
│   │   ├── keyboards.ts              # 인라인 키보드
│   │   └── formatters.ts             # 메시지 포맷터
│   │
│   ├── data/
│   │   ├── storage.ts                # SQLite 추상화 레이어
│   │   ├── event-queue.ts            # 인메모리 이벤트 큐
│   │   └── migrations.ts             # 스키마 마이그레이션
│   │
│   └── utils/
│       ├── tmux.ts                   # tmux 제어
│       ├── process.ts                # 프로세스 관리
│       └── shell.ts                  # 쉘 명령 실행
│
├── config/
│   ├── agents.config.ts              # 에이전트 정의
│   ├── monitoring.config.ts          # 모니터링 설정
│   ├── recovery.rules.ts             # 복구 룰셋
│   └── telegram.config.ts            # 봇 설정
│
├── data/
│   ├── robo99.db                     # SQLite (메트릭+진단+기능)
│   ├── logs/
│   │   ├── agent.log                 # 에이전트 로그
│   │   ├── monitoring.log            # 모니터링 로그
│   │   ├── recovery.log              # 복구 이력
│   │   └── rotated/                  # 로테이션 아카이브
│   ├── features/
│   │   ├── proposed/                 # 승인 대기 제안
│   │   ├── implemented/              # 구현 완료
│   │   └── rejected/                 # 거부 + 사유
│   └── snapshots/                    # 시스템 상태 스냅샷
│
├── bin/
│   ├── start-agent.sh                # 향상된 실행기
│   ├── watchdog.sh                   # 향상된 워치독
│   └── deploy-feature.sh             # 기능 배포기
│
├── telegram-bot/                     # (기존, 점진적 마이그레이션)
├── scripts/                          # (기존, 점진적 교체)
├── package.json
├── tsconfig.json
└── ARCHITECTURE.md                   # 이 문서
```

---

## 4. 핵심 타입 정의

```typescript
// === 에이전트 상태 ===
interface AgentState {
  id: string;
  name: string;
  status: 'running' | 'paused' | 'recovering' | 'errored' | 'upgrading';
  uptime: number;
  tmuxSession: string;
  pid: number | null;
  lastHealthCheck: Date;
  version: string;
}

// === 헬스 메트릭 ===
interface HealthMetrics {
  timestamp: Date;
  agentId: string;
  status: 'healthy' | 'degraded' | 'critical';
  cpuPercent: number;
  memoryMB: number;
  responseTimeMs: number;
  errorRate: number;           // 최근 윈도우 내 에러 비율
  activeConnections: number;   // 텔레그램 등 활성 연결 수
}

// === 에러 분류 ===
interface ClassifiedError {
  id: string;
  timestamp: Date;
  raw: string;
  category: 'network' | 'auth' | 'resource' | 'timeout' | 'logic' | 'unknown';
  severity: 'low' | 'medium' | 'high' | 'critical';
  frequency: number;           // 최근 동일 에러 발생 횟수
  firstSeen: Date;
  context: Record<string, unknown>;
}

// === 진단 결과 ===
interface DiagnosisResult {
  id: string;
  timestamp: Date;
  symptoms: string[];
  rootCause: string;
  confidence: number;          // 0.0 ~ 1.0
  relatedIncidents: string[];  // 과거 유사 사례 ID
  suggestedActions: RecoveryAction[];
}

// === 복구 계획 ===
interface RecoveryPlan {
  id: string;
  diagnosisId: string;
  steps: RecoveryStep[];
  estimatedSeconds: number;
  riskLevel: 'low' | 'medium' | 'high';
  canAutoExecute: boolean;     // low risk만 자동 실행
}

interface RecoveryStep {
  order: number;
  action: string;
  target: string;
  params: Record<string, unknown>;
  validation: string;          // 성공 확인 방법
  rollback?: string;           // 실패 시 롤백 액션
}

// === 기능 제안 ===
interface FeatureProposal {
  id: string;
  created: Date;
  title: string;
  description: string;
  rationale: string;           // 왜 필요한가
  effort: 'trivial' | 'small' | 'medium' | 'large';
  risk: 'low' | 'medium' | 'high';
  status: 'proposed' | 'approved' | 'implementing' | 'deployed' | 'rejected';
  implementationPlan: string;
  testCriteria: string[];
}

// === 시스템 이벤트 ===
interface SystemEvent {
  id: string;
  timestamp: Date;
  source: 'agent' | 'monitor' | 'diagnosis' | 'recovery' | 'feature' | 'telegram';
  type: string;
  severity: 'info' | 'warn' | 'error' | 'critical';
  data: Record<string, unknown>;
  correlationId?: string;      // 관련 이벤트 추적용
}
```

---

## 5. 컴포넌트별 상세 설계

### 5.1 모니터링 코어

| 항목 | AS-IS | TO-BE |
|------|-------|-------|
| 체크 주기 | 5분 | 30초 |
| 체크 항목 | API alive, tmux 존재, bun 중복 | CPU, Memory, 응답시간, 에러율, 연결상태 |
| 에러 처리 | 로그 한 줄 | 분류 → 빈도 분석 → 심각도 판정 → 알림 |
| 데이터 | 텍스트 로그 | SQLite + 구조화 로그 + 메트릭 시계열 |
| 알림 | 없음 | 텔레그램 실시간 알림 (심각도별 차등) |

**핵심 로직:**
```
30초마다:
  1. tmux 세션 상태 확인
  2. bun 프로세스 CPU/Memory 수집
  3. 텔레그램 API 응답시간 측정
  4. 에러 로그 파싱 → 자동 분류
  5. 메트릭 SQLite 저장
  6. 임계치 초과 시 → Alert Engine → 텔레그램
```

### 5.2 자가 진단 엔진

```
5분마다 (또는 Alert 트리거 시 즉시):
  1. 최근 메트릭 윈도우 분석 (1분, 5분, 15분)
  2. 증상 패턴 매칭:
     - 응답시간 증가 + CPU 정상 → 네트워크 문제
     - CPU 급등 + 에러율 증가 → 프로세스 과부하
     - 연결 수 0 + API 실패 → 인증/토큰 문제
  3. 과거 사례 DB 조회 → 유사 사례 매칭
  4. 신뢰도 산출 → 복구 액션 제안
  5. 결과를 knowledge-base에 축적
```

### 5.3 자동 복구 루프

```
진단 결과 수신 시:
  1. 복구 계획 수립 (rules.ts 의사결정 트리)
  2. 리스크 평가:
     - low: 자동 실행 (로그레벨 변경, 캐시 클리어 등)
     - medium: 텔레그램으로 승인 요청 후 실행
     - high: 텔레그램 알림만 (수동 개입 필요)
  3. 실행 → 검증 → 성공/실패 기록
  4. 실패 시 롤백 → 에스컬레이션
```

**복구 룰 예시:**
```typescript
const RECOVERY_RULES = [
  {
    symptom: ['tmux_session_missing'],
    action: 'restart_tmux_session',
    risk: 'low',
    auto: true,
  },
  {
    symptom: ['bun_process_duplicate'],
    action: 'kill_old_bun_keep_latest',
    risk: 'low',
    auto: true,
  },
  {
    symptom: ['high_cpu', 'high_error_rate'],
    action: 'graceful_restart',
    risk: 'medium',
    auto: false,  // 승인 필요
  },
  {
    symptom: ['telegram_api_auth_fail'],
    action: 'rotate_token_and_restart',
    risk: 'high',
    auto: false,  // 수동 개입
  },
];
```

### 5.4 기능 자동 제안 엔진

```
매시간 (또는 충분한 상호작용 데이터 축적 시):
  1. 최근 상호작용 패턴 분석
  2. 반복 에러/복구 패턴에서 개선점 도출
  3. 기능 제안서 생성:
     - 제목, 설명, 이유, 예상 효과
     - 구현 난이도 + 리스크 평가
     - 테스트 기준
  4. 텔레그램으로 제안 발송 (인라인 키보드: 승인/거부/보류)
  5. 승인 시:
     - trivial/small + low risk → 자동 구현 + 테스트
     - 그 외 → 구현 계획서만 작성, 수동 검토
```

### 5.5 텔레그램 대시보드

**명령어 체계:**
```
/status           시스템 상태 요약 (에이전트, 프로세스, 연결)
/metrics [1h|6h|24h]  성능 메트릭 리포트
/logs [error|warn|all] [n]  최근 로그 조회
/errors           최근 에러 분류 요약
/recover [auto|plan-id]    복구 트리거/승인
/features         기능 제안 목록
/approve <id>     기능 제안 승인
/reject <id>      기능 제안 거부
/restart          에이전트 재시작
/config [key] [value]  설정 조회/변경
/help             명령어 도움말
```

**인라인 키보드 예시:**
```
[Alert] CPU 사용률 92% (critical)
근본 원인: bun 프로세스 메모리 누수 추정
신뢰도: 0.78

┌─────────────────────────────────┐
│ [자동 복구 실행] [상세 로그 보기] │
│ [무시]          [에스컬레이션]   │
└─────────────────────────────────┘
```

---

## 6. 구현 로드맵

### Phase 1: Foundation (1~3일)
- [ ] `src/core/types.ts` — 공유 타입 정의
- [ ] `src/core/logger.ts` — 구조화 로깅 (JSON, 로테이션)
- [ ] `src/core/config.ts` — 설정 로더
- [ ] `config/agents.config.ts` — 에이전트 설정
- [ ] `src/data/storage.ts` — SQLite 추상화 (bun:sqlite)
- [ ] `src/data/migrations.ts` — 스키마 초기화
- [ ] `package.json` + `tsconfig.json` 업데이트

### Phase 2: Monitoring (3~5일)
- [ ] `src/monitoring/health-checker.ts` — 30초 헬스체크
- [ ] `src/monitoring/metrics-collector.ts` — 메트릭 수집
- [ ] `src/monitoring/error-classifier.ts` — 에러 분류
- [ ] `src/monitoring/alert-engine.ts` — 알림 생성
- [ ] `src/monitoring/index.ts` — 모니터링 통합

### Phase 3: Diagnosis & Recovery (5~8일)
- [ ] `src/diagnosis/symptom-detector.ts` — 증상 탐지
- [ ] `src/diagnosis/root-cause-analyzer.ts` — RCA
- [ ] `src/diagnosis/knowledge-base.ts` — 학습 DB
- [ ] `src/recovery/rules.ts` — 복구 의사결정 트리
- [ ] `src/recovery/planner.ts` — 복구 계획 수립
- [ ] `src/recovery/executor.ts` — 복구 실행
- [ ] `src/recovery/validator.ts` — 검증 + 롤백

### Phase 4: Telegram Dashboard (8~11일)
- [ ] `src/telegram/index.ts` — 봇 재구축
- [ ] 핸들러: status, metrics, logs, errors
- [ ] 핸들러: recover, features, admin
- [ ] `src/telegram/keyboards.ts` — 인라인 키보드
- [ ] `src/telegram/formatters.ts` — 리포트 포맷

### Phase 5: Feature Engine (11~14일)
- [ ] `src/features/suggestion-engine.ts` — 패턴 분석
- [ ] `src/features/proposal-generator.ts` — 제안서 생성
- [ ] `src/features/implementor.ts` — 자동 구현
- [ ] `src/features/test-runner.ts` — 검증

### Phase 6: Integration & Polish (14~17일)
- [ ] `src/core/agent-manager.ts` — 전체 오케스트레이션
- [ ] `bin/start-agent.sh` — 향상된 실행기
- [ ] `bin/watchdog.sh` — 향상된 워치독
- [ ] 로그 로테이션, 스냅샷, 에러 핸들링 강화
- [ ] 기존 scripts/ 마이그레이션 완료

---

## 7. 설정 예시

```typescript
// config/agents.config.ts
export const AGENT_CONFIG = {
  id: 'robo99-main',
  name: 'Robo99 Main Agent',
  tmuxSession: 'robo99',
  claudeBin: '~/.local/bin/claude',
  claudeArgs: '--channels plugin:telegram@claude-plugins-official',

  healthCheck: {
    intervalMs: 30_000,
    timeoutMs: 10_000,
  },

  thresholds: {
    cpu: { warn: 70, critical: 90 },
    memory: { warn: 75, critical: 90 },
    errorRate: { warn: 3, critical: 10 },     // percent
    responseTime: { warn: 3000, critical: 8000 }, // ms
  },

  recovery: {
    autoEnabled: true,
    maxAutoRetries: 3,
    cooldownMs: 300_000,  // 복구 후 5분간 재진단 보류
  },

  features: {
    suggestionEnabled: true,
    autoImplementRisk: 'low',  // low 리스크만 자동 구현
    proposalCooldown: 3600_000, // 1시간에 최대 1개 제안
  },

  // Claude 호출 제어 (플랜 할당량 보존)
  claudeGate: {
    maxCallsPerHour: 5,          // 시간당 최대 5회 호출
    maxCallsPerDay: 30,          // 일일 최대 30회 호출
    debounceMs: 300_000,         // 동일 이벤트 5분 디바운싱
    cacheTtlMs: 3600_000,        // 응답 캐시 1시간 유지
    alertOnRateLimit: true,      // 레이트 리밋 감지 시 텔레그램 알림
  },
};

// config/monitoring.config.ts
export const MONITORING_CONFIG = {
  logs: {
    dir: '~/ClaudeCode/data/logs',
    maxSizeMB: 50,
    maxFiles: 10,
    format: 'json' as const,
    rotateDaily: true,
  },
  storage: {
    dbPath: '~/ClaudeCode/data/robo99.db',
    retentionDays: 30,
    snapshotIntervalMs: 3600_000,
  },
  metrics: {
    windows: ['1m', '5m', '15m', '1h'] as const,
  },
};
```

---

## 8. SQLite 스키마

```sql
-- 헬스 메트릭 시계열
CREATE TABLE health_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  agent_id TEXT NOT NULL,
  status TEXT NOT NULL,
  cpu_percent REAL,
  memory_mb REAL,
  response_time_ms INTEGER,
  error_rate REAL,
  active_connections INTEGER
);
CREATE INDEX idx_health_ts ON health_metrics(timestamp);

-- 분류된 에러
CREATE TABLE classified_errors (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  raw TEXT NOT NULL,
  category TEXT NOT NULL,
  severity TEXT NOT NULL,
  frequency INTEGER DEFAULT 1,
  first_seen TEXT NOT NULL,
  context TEXT  -- JSON
);

-- 진단 이력
CREATE TABLE diagnoses (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  symptoms TEXT NOT NULL,  -- JSON array
  root_cause TEXT NOT NULL,
  confidence REAL NOT NULL,
  related_incidents TEXT,  -- JSON array
  suggested_actions TEXT,  -- JSON array
  outcome TEXT  -- 'resolved' | 'failed' | 'escalated' | null
);

-- 복구 이력
CREATE TABLE recovery_history (
  id TEXT PRIMARY KEY,
  diagnosis_id TEXT REFERENCES diagnoses(id),
  timestamp TEXT NOT NULL,
  plan TEXT NOT NULL,       -- JSON
  risk_level TEXT NOT NULL,
  auto_executed INTEGER NOT NULL DEFAULT 0,
  result TEXT NOT NULL,     -- 'success' | 'failed' | 'rolled_back'
  duration_ms INTEGER
);

-- 기능 제안
CREATE TABLE feature_proposals (
  id TEXT PRIMARY KEY,
  created TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  rationale TEXT,
  effort TEXT,
  risk TEXT,
  status TEXT NOT NULL DEFAULT 'proposed',
  implementation_plan TEXT,
  test_criteria TEXT,  -- JSON array
  resolved_at TEXT
);

-- 시스템 이벤트 (범용 이벤트 로그)
CREATE TABLE system_events (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  source TEXT NOT NULL,
  type TEXT NOT NULL,
  severity TEXT NOT NULL,
  data TEXT,  -- JSON
  correlation_id TEXT
);
CREATE INDEX idx_events_ts ON system_events(timestamp);
CREATE INDEX idx_events_severity ON system_events(severity);

-- 학습된 패턴 (knowledge base)
CREATE TABLE learned_patterns (
  id TEXT PRIMARY KEY,
  pattern TEXT NOT NULL,
  category TEXT NOT NULL,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  last_seen TEXT,
  recommended_action TEXT
);
```

---

## 9. 핵심 설계 원칙

1. **Local-First (할당량 보존)**: 99%는 로컬 처리, Claude는 판단/창의에만 사용. 플랜 할당량을 핵심 작업에 집중
2. **점진적 자율성**: low risk 자동 → medium 승인 후 → high 수동. 신뢰가 쌓이면 자율 범위 확대
3. **관측 가능성 우선**: 모든 액션은 이벤트로 기록. 사후 분석과 학습의 기반
4. **안전한 실패**: 모든 자동 복구에 롤백 경로 보장. 최악의 경우 원상복구
5. **학습 루프**: 진단→복구→결과→패턴 축적. 같은 문제를 반복하지 않음. L2 캐시로 축적
6. **단일 진입점**: 텔레그램이 유일한 운영 인터페이스. 어디서든 모바일로 제어
7. **호출 게이트**: 시간당/일일 Claude 호출 횟수 제한 + 디바운싱. 레이트 리밋 원천 방지

# robo99_hq Architecture v2 — 독립 운영 설계

## 1. 현재 문제 진단

### 1.1 왜 스케줄러가 전부 고장나는가

| 증상 | 근본 원인 |
|------|-----------|
| stage2_scanner "Too many open files" | SQLite 커넥션을 루프 1200회에서 안 닫음 |
| vcp_scanner 연쇄 실패 | 같은 job 안에서 stage2가 fd를 고갈시킨 뒤 실행 |
| Claude CLI 3초 실패 (theme, watchlist) | run_claude()에 재시도 없음, 진단 정보 부족 |
| 장전 브리핑 텔레그램 누락 | vault_writer import 실패 (openclaw 환경에서 실행) |
| 텔레그램이 오락가락 | 7곳에 복붙된 토큰 로딩 + 전송 코드 |

### 1.2 구조적 부채

```
현재: 각 스크립트가 독립적으로 DB 열고, 텔레그램 보내고, 파일 쓴다
      ↓
      stage2_scanner.py → sqlite3.connect() × 1200 → fd 폭발
      vcp_scanner.py    → sqlite3.connect() × 500  → fd 폭발
      stage2_briefing.py → 자체 Telegram 전송
      vcp_scanner.py     → 자체 Telegram 전송
      monitor_daemon.py  → 자체 Telegram 전송
      healthcheck.py     → 자체 Telegram 전송
      scheduler_daemon.py → 자체 Telegram 전송
      vault_writer.py    → 자체 Telegram 전송
```

**7개의 Telegram 구현, 6개의 토큰 로딩 로직, 0개의 공유 인프라.**

---

## 2. 새 아키텍처 설계

### 2.1 핵심 원칙

1. **Single Source of Truth** — DB 접근, Telegram, 파일 I/O는 각각 하나의 모듈만 담당
2. **LLM은 stdout JSON만** — Claude CLI는 파일 쓰기/Telegram 전송 금지 (CTO 원칙)
3. **Job 격리** — 한 job의 실패가 다른 job에 전파되지 않음
4. **openclaw 독립** — 우리 시스템은 openclaw 없이 완전히 작동

### 2.2 모듈 구조

```
scripts/
├── lib/                          ← NEW: 공유 인프라 (모든 스크립트가 import)
│   ├── __init__.py
│   ├── db.py                     ← SQLite 커넥션 관리 (단일 진입점)
│   ├── telegram.py               ← Telegram 전송 (단일 진입점)
│   ├── claude_runner.py          ← Claude CLI wrapper (재시도, 진단)
│   └── config.py                 ← 경로, 토큰, 상수 (단일 진입점)
│
├── scanners/                     ← 리팩터링: lib/ 위에 재작성
│   ├── stage2_scanner.py         ← lib.db 사용, 자체 DB 열지 않음
│   ├── vcp_scanner.py            ← lib.db 사용
│   ├── theme_volume_screener.py  ← lib.db 사용
│   ├── rs_ranking.py
│   ├── geek_filter.py
│   └── stage2_briefing.py        ← lib.telegram 사용, 자체 전송 안 함
│
├── entity_syncer.py              ← 유지 (이미 잘 설계됨)
├── vault_writer.py               ← 유지 + lib.telegram으로 전송 위임
├── schema_models.py              ← 유지
├── healthcheck_entities.py       ← lib.telegram 사용으로 전환
├── scheduler_daemon.py           ← lib.claude_runner 사용으로 전환
├── monitor_daemon.py             ← lib.telegram 사용으로 전환
│
├── start_scheduler.sh            ← 유일한 스케줄러 시작점
└── rerun_today.py                ← 수동 재실행 도구
```

### 2.3 lib/ 모듈 상세 설계

#### lib/config.py — 모든 경로와 설정의 단일 진입점

```python
from pathlib import Path

BASE = Path.home() / "robo99_hq"
SCRIPTS = BASE / "scripts"
ALERTS = BASE / "alerts"
CACHE_DIR = ALERTS / "cache"
CACHE_DB = CACHE_DIR / "krx_cache.sqlite"
STATE_DIR = BASE / "tickers" / ".state"
SECRETS = BASE / "secrets"

TG_CHAT_ID = "1883449676"

# 토큰 로딩 우선순위:
# 1. 환경변수 TELEGRAM_BOT_TOKEN
# 2. ~/robo99_hq/secrets/telegram_token.txt  ← 우리 소유
# 3. ~/.claude/channels/telegram/.env         ← openclaw 공유 (fallback)
```

#### lib/db.py — SQLite 커넥션 관리

```python
"""
모든 scanner가 이 모듈을 통해서만 DB에 접근한다.
직접 sqlite3.connect() 호출 금지.
"""
import sqlite3
import pandas as pd
from contextlib import contextmanager
from lib.config import CACHE_DB

@contextmanager
def connect(db_path=CACHE_DB):
    """Context manager — with db.connect() as conn: ..."""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

def query_df(sql, params=(), db_path=CACHE_DB) -> pd.DataFrame:
    """한 줄로 쿼리 → DataFrame. 커넥션 자동 관리."""
    with connect(db_path) as conn:
        return pd.read_sql(sql, conn, params=params)

def cache_is_fresh(end_date: str) -> bool:
    """캐시 최신 여부 확인."""
    ...
```

#### lib/telegram.py — 단일 Telegram 모듈

```python
"""
robo99_hq 전체에서 Telegram 메시지를 보내는 유일한 모듈.
다른 스크립트는 직접 requests.post() 금지.
"""

def send(text: str, chat_id: str = None) -> bool:
    """메시지 전송. 4000자 초과 시 자동 분할."""
    ...

def send_alert(title: str, detail: str) -> bool:
    """⚠️ 포맷 경고 전송."""
    ...

def send_briefing(title: str, body: str) -> bool:
    """📊 포맷 브리핑 전송."""
    ...
```

#### lib/claude_runner.py — Claude CLI wrapper

```python
"""
Claude CLI 호출의 단일 진입점.
재시도, 타임아웃, stdout/stderr 진단을 표준화.
"""

def run(prompt: str, task_name: str,
        retries: int = 2,
        timeout: int = 600,
        retry_delay: int = 10) -> str | None:
    """
    Claude CLI 실행.
    실패 시 retries만큼 재시도.
    exit code, stdout 앞 200자, stderr를 모두 로깅.
    """
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "-p", prompt],
            ...
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

        # 진단 로그
        log.error(
            f"[{task_name}] 시도 {attempt}/{retries} 실패: "
            f"exit={result.returncode}, "
            f"stdout={len(result.stdout)}chars, "
            f"stderr={result.stderr[:200] or '(empty)'}"
        )
        if attempt < retries:
            time.sleep(retry_delay)

    telegram.send_alert(f"Claude:{task_name}", "최종 실패")
    return None
```

### 2.4 Scanner 리팩터링 패턴

**Before (현재):**
```python
# stage2_scanner.py 안에서
conn = sqlite3.connect(CACHE_DB)       # ← fd 누수
df = pd.read_sql(q, conn)             # ← conn 안 닫음
# ... 1200번 반복 ...
requests.post(telegram_api, ...)       # ← 자체 전송
```

**After (v2):**
```python
# scanners/stage2_scanner.py
from lib import db, telegram

df = db.query_df(sql, params)          # ← 자동 close
# ... 결과 계산 ...
return results                         # ← JSON 반환만, 전송은 상위에서
```

### 2.5 Scheduler 흐름 (v2)

```
scheduler_daemon.py
  │
  ├─ job_premarket()
  │    ├─ claude_runner.run(prompt, retries=2)  → JSON stdout
  │    ├─ vault_writer.process_premarket(json)  → .md 파일 + 텔레그램
  │    └─ entity_syncer (후처리)
  │
  ├─ job_screening_morning()
  │    ├─ subprocess: scanners/rs_ranking.py
  │    ├─ subprocess: scanners/stage2_scanner.py  ← lib.db 사용, fd 안전
  │    ├─ subprocess: scanners/geek_filter.py
  │    ├─ subprocess: scanners/stage2_briefing.py ← lib.telegram으로 전송
  │    └─ subprocess: scanners/vcp_scanner.py     ← 독립 실행, stage2 실패와 무관
  │
  ├─ job_theme_screener()
  │    ├─ subprocess: scanners/theme_volume_screener.py
  │    ├─ claude_runner.run(prompt, retries=2)  → JSON stdout
  │    └─ vault_writer.process_theme_screener(json) → .md + 텔레그램
  │
  └─ job_system_health()
       └─ healthcheck_entities.py → lib.telegram.send_alert()
```

---

## 3. openclaw 격리 전략

### 3.1 openclaw이 건드릴 수 있는 것 (현재)

| 접점 | 위험도 | 조치 |
|------|--------|------|
| scheduler_daemon.py를 자체 Python으로 실행 | 🔴 높음 | openclaw SYSTEM_PROMPT에서 제거 |
| ~/.claude/channels/telegram/.env 수정 | 🟡 중간 | 우리 토큰을 secrets/에 독립 저장 |
| Claude CLI 동시 호출 (rate limit) | 🟡 중간 | claude_runner에 backoff 추가 |
| tmux "robo99" 세션에서 스크립트 실행 | 🟠 | tmux 세션 이름 분리 확인 |

### 3.2 openclaw 쪽에서 해야 할 것

#### (A) SYSTEM_PROMPT.md 수정

`~/.openclaw/workspace_hq/SYSTEM_PROMPT.md`에서 다음 규칙 추가:

```markdown
## 금지 사항
- ~/robo99_hq/scripts/scheduler_daemon.py 를 직접 실행하지 마시오
- ~/robo99_hq/scripts/monitor_daemon.py 를 직접 실행하지 마시오
- ~/robo99_hq/alerts/ 디렉토리의 파일을 수정하지 마시오
- ~/robo99_hq/tickers/.state/ 파일을 직접 수정하지 마시오
- 위 작업은 모두 start_scheduler.sh 를 통해 자동 관리됩니다
```

#### (B) start_robo99.sh에서 스케줄러 시작 코드 제거

만약 `start_robo99.sh`가 scheduler_daemon.py를 같이 실행한다면, 해당 라인 제거.
스케줄러는 오직 `start_scheduler.sh`로만 시작.

#### (C) 텔레그램 토큰 독립

```bash
# 우리 전용 토큰 파일 생성 (한 번만)
cp ~/.claude/channels/telegram/.env ~/robo99_hq/secrets/telegram_token.txt
# telegram_token.txt 내용: 토큰 값만 (TELEGRAM_BOT_TOKEN= 접두사 없이)
```

### 3.3 우리 쪽에서 하는 방어

- `lib/config.py`가 토큰을 `secrets/telegram_token.txt` → env var → `.claude/.env` 순으로 로딩
- `start_scheduler.sh`가 uv ephemeral 환경을 보장 (openclaw Python과 완전 분리)
- `scheduler_daemon.py`의 lockfile이 중복 실행 차단
- 모든 스크립트가 `lib/` 를 통해서만 DB/Telegram 접근 → 일관된 에러 처리

---

## 4. 구현 순서

### Phase A: 인프라 (lib/) — 1일

1. `lib/config.py` — 경로, 토큰, 상수
2. `lib/db.py` — SQLite context manager + query_df
3. `lib/telegram.py` — 통합 전송 모듈
4. `lib/claude_runner.py` — Claude CLI wrapper + 재시도
5. 테스트: 각 모듈 독립 동작 확인

### Phase B: Scanner 전환 — 1일

1. stage2_scanner → `lib.db.query_df()` 사용
2. vcp_scanner → `lib.db.query_df()` 사용
3. stage2_briefing → `lib.telegram.send_briefing()` 사용
4. theme_volume_screener → `lib.db` 사용
5. monitor_daemon → `lib.telegram.send_alert()` 사용
6. healthcheck → `lib.telegram.send_alert()` 사용

### Phase C: Scheduler + vault_writer 통합 — 0.5일

1. scheduler_daemon → `lib.claude_runner.run()` 사용
2. vault_writer → `lib.telegram.send()` 위임
3. notify_failure → `lib.telegram.send_alert()` 위임
4. 전체 파이프라인 테스트

### Phase D: openclaw 하네스 — 사용자 작업

1. SYSTEM_PROMPT.md 금지 규칙 추가
2. start_robo99.sh에서 스케줄러 코드 제거
3. 토큰 파일 독립 생성
4. 2일 모니터링 후 안정성 확인

---

## 5. 파일 소유권 맵 (최종)

```
~/robo99_hq/
├── scripts/
│   ├── lib/                    ← 우리 소유 (v2 신규)
│   ├── scanners/               ← 우리 소유 (v2 리팩터)
│   ├── entity_syncer.py        ← 우리 소유
│   ├── vault_writer.py         ← 우리 소유
│   ├── schema_models.py        ← 우리 소유
│   ├── scheduler_daemon.py     ← 우리 소유 (openclaw 실행 금지)
│   ├── monitor_daemon.py       ← 우리 소유 (openclaw 실행 금지)
│   ├── start_scheduler.sh      ← 우리 소유 (유일한 시작점)
│   ├── start_robo99.sh         ← openclaw 소유 (건드리지 않음)
│   └── telegram_watchdog.sh    ← openclaw 소유 (건드리지 않음)
│
├── alerts/                     ← 우리 소유 (openclaw 쓰기 금지)
├── tickers/.state/             ← 우리 소유 (entity_syncer만 쓰기)
├── secrets/                    ← 우리 소유
│   └── telegram_token.txt      ← v2 신규: 독립 토큰
│
├── watchlist.md                ← 사용자 소유 (양쪽 읽기 가능)
├── CLAUDE.md                   ← 사용자 소유 (양쪽 읽기 가능)
└── docs/                       ← 사용자 소유
```

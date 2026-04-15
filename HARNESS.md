# HARNESS — openclaw 격리 지침

> **목적**: openclaw가 더 이상 로보99 파일을 간섭하지 못하도록 차단.
> **대상**: openclaw 측 시스템 프롬프트·설정·실행 환경.
> **작성일**: 2026-04-14

---

## 왜 필요한가

2026-04-13 장애 원인을 역추적한 결과:

1. `scheduler_daemon.py`를 openclaw가 자기 Python 환경에서 직접 실행 → `import apscheduler` 실패 → 묵시적 종료
2. `~/robo99_hq/alerts/cache/krx_cache.sqlite`를 양쪽이 동시 쓰기 → fd 누수 + 레이스 컨디션
3. `~/.claude/channels/telegram/.env` 토큰 파일을 openclaw가 교체 → 우리 봇 인증 실패
4. commander.md의 "스케줄러 관리" 문구를 보고 openclaw가 "내가 관리해야 한다"고 오판

**핵심 원칙**: openclaw와 우리 시스템은 **같은 디렉토리를 공유하지만 쓰기 권한은 분리**한다.

---

## 형님이 해야 할 작업 (순서대로)

### 1. 독립 토큰 파일 생성 (1분)

```bash
bash ~/robo99_hq/scripts/setup_telegram_token.sh
```

- `~/.claude/channels/telegram/.env` 에서 토큰 추출
- `~/robo99_hq/secrets/telegram_token.txt` 에 저장 (chmod 600)
- Telegram API로 유효성 자동 검증

이후 `lib/config.py`의 `get_tg_token()`이 **우리 파일을 최우선**으로 읽음.
openclaw가 `.env`를 바꿔도 우리 시스템은 영향받지 않음.

---

### 2. openclaw SYSTEM_PROMPT에 금지 규칙 추가

openclaw가 무엇이든 — Claude Code든 다른 에이전트 세션이든 — 형님 컴퓨터에서
로보99 파일에 접근할 수 있는 모든 세션의 시스템 프롬프트에 아래 블록을 추가.

```markdown
## 🚫 ROBO99 파일 간섭 금지 (CRITICAL)

`~/robo99_hq/` 는 독립 시스템입니다. 다음 규칙을 반드시 지키세요.

### 절대 하지 말 것

1. **`~/robo99_hq/scripts/*_daemon.py` 직접 실행 금지**
   - `scheduler_daemon.py`, `monitor_daemon.py`는 launchd가 `start_scheduler.sh`로만 실행
   - `python scheduler_daemon.py` 또는 `uv run python scheduler_daemon.py` 실행하지 말 것

2. **아래 경로에 쓰기 금지** (읽기만 허용)
   ```
   ~/robo99_hq/alerts/                    ← 스캐너 결과
   ~/robo99_hq/alerts/cache/*.sqlite      ← KRX 가격 캐시
   ~/robo99_hq/tickers/.state/            ← 종목 상태
   ~/robo99_hq/themes/.state/             ← 테마 상태
   ~/robo99_hq/state_events/              ← 이벤트 저널
   ~/robo99_hq/alerts/.scheduler.lock     ← 스케줄러 락
   ~/robo99_hq/secrets/                   ← 독립 자격증명
   ```

3. **launchd plist 수정 금지**
   - `~/Library/LaunchAgents/com.robo99.*.plist` 건드리지 말 것
   - `launchctl load/unload` 실행 금지

4. **토큰 파일 교체 금지**
   - `~/.claude/channels/telegram/.env` 의 TELEGRAM_BOT_TOKEN 재생성 금지
   - (로보99는 `~/robo99_hq/secrets/telegram_token.txt`를 우선 읽지만
     공유 토큰이 바뀌면 원래 쓰던 다른 도구가 망가질 수 있음)

### 허용되는 것

- 위 경로 **읽기** (상태 확인, 분석, 보고)
- `~/robo99_hq/watchlist.md`, `SYSTEM.md`, `agents/*.md`, `docs/` 읽기·쓰기
- 스케줄러에 문제가 있다고 판단되면 형님에게
  `bash ~/robo99_hq/scripts/start_scheduler.sh --bg` 실행 **안내만** (직접 실행 X)

### 기억할 것

로보99는 자체 Commander 에이전트(`~/robo99_hq/agents/commander.md`)가
관리합니다. openclaw는 **형님을 돕되 로보99 내부는 건드리지 않습니다.**
```

---

### 3. tmux 세션 이름 확인

openclaw가 `robo99` tmux 세션을 열어 Claude Code를 띄웁니다.
이 세션은 **형님과 Claude Code 대화용**이며, 여기서 띄워진 Claude가
아래 규칙에 따라 로보99 시스템을 **조작**할 수는 있습니다 (그게 정상 플로우).

다만 openclaw 자체(= `start_robo99.sh` 바깥의 openclaw 프로세스)는
위 규칙을 따라야 합니다.

```bash
# 상태 확인
tmux list-sessions | grep robo99
ps -ef | grep -E "(openclaw|bun run)"
```

---

### 4. 검증 (설치 후 1회 실행)

```bash
# (a) 토큰 파일 존재 및 권한
ls -la ~/robo99_hq/secrets/telegram_token.txt
# 기대: -rw-------

# (b) lib 모듈 로드 테스트
cd ~/robo99_hq && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from lib import config, telegram
print('✅ config.BASE:', config.BASE)
print('✅ token 길이:', len(config.get_tg_token()))
print('✅ chat_id:', config.TG_CHAT_ID)
"

# (c) 테스트 메시지 전송
cd ~/robo99_hq && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from lib.telegram import send_briefing
send_briefing('🔧 Harness 설치 완료', '로보99는 이제 openclaw와 독립적으로 운영됩니다.')
"
# 기대: 텔레그램으로 📊 메시지 도착
```

---

## 경계 정리 (누가 뭘 소유하는가)

```
┌──────────────────────────────────────────────────────────┐
│ robo99 전용 (쓰기 금지)        양쪽 읽기 가능             │
├──────────────────────────────────────────────────────────┤
│ alerts/*                        watchlist.md              │
│ alerts/cache/*.sqlite           SYSTEM.md                 │
│ tickers/.state/*.yaml           HARNESS.md                │
│ themes/.state/*.yaml            agents/*.md               │
│ state_events/*.jsonl            tickers/*.md (마크다운)   │
│ alerts/.scheduler.lock          themes/active/*.md        │
│ secrets/                        docs/                     │
│ ~/Library/LaunchAgents/         reviews/                  │
│   com.robo99.*.plist            inbox/                    │
├──────────────────────────────────────────────────────────┤
│ openclaw 전용                                              │
├──────────────────────────────────────────────────────────┤
│ ~/.openclaw/workspace_*                                    │
│ tmux "robo99" 세션 수명주기                                │
│ ~/ClaudeCode/scripts/start_robo99.sh                       │
│ ~/.claude/channels/telegram/.env  (공유 토큰, 우리는 독립) │
└──────────────────────────────────────────────────────────┘
```

---

## 문제 발생 시

### "텔레그램이 또 안 와요"

1. 토큰 파일 확인: `cat ~/robo99_hq/secrets/telegram_token.txt | head -c 20`
2. API 상태: `curl -s "https://api.telegram.org/bot$(cat ~/robo99_hq/secrets/telegram_token.txt)/getMe"`
3. 로그: `tail -50 ~/robo99_hq/alerts/scheduler.log`

### "스케줄러가 멈췄어요"

```bash
# 상태 확인 (읽기만, 데몬 만지지 말 것)
bash ~/robo99_hq/scripts/start_scheduler.sh status

# 재시작 필요 시 (형님이 직접)
bash ~/robo99_hq/scripts/start_scheduler.sh --bg
```

### "openclaw가 또 우리 파일을 건드렸어요"

1. `~/robo99_hq/state_events/*.jsonl` 에서 수정 시각 추적
2. openclaw SYSTEM_PROMPT에 위 금지 규칙이 있는지 재확인
3. 반복되면 openclaw가 접근하는 디렉토리를 `chflags uchg`로 보호 (최후의 수단)

---

## 요약 (TL;DR)

1. `bash ~/robo99_hq/scripts/setup_telegram_token.sh` 실행
2. openclaw SYSTEM_PROMPT에 "🚫 ROBO99 파일 간섭 금지" 블록 추가
3. 검증 스크립트 3개 실행하여 연결 확인
4. 끝. 이제 양쪽이 서로 간섭하지 않음.

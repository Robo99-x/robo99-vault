#!/bin/zsh
# telegram_watchdog.sh — tmux 세션 + 텔레그램 봇 헬스체크
# launchd에서 5분마다 자동 실행

SESSION="robo99"
CLAUDE_BIN="$HOME/.local/bin/claude"
CLAUDE_CMD="$CLAUDE_BIN --channels plugin:telegram@claude-plugins-official"
TOKEN_FILE="$HOME/.claude/channels/telegram/.env"
LOG="$HOME/ClaudeCode/scripts/telegram_watchdog.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"; }

# ── 토큰 로드 ──────────────────────────────────────
if [[ ! -f "$TOKEN_FILE" ]]; then
  log "ERROR: .env 없음"
  exit 1
fi
TOKEN=$(grep TELEGRAM_BOT_TOKEN "$TOKEN_FILE" | cut -d= -f2)

# ── Telegram API 연결 확인 ─────────────────────────
API_OK=$(curl -s --max-time 5 "https://api.telegram.org/bot${TOKEN}/getMe" \
  | python3 -c "import sys,json; print('ok' if json.load(sys.stdin).get('ok') else 'fail')" 2>/dev/null)

if [[ "$API_OK" != "ok" ]]; then
  log "ERROR: Telegram API 응답 없음"
  exit 1
fi

# ── tmux 세션 확인 ─────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "OK: tmux 세션 '$SESSION' 실행 중"
else
  log "WARN: tmux 세션 없음. 재시작..."
  tmux new-session -d -s "$SESSION" -x 220 -y 50
  tmux send-keys -t "$SESSION" "cd $HOME && $CLAUDE_CMD" Enter
  log "OK: 세션 재시작 완료"
fi

# ── bun 프로세스 확인 ──────────────────────────────
PLUGIN_DIR="$HOME/.claude/plugins/cache/claude-plugins-official/telegram/0.0.4"
BUN_PIDS=$(pgrep -f "bun run --cwd $PLUGIN_DIR" 2>/dev/null)
BUN_COUNT=$(echo "$BUN_PIDS" | grep -c '[0-9]' 2>/dev/null || echo 0)

if [[ "$BUN_COUNT" -eq 0 ]]; then
  log "WARN: bun 프로세스 없음 (tmux 세션이 Claude를 아직 로드 중일 수 있음)"
elif [[ "$BUN_COUNT" -gt 1 ]]; then
  log "WARN: bun 중복 실행 ($BUN_COUNT개). 구버전 정리..."
  # 가장 최근 PID만 남기고 나머지 종료
  LATEST=$(echo "$BUN_PIDS" | tail -1)
  echo "$BUN_PIDS" | head -n -1 | xargs kill 2>/dev/null
  log "OK: $LATEST 만 유지"
else
  log "OK: bun PID $BUN_PIDS"
fi

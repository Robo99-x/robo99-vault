#!/bin/zsh
# start_robo99.sh — 로보99 텔레그램 채널 세션 시작/재시작
#
# 사용:
#   ./start_robo99.sh          # 세션 시작 (이미 있으면 재접속)
#   ./start_robo99.sh restart  # 강제 재시작
#   ./start_robo99.sh status   # 상태 확인

SESSION="robo99"
CLAUDE_BIN="$HOME/.local/bin/claude"
CLAUDE_CMD="$CLAUDE_BIN --channels plugin:telegram@claude-plugins-official"
LOG="$HOME/ClaudeCode/scripts/robo99_session.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# ── 상태 확인 ──────────────────────────────────────
if [[ "$1" == "status" ]]; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    PID=$(tmux list-panes -t "$SESSION" -F "#{pane_pid}" 2>/dev/null | head -1)
    log "OK: 세션 '$SESSION' 실행 중 (pane PID: $PID)"
    tmux list-panes -t "$SESSION" -F "  pane #{pane_index}: #{pane_current_command}"
  else
    log "WARN: 세션 '$SESSION' 없음"
  fi
  exit 0
fi

# ── 강제 재시작 ────────────────────────────────────
if [[ "$1" == "restart" ]]; then
  log "재시작 요청..."
  tmux kill-session -t "$SESSION" 2>/dev/null && log "기존 세션 종료"
  sleep 1
fi

# ── 세션 시작 ──────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "세션 '$SESSION' 이미 실행 중. 재접속합니다."
  tmux attach-session -t "$SESSION"
else
  log "새 세션 '$SESSION' 시작..."
  tmux new-session -d -s "$SESSION" -x 220 -y 50
  tmux send-keys -t "$SESSION" "cd $HOME && $CLAUDE_CMD" Enter
  log "세션 시작 완료. 접속합니다."
  sleep 1
  tmux attach-session -t "$SESSION"
fi

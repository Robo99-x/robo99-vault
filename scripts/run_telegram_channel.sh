#!/bin/zsh
# run_telegram_channel.sh
# launchd KeepAlive가 이 스크립트를 직접 관리.
# tmux 세션 안에서 Claude 채널을 실행하고,
# 세션이 종료되면 이 스크립트도 종료 → launchd가 즉시 재시작.

SESSION="robo99"
CLAUDE_BIN="$HOME/.local/bin/claude"
CLAUDE_CMD="$CLAUDE_BIN --dangerously-skip-permissions --channels plugin:telegram@claude-plugins-official"
LOG="$HOME/robo99_hq/alerts/telegram_channel.log"

# launchd와 사용자 터미널이 동일한 tmux 소켓 사용하도록 명시
export TMUX_TMPDIR="/tmp/tmux-$(id -u)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"; }

log "채널 시작 요청"

# 기존 세션 정리
if tmux has-session -t "$SESSION" 2>/dev/null; then
    log "기존 세션 종료 후 재시작"
    tmux kill-session -t "$SESSION" 2>/dev/null
    sleep 1
fi

# 새 tmux 세션에서 Claude 실행 (send-keys로 명령어 전달 — 인수 파싱 문제 회피)
tmux new-session -d -s "$SESSION" -x 220 -y 50
tmux send-keys -t "$SESSION" "$CLAUDE_CMD" Enter
sleep 3
log "세션 '$SESSION' 시작 완료"

# tmux 세션이 살아있는 동안 대기 — 종료되면 이 스크립트도 종료
while tmux has-session -t "$SESSION" 2>/dev/null; do
    sleep 5
done

log "세션 종료 감지 — launchd가 재시작합니다"
exit 0

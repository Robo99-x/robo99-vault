#!/usr/bin/env bash
# start_scheduler.sh — 스케줄러 단일 시작점
#
# openclaw 이 아닌 이 스크립트를 통해서만 scheduler_daemon.py 를 실행할 것.
# 이 스크립트는 필요한 모든 의존성을 uv ephemeral 환경으로 명시하므로
# 시스템 Python 상태나 openclaw 환경에 영향받지 않는다.
#
# 사용:
#   bash ~/robo99_hq/scripts/start_scheduler.sh         # foreground
#   bash ~/robo99_hq/scripts/start_scheduler.sh --bg     # background (nohup)

set -euo pipefail

HQ_DIR="${HQ_DIR:-$HOME/robo99_hq}"
cd "$HQ_DIR/scripts"

# uv 경로 해석
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
elif [ -x "/opt/homebrew/bin/uv" ]; then
  UV_BIN="/opt/homebrew/bin/uv"
else
  echo "uv 없음. 'curl -LsSf https://astral.sh/uv/install.sh | sh'" >&2
  exit 127
fi

DEPS="--with pyyaml --with requests --with apscheduler --with pytz"

if [ "${1:-}" = "--bg" ]; then
  echo "[$(date)] 스케줄러 백그라운드 시작"
  nohup "$UV_BIN" run $DEPS python scheduler_daemon.py \
    > "$HQ_DIR/alerts/scheduler.log" \
    2> "$HQ_DIR/alerts/scheduler.err" &
  echo "PID: $!"
else
  echo "[$(date)] 스케줄러 포그라운드 시작 (Ctrl+C 종료)"
  exec "$UV_BIN" run $DEPS python scheduler_daemon.py
fi

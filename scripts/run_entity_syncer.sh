#!/usr/bin/env bash
# entity_syncer 실행 래퍼.
# - uv 의 ephemeral 환경으로 pyyaml 을 매번 주입해 실행한다.
# - pyproject.toml 을 건드리지 않으므로 다른 uv 프로젝트와 충돌하지 않는다.
# - 수동 실행과 launchd 에서 동일하게 호출할 수 있다.
#
# 사용:
#   bash scripts/run_entity_syncer.sh              # 실제 실행
#   bash scripts/run_entity_syncer.sh --dry-run    # 드라이런

set -euo pipefail

HQ_DIR="${HQ_DIR:-$HOME/robo99_hq}"
cd "$HQ_DIR"

# uv 경로 해석 (launchd 는 PATH 가 최소라 풀패스 필요할 수 있음)
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
elif [ -x "/opt/homebrew/bin/uv" ]; then
  UV_BIN="/opt/homebrew/bin/uv"
else
  echo "uv 가 설치되어 있지 않습니다. 'curl -LsSf https://astral.sh/uv/install.sh | sh' 로 설치하세요." >&2
  exit 127
fi

LOG_DIR="$HQ_DIR/alerts/logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG_FILE="$LOG_DIR/entity_syncer_${TS}.log"

echo "[$(date)] entity_syncer 시작 ($*)" | tee -a "$LOG_FILE"
"$UV_BIN" run --with pyyaml python scripts/entity_syncer.py "$@" 2>&1 | tee -a "$LOG_FILE"
STATUS=${PIPESTATUS[0]}
echo "[$(date)] 종료 code=$STATUS" | tee -a "$LOG_FILE"
exit "$STATUS"

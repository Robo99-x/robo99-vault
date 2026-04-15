#!/bin/zsh
# setup_telegram_token.sh — 로보99 독립 텔레그램 토큰 설정
#
# 목적:
#   openclaw가 공유하는 ~/.claude/channels/telegram/.env 에 의존하지 않고
#   로보99 시스템이 자체적으로 토큰을 소유하도록 secrets/telegram_token.txt 생성.
#
# 사용:
#   bash ~/robo99_hq/scripts/setup_telegram_token.sh
#
# 멱등성:
#   이미 secrets/telegram_token.txt가 존재하면 덮어쓸지 물어봄.

set -e

SECRETS_DIR="$HOME/robo99_hq/secrets"
TARGET="$SECRETS_DIR/telegram_token.txt"
SOURCE="$HOME/.claude/channels/telegram/.env"

# ── 디렉토리 보장 ──────────────────────────────────
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# ── 기존 파일 체크 ─────────────────────────────────
if [[ -f "$TARGET" ]]; then
  echo "⚠️  이미 존재: $TARGET"
  echo -n "덮어쓸까요? (y/N): "
  read -r ans
  if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
    echo "중단."
    exit 0
  fi
fi

# ── 소스 확인 ──────────────────────────────────────
if [[ ! -f "$SOURCE" ]]; then
  echo "❌ 소스 파일 없음: $SOURCE"
  echo ""
  echo "대안 1: 토큰을 직접 입력"
  echo -n "TELEGRAM_BOT_TOKEN 값을 붙여넣으세요 (빈 줄이면 중단): "
  read -r manual_token
  if [[ -z "$manual_token" ]]; then
    echo "중단."
    exit 1
  fi
  TOKEN="$manual_token"
else
  # ── .env에서 추출 ──────────────────────────────
  TOKEN=$(grep '^TELEGRAM_BOT_TOKEN' "$SOURCE" | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
  if [[ -z "$TOKEN" ]]; then
    echo "❌ $SOURCE 에서 TELEGRAM_BOT_TOKEN 추출 실패"
    exit 1
  fi
  echo "✅ 소스에서 토큰 추출 완료 (길이: ${#TOKEN})"
fi

# ── 토큰 검증 (Telegram API) ───────────────────────
echo "🔍 토큰 유효성 확인 중..."
API_RESULT=$(curl -s --max-time 5 "https://api.telegram.org/bot${TOKEN}/getMe" || echo '{}')
OK=$(echo "$API_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null)

if [[ "$OK" != "True" ]]; then
  echo "❌ Telegram API 검증 실패"
  echo "응답: $API_RESULT"
  echo -n "그래도 저장할까요? (y/N): "
  read -r force
  if [[ "$force" != "y" && "$force" != "Y" ]]; then
    exit 1
  fi
else
  BOT_USERNAME=$(echo "$API_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['username'])")
  echo "✅ 봇 확인: @$BOT_USERNAME"
fi

# ── 저장 ───────────────────────────────────────────
printf '%s' "$TOKEN" > "$TARGET"
chmod 600 "$TARGET"

echo ""
echo "✅ 저장 완료: $TARGET"
echo "   권한: $(stat -f '%Sp' "$TARGET")"
echo "   크기: $(wc -c < "$TARGET") bytes"
echo ""
echo "🎯 이제 lib/config.py가 이 파일을 최우선으로 사용합니다."
echo "   (openclaw의 ~/.claude/channels/telegram/.env 와 독립)"

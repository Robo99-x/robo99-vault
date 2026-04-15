#!/bin/bash
# setup_git_vault.sh — robo99_hq git 초기화 및 GitHub 연결
#
# 사용법:
#   1. GitHub에서 private repo 생성 (예: robo99-vault)
#   2. 아래 GITHUB_URL에 URL 입력
#   3. cd ~/robo99_hq && bash scripts/setup_git_vault.sh
#
# ────────────────────────────────────────────────
GITHUB_URL="https://github.com/Robo99-x/robo99-vault.git"
# ────────────────────────────────────────────────

set -e
cd "$(dirname "$0")/.."
VAULT_DIR="$(pwd)"
echo "📂 볼트 경로: $VAULT_DIR"

# 1) index.lock 제거 (이전 충돌 정리)
if [ -f ".git/index.lock" ]; then
    echo "🔓 index.lock 제거..."
    rm -f .git/index.lock
fi

# 2) 기존 git 히스토리 초기화 (eco-moat-ai 잔재 제거)
echo "🗑️  기존 .git 초기화..."
rm -rf .git
git init
git checkout -b main

# 3) remote 설정
if [ "$GITHUB_URL" = "https://github.com/YOUR_USERNAME/robo99-vault.git" ]; then
    echo ""
    echo "⚠️  GITHUB_URL을 먼저 설정해주세요."
    echo "   이 스크립트 상단의 GITHUB_URL 변수를 실제 GitHub repo URL로 변경 후 재실행."
    exit 1
fi

echo "🔗 remote 설정: $GITHUB_URL"
git remote add origin "$GITHUB_URL"

# 4) 첫 커밋
echo "📦 파일 스테이징..."
git add .
echo "✅ 스테이징 완료:"
git status --short | wc -l
echo "개 파일"

git commit -m "chore: robo99_hq v2 초기 커밋 (2026-04-15)

- Phase A-D 인프라 리팩토링 완료
  - lib/ (config, db, telegram, claude_runner) 단일 진입점
  - 모든 스크립트 하드코딩 경로 제거
  - SQLite fd 누수 수정 (with db.connect() 패턴)
  - Telegram 구현체 통합 (lib/telegram.py)
- entity_syncer.py: 사람↔기계 영역 동기화 엔진
- vault_writer.py: premarket/theme briefing → Obsidian 파일 저장
- weekly_market_upgrade.py: 히트레이트 + 시장 레짐 분석
- tickers/: ACTIVE watchlist 사람 레이어(.md) 초기 생성
"

# 5) GitHub 푸시
echo ""
echo "🚀 GitHub 푸시..."
git push -u origin main

echo ""
echo "✅ 완료! GitHub 저장소: $GITHUB_URL"
echo ""
echo "다음 단계 (Windows Obsidian):"
echo "  1. Obsidian 커뮤니티 플러그인 → Obsidian Git 설치"
echo "  2. 설정 → Obsidian Git → Remote: $GITHUB_URL"
echo "  3. Pull interval: 10분 권장"

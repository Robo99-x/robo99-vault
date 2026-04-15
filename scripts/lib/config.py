"""
lib/config.py — robo99_hq 전역 설정

모든 경로, 상수, 토큰 로딩을 여기서 관리한다.
다른 모듈은 직접 Path 조합이나 토큰 파일 읽기를 하지 않는다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ── 경로 ──────────────────────────────────────────────────
BASE = Path.home() / "robo99_hq"
SCRIPTS = BASE / "scripts"
ALERTS = BASE / "alerts"
CACHE_DIR = ALERTS / "cache"
CACHE_DB = CACHE_DIR / "krx_cache.sqlite"
STATE_DIR = BASE / "tickers" / ".state"
SECRETS = BASE / "secrets"
LOG_DIR = ALERTS  # scheduler.log, scheduler.err 등

# ── 텔레그램 ─────────────────────────────────────────────
TG_CHAT_ID = "1883449676"

_tg_token_cache: str = ""


def get_tg_token() -> str:
    """텔레그램 봇 토큰 로딩. 우선순위:
    1. 환경변수 TELEGRAM_BOT_TOKEN
    2. ~/robo99_hq/secrets/telegram_token.txt  (우리 전용)
    3. ~/.claude/channels/telegram/.env         (openclaw 공유, fallback)
    4. ~/robo99_hq/secrets/config.json          (레거시)
    """
    global _tg_token_cache
    if _tg_token_cache:
        return _tg_token_cache

    # 1. 환경변수
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    # 2. 우리 전용 토큰 파일
    if not token:
        own_token = SECRETS / "telegram_token.txt"
        if own_token.exists():
            token = own_token.read_text().strip()

    # 3. openclaw 공유 (.env 파일)
    if not token:
        env_path = Path.home() / ".claude" / "channels" / "telegram" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    # 4. 레거시 config.json
    if not token:
        cfg_path = SECRETS / "config.json"
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text())
                token = data.get("channels", {}).get("telegram", {}).get("botToken", "")
            except Exception:
                pass

    _tg_token_cache = token
    return token


# ── 스크립트 타임아웃 설정 ─────────────────────────────
SCRIPT_TIMEOUTS = {
    "collect_market_data.py": 600,
    "stage2_scanner.py": 480,
    "rs_ranking.py": 300,
    "geek_filter.py": 120,
    "stage2_briefing.py": 120,
    "vcp_scanner.py": 180,
    "theme_volume_screener.py": 120,
}
DEFAULT_SCRIPT_TIMEOUT = 300
CLAUDE_TIMEOUT = 600

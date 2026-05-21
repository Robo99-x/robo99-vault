#!/usr/bin/env python3
"""
consensus_monitor.py — 애널 채널 메시지 수집기

지정된 텔레그램 채널을 모니터링하고 새 메시지를
40_consensus/raw/{channel_name}/YYYY/MM/DD/ 에 저장한다.

실행:
  tmux new-session -d -s consensus "cd ~/robo99_hq/scripts && uv run python consensus_monitor.py"
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.config import BASE, SECRETS

KST_OFFSET = 9 * 3600  # UTC+9

# ── 로깅 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(BASE / "alerts" / "consensus_monitor.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("consensus_monitor")

# ── 설정 ──────────────────────────────────────────────────
CONSENSUS_DIR = BASE / "40_consensus" / "raw"
SESSION_FILE = SECRETS / "telethon_session"

# 모니터링할 채널 목록 (채널명: 저장 디렉토리명)
CHANNELS: dict[str, str] = {
    "merITz_tech": "meritz_tech",
    "cahier_de_market": "cahier_de_market",
}


def _load_credentials() -> tuple[int, str]:
    """secrets/telethon.env → (api_id, api_hash)."""
    env_file = SECRETS / "telethon.env"
    api_id = api_hash = None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELETHON_API_ID="):
            api_id = int(line.split("=", 1)[1].strip())
        elif line.startswith("TELETHON_API_HASH="):
            api_hash = line.split("=", 1)[1].strip()
    if not api_id or not api_hash:
        raise ValueError("secrets/telethon.env에 TELETHON_API_ID / TELETHON_API_HASH 없음")
    return api_id, api_hash


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """메시지 앞부분에서 파일명용 텍스트 추출."""
    text = re.sub(r"[^\w가-힣]", "_", text[:max_len]).strip("_")
    return text or "msg"


def _message_to_markdown(msg, channel_name: str) -> str:
    """Telethon Message → markdown 문자열."""
    # KST 시각
    ts_utc = msg.date.replace(tzinfo=timezone.utc)
    ts_kst = ts_utc.timestamp() + KST_OFFSET
    kst_str = datetime.fromtimestamp(ts_kst).strftime("%Y-%m-%dT%H:%M:%S")

    text = msg.text or ""
    # 발신자 정보
    sender = ""
    if hasattr(msg, "post_author") and msg.post_author:
        sender = msg.post_author
    elif hasattr(msg, "sender") and msg.sender:
        s = msg.sender
        sender = getattr(s, "username", None) or getattr(s, "first_name", "") or ""

    frontmatter = (
        f"---\n"
        f"source: telegram\n"
        f"channel: {channel_name}\n"
        f"message_id: {msg.id}\n"
        f"date: {kst_str[:10]}\n"
        f"datetime: {kst_str} KST\n"
        f"sender: {sender}\n"
        f"processed: false\n"
        f"---\n\n"
    )
    return frontmatter + text


async def run():
    from telethon import TelegramClient, events

    api_id, api_hash = _load_credentials()
    client = TelegramClient(str(SESSION_FILE), api_id, api_hash)

    await client.start()
    log.info(f"텔레그램 로그인 완료 | 모니터링 채널: {list(CHANNELS.keys())}")

    @client.on(events.NewMessage(chats=list(CHANNELS.keys())))
    async def handler(event):
        msg = event.message
        if not msg.text:
            return  # 텍스트 없는 메시지(사진 등) 스킵

        # 채널명 → 저장 디렉토리명 매핑
        chat = await event.get_chat()
        chat_username = getattr(chat, "username", "") or ""
        dir_name = CHANNELS.get(chat_username) or CHANNELS.get(chat_username.lower()) or chat_username.lower()

        # 저장 경로
        ts_kst = datetime.fromtimestamp(msg.date.timestamp() + KST_OFFSET)
        out_dir = CONSENSUS_DIR / dir_name / ts_kst.strftime("%Y/%m/%d")
        out_dir.mkdir(parents=True, exist_ok=True)

        short = _sanitize_filename(msg.text)
        filename = f"{ts_kst.strftime('%H%M%S')}_{msg.id}_{short}.md"
        filepath = out_dir / filename

        if filepath.exists():
            return  # 중복 방지

        content = _message_to_markdown(msg, dir_name)
        filepath.write_text(content, encoding="utf-8")
        log.info(f"저장: {filepath.relative_to(BASE)}")

    log.info("모니터링 시작 — Ctrl+C로 종료")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(run())

"""
lib/telegram.py — robo99_hq 통합 텔레그램 모듈

전체 시스템에서 텔레그램 메시지를 보내는 유일한 모듈.
다른 스크립트는 직접 requests.post(...telegram...) 하지 않는다.

사용법:
    from lib import telegram

    telegram.send("안녕하세요")
    telegram.send_alert("stage2_scanner", "Too many open files 에러")
    telegram.send_briefing("장전 브리핑", body_text)
"""
from __future__ import annotations

import logging
import time

from lib.config import TG_CHAT_ID, get_tg_token

log = logging.getLogger("telegram")


def send(text: str, chat_id: str = TG_CHAT_ID) -> bool:
    """텔레그램 메시지 전송. 4000자 초과 시 자동 분할.

    Returns:
        성공 여부
    """
    token = get_tg_token()
    if not token:
        log.warning("텔레그램 토큰 없음 — 전송 불가")
        return False

    try:
        import requests

        chunks = _split_message(text, max_len=4000)
        for chunk in chunks:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=15,
            )
            if not resp.ok:
                log.error(f"텔레그램 전송 실패: {resp.status_code} {resp.text[:200]}")
                return False
            time.sleep(0.3)  # rate limit 방지
        return True
    except Exception as e:
        log.error(f"텔레그램 전송 예외: {e}")
        return False


def send_alert(title: str, detail: str, chat_id: str = TG_CHAT_ID) -> bool:
    """⚠️ 경고/실패 알림 전송.

    Usage:
        telegram.send_alert("stage2_scanner", "OSError: Too many open files")
    """
    from datetime import datetime

    now = datetime.now().strftime("%H:%M")
    text = f"⚠️ [{now}] {title}\n{detail[:500]}"
    return send(text, chat_id)


def send_briefing(title: str, body: str, chat_id: str = TG_CHAT_ID) -> bool:
    """📊 브리핑 메시지 전송.

    Usage:
        telegram.send_briefing("장전 브리핑", rendered_markdown_body)
    """
    text = f"📊 {title}\n\n{body}"
    return send(text, chat_id)


def is_configured() -> bool:
    """텔레그램 토큰이 설정되어 있는지 확인."""
    return bool(get_tg_token())


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """긴 메시지를 줄 단위로 분할. 단일 줄이 max_len 초과해도 안전."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        # 단일 줄이 max_len 초과하면 강제 분할
        while len(line) > max_len:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:max_len])
            line = line[max_len:]
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks

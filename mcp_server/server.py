#!/usr/bin/env python3
"""
robo99_hq MCP Server — stdio 방식 자체 MCP 서버

Claude Code 시작 시 자동으로 프로세스가 뜨고, 외부 연결 없이
로컬에서 실행되어 끊김 없는 안정적 운영.

도구:
  telegram_send       — 텔레그램 메시지 발송
  telegram_send_alert — 텔레그램 경고 알림 발송
  watchlist_read      — watchlist.md 전문 조회
  log_append          — log.md append-only 기록
  pending_msgs_get    — 텔레그램 수신 대기 메시지 조회
  inbox_write         — 00_inbox/ raw 파일 저장

등록:
  ~/.claude/settings.json 의 mcpServers 키에 아래 추가:
  {
    "mcpServers": {
      "robo99": {
        "command": "/Users/robo99/robo99_hq/scripts/.venv/bin/python",
        "args": ["/Users/robo99/robo99_hq/mcp_server/server.py"]
      }
    }
  }
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# robo99_hq scripts를 sys.path에 추가
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions

BASE = Path(__file__).resolve().parent.parent
INBOX_DIR = BASE / "00_inbox"
LOG_FILE = BASE / "log.md"
PENDING_FILE = BASE / "mcp_server" / "pending_msgs.jsonl"

app = Server("robo99-hq")


# ── 도구 목록 ──────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="telegram_send",
            description="텔레그램으로 메시지 발송. 형님에게 브리핑·알림 전송 시 사용.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "보낼 메시지 (3800자 이내 권장)"},
                    "chat_id": {"type": "string", "description": "채팅 ID (기본: 1883449676)"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="telegram_send_alert",
            description="텔레그램 경고 알림 발송. 시스템 오류·장애 시 사용.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "알림 제목"},
                    "detail": {"type": "string", "description": "상세 내용"},
                },
                "required": ["title", "detail"],
            },
        ),
        types.Tool(
            name="watchlist_read",
            description="watchlist.md 전문 조회. 현재 ACTIVE/MONITORING 종목 확인 시 사용.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="log_append",
            description="log.md에 이벤트 기록 (append-only). INGEST/DRAFT/CONFIRM/INTEGRATE/SKIP/CIO_SESSION 등.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "액션 코드 (INGEST, DRAFT, CONFIRM, INTEGRATE, SKIP, CIO_SESSION 등)"},
                    "description": {"type": "string", "description": "설명"},
                },
                "required": ["action", "description"],
            },
        ),
        types.Tool(
            name="pending_msgs_get",
            description="텔레그램 수신 대기 메시지 조회. 폴링 데몬이 저장한 미처리 메시지 목록 반환.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mark_read": {"type": "boolean", "description": "조회 후 읽음 처리 여부 (기본: false)"},
                },
            },
        ),
        types.Tool(
            name="inbox_write",
            description="00_inbox/ 에 raw 파일 저장. 뉴스/공시 ingest 시 사용.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "저장할 원문 내용"},
                    "source": {"type": "string", "description": "출처 (telegram/manual 등)"},
                },
                "required": ["content"],
            },
        ),
    ]


# ── 도구 실행 ──────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "telegram_send":
            result = await _telegram_send(arguments)
        elif name == "telegram_send_alert":
            result = await _telegram_send_alert(arguments)
        elif name == "watchlist_read":
            result = await _watchlist_read()
        elif name == "log_append":
            result = await _log_append(arguments)
        elif name == "pending_msgs_get":
            result = await _pending_msgs_get(arguments)
        elif name == "inbox_write":
            result = await _inbox_write(arguments)
        else:
            result = f"알 수 없는 도구: {name}"
    except Exception as e:
        result = f"오류: {e}"

    return [types.TextContent(type="text", text=str(result))]


# ── 구현 ──────────────────────────────────────────────────────

async def _telegram_send(args: dict) -> str:
    from lib import telegram
    text = args["text"]
    chat_id = args.get("chat_id", "1883449676")
    ok = telegram.send(text, chat_id=chat_id)
    return "발송 완료" if ok else "발송 실패 (토큰 확인 필요)"


async def _telegram_send_alert(args: dict) -> str:
    from lib import telegram
    ok = telegram.send_alert(args["title"], args["detail"])
    return "알림 발송 완료" if ok else "알림 발송 실패"


async def _watchlist_read() -> str:
    wl = BASE / "watchlist.md"
    if not wl.exists():
        return "watchlist.md 없음"
    return wl.read_text(encoding="utf-8")


async def _log_append(args: dict) -> str:
    action = args["action"].upper()
    desc = args["description"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    line = f"\n## [{now}] {action} {desc}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    return f"log.md 기록: {line.strip()}"


async def _pending_msgs_get(args: dict) -> str:
    mark_read = args.get("mark_read", False)
    if not PENDING_FILE.exists():
        return "대기 메시지 없음"

    lines = [l.strip() for l in PENDING_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    unread = []
    for line in lines:
        try:
            msg = json.loads(line)
            if not msg.get("read"):
                unread.append(msg)
        except Exception:
            pass

    if not unread:
        return "대기 메시지 없음"

    if mark_read:
        # 모두 read 처리
        all_msgs = []
        for line in lines:
            try:
                msg = json.loads(line)
                msg["read"] = True
                all_msgs.append(json.dumps(msg, ensure_ascii=False))
            except Exception:
                all_msgs.append(line)
        PENDING_FILE.write_text("\n".join(all_msgs) + "\n", encoding="utf-8")

    result = f"대기 메시지 {len(unread)}건:\n"
    for msg in unread:
        result += f"[{msg.get('ts', '')}] {msg.get('user', '')} — {msg.get('text', '')[:200]}\n"
    return result


async def _inbox_write(args: dict) -> str:
    content = args["content"]
    source = args.get("source", "manual")
    now = datetime.now()
    day_dir = INBOX_DIR / now.strftime("%Y/%m/%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    ts = now.strftime("%Y-%m-%d-%H%M%S")
    fname = f"{ts}-{source}-raw.md"
    path = day_dir / fname

    fm = f"---\nsource: {source}\ndate: {now.strftime('%Y-%m-%d')}\ndatetime: {now.strftime('%Y-%m-%dT%H:%M:%S')} KST\nprocessed: false\n---\n\n{content}"
    path.write_text(fm, encoding="utf-8")
    return f"저장: {path.relative_to(BASE)}"


# ── 메인 ──────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="robo99-hq",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
check_mcp_health.py — MCP 서버 및 텔레그램 연결 상태 점검

job_system_health()에서 호출. 결과를 stdout으로 출력하고
문제 있으면 텔레그램 알림 발송.

점검 항목:
  1. robo99 MCP 서버 프로세스 상태
  2. 텔레그램 봇 API 연결 (getMe ping)
  3. 텔레그램 토큰 유효성
  4. pending_msgs.jsonl 적체 여부
  5. 07:00~23:00 사이 텔레그램 발송 실패 기록
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.config import BASE, get_tg_token
from lib import telegram

MCP_SERVER = BASE / "mcp_server" / "server.py"
PENDING_FILE = BASE / "mcp_server" / "pending_msgs.jsonl"
TODAY = date.today().isoformat()


def check_mcp_process() -> tuple[bool, str]:
    """robo99 MCP 서버 프로세스 실행 여부. 스케줄러 외부 실행 시 없어도 정상."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", str(MCP_SERVER)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split()
            return True, f"실행 중 (PID: {', '.join(pids)})"
        # Claude Code 세션 밖(스케줄러)에서 실행 시 없는 게 정상 → True 처리
        return True, "비활성 (Claude Code 세션 시작 시 자동 로드)"
    except Exception as e:
        return False, f"확인 실패: {e}"


def check_telegram_api() -> tuple[bool, str]:
    """텔레그램 Bot API ping (getMe)."""
    try:
        import requests
        token = get_tg_token()
        if not token:
            return False, "토큰 없음"
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10
        )
        if resp.ok:
            name = resp.json().get("result", {}).get("username", "?")
            return True, f"연결 OK (@{name})"
        return False, f"API 오류: {resp.status_code}"
    except Exception as e:
        return False, f"연결 실패: {e}"


def check_pending_msgs() -> tuple[bool, str]:
    """pending_msgs.jsonl 적체 여부."""
    if not PENDING_FILE.exists():
        return True, "파일 없음 (정상)"
    try:
        lines = [l.strip() for l in PENDING_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        unread = sum(1 for l in lines if not json.loads(l).get("read", False))
        if unread > 10:
            return False, f"미처리 메시지 {unread}건 적체"
        return True, f"미처리 {unread}건 (정상)"
    except Exception as e:
        return False, f"파싱 오류: {e}"


def check_scheduler_log_alerts() -> tuple[bool, str]:
    """오늘 스케줄러 로그에서 텔레그램 관련 실패 카운트."""
    log_file = BASE / "alerts" / "scheduler.log"
    if not log_file.exists():
        return True, "로그 없음"
    try:
        count = 0
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if TODAY in line and ("텔레그램 전송 실패" in line or "telegram" in line.lower() and "fail" in line.lower()):
                count += 1
        if count > 0:
            return False, f"오늘 텔레그램 발송 실패 {count}건"
        return True, "발송 실패 없음"
    except Exception as e:
        return False, f"로그 읽기 오류: {e}"


def main() -> int:
    now = datetime.now().strftime("%H:%M")
    checks = [
        ("robo99 MCP 프로세스", check_mcp_process()),
        ("텔레그램 API 연결", check_telegram_api()),
        ("수신 대기 메시지", check_pending_msgs()),
        ("텔레그램 발송 실패", check_scheduler_log_alerts()),
    ]

    ok_count = sum(1 for _, (ok, _) in checks if ok)
    total = len(checks)
    all_ok = ok_count == total

    lines = [f"[MCP/텔레그램 점검 {TODAY} {now}] {ok_count}/{total} OK"]
    for name, (ok, msg) in checks:
        icon = "✅" if ok else "⚠️"
        lines.append(f"{icon} {name}: {msg}")

    report = "\n".join(lines)
    print(report)

    if not all_ok:
        failures = [f"{name}: {msg}" for name, (ok, msg) in checks if not ok]
        telegram.send_alert(
            f"MCP/텔레그램 점검 이상 {TODAY}",
            "\n".join(failures)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
lib/claude_runner.py — Claude CLI wrapper

Claude CLI 호출의 단일 진입점.
재시도, 타임아웃, stdout/stderr 진단을 표준화한다.

사용법:
    from lib import claude_runner

    # 기본 (재시도 2회)
    stdout = claude_runner.run("Read ~/CLAUDE.md ...", "장전 브리핑")

    # JSON 전용 (재시도 + JSON 추출)
    json_str = claude_runner.run_json("Output ONLY JSON ...", "장마감 특징주")
"""
from __future__ import annotations

import logging
import re
import socket
import subprocess
import time

from lib import telegram
from lib.config import BASE, CLAUDE_TIMEOUT

log = logging.getLogger("claude_runner")


def _is_network_up() -> bool:
    """5초 소켓 체크로 인터넷 연결 여부 확인."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("8.8.8.8", 53))
        s.close()
        return True
    except Exception:
        return False


def run(
    prompt: str,
    task_name: str,
    retries: int = 2,
    timeout: int = CLAUDE_TIMEOUT,
    retry_delay: int = 10,
    cwd: str | None = None,
) -> str | None:
    """Claude CLI 실행.

    Args:
        prompt: Claude에 전달할 프롬프트
        task_name: 로그/알림에 표시할 작업명
        retries: 최대 시도 횟수 (기본 2)
        timeout: 타임아웃 초 (기본 600)
        retry_delay: 재시도 간 대기 초 (기본 10)
        cwd: 작업 디렉토리 (기본 BASE)

    Returns:
        성공 시 stdout 텍스트, 실패 시 None
    """
    work_dir = cwd or str(BASE)

    if not _is_network_up():
        log.error(f"[{task_name}] 네트워크 오프라인 — Claude 호출 스킵")
        telegram.send_alert(
            f"네트워크 오프라인:{task_name}",
            "인터넷 연결 없음. Claude 호출 건너뜀.",
        )
        return None

    for attempt in range(1, retries + 1):
        log.info(f"[{task_name}] Claude 시도 {attempt}/{retries}")
        try:
            result = subprocess.run(
                ["claude", "--dangerously-skip-permissions", "-p", prompt],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Rate limit 감지 — 재시도 무의미, 즉시 중단
            if "hit your limit" in result.stdout or "hit your limit" in result.stderr:
                log.warning(f"[{task_name}] Claude 사용량 한도 초과 — 재시도 중단")
                telegram.send_alert(
                    f"Claude 한도 초과:{task_name}",
                    "You've hit your limit. 12pm KST 이후 자동 복구.",
                )
                return None

            if result.returncode == 0 and result.stdout.strip():
                log.info(
                    f"[{task_name}] 완료 (stdout {len(result.stdout)} chars, "
                    f"{_elapsed(result)})"
                )
                return result.stdout

            # 실패 진단 로그
            log.error(
                f"[{task_name}] 시도 {attempt}/{retries} 실패: "
                f"exit={result.returncode}, "
                f"stdout={len(result.stdout)}chars "
                f"(첫 200자: {result.stdout[:200]!r}), "
                f"stderr={result.stderr[:300] or '(empty)'}"
            )

        except subprocess.TimeoutExpired:
            log.error(f"[{task_name}] 시도 {attempt}/{retries} 타임아웃 ({timeout}초)")

        except Exception as e:
            log.error(f"[{task_name}] 시도 {attempt}/{retries} 예외: {e}")

        if attempt < retries:
            log.info(f"[{task_name}] {retry_delay}초 후 재시도...")
            time.sleep(retry_delay)

    # 모든 시도 실패
    telegram.send_alert(
        f"Claude:{task_name}",
        f"{retries}회 시도 후 최종 실패",
    )
    return None


def run_json(
    prompt: str,
    task_name: str,
    **kwargs,
) -> str | None:
    """Claude CLI 실행 후 JSON 블록을 추출.

    Returns:
        추출된 JSON 문자열, 실패 시 None
    """
    stdout = run(prompt, task_name, **kwargs)
    if stdout is None:
        return None

    json_str = extract_json(stdout)
    if json_str is None:
        log.error(f"[{task_name}] stdout에서 JSON 추출 실패 (길이 {len(stdout)})")
        return None

    return json_str


def extract_json(text: str) -> str | None:
    """Claude stdout에서 JSON 블록 추출.

    지원 형식:
    1. ```json ... ```  코드블록
    2. ``` ... ```      언어 미지정 코드블록
    3. bare { ... }     순수 JSON
    """
    # 1. ```json ... ``` 코드블록
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 2. bare JSON (첫 { ~ 마지막 })
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    # 3. 텍스트 중간에 있는 JSON
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]

    return None


def _elapsed(result: subprocess.CompletedProcess) -> str:
    """실행 시간 추정 (로그용). subprocess는 시간을 안 주므로 근사값."""
    return "time N/A"

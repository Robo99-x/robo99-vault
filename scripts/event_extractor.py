#!/usr/bin/env python3
"""
event_extractor.py — 00_inbox/ raw 파일에서 Event Card 초안 생성

Usage:
    uv run python event_extractor.py <raw_file_path>
    uv run python event_extractor.py 00_inbox/2026/04/29/2026-04-29-174857-telegram-raw.md

처리 흐름:
    1. raw 파일 읽기
    2. LLM(Sonnet)으로 이벤트 메타데이터 JSON 추출
    3. events/YYYY-MM-DD_slug.md 에 Event Card 초안 저장
    4. raw 파일 processed: true 로 업데이트

주의: dedup/판정 없음 (1차 구현). 이후 단계에서 추가 예정.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib import claude_runner
from lib.config import BASE

log = logging.getLogger("event_extractor")

EVENTS_DIR = BASE / "events"

EXTRACT_PROMPT_TEMPLATE = """\
아래는 텔레그램으로 수신한 원문 텍스트입니다.
투자 이벤트 카드를 만들기 위해 핵심 정보를 추출해주세요.

## 원문
{raw_text}

## 지시사항
아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만.
원문에서 확인할 수 없는 필드는 빈 문자열("")로 남기세요.

{{
  "event_date": "YYYY-MM-DD (이벤트 발생일. 불명확하면 오늘 날짜)",
  "event_type": "카테고리 (예: 실적/가이던스, 공시/계약, 임상/파이프라인, 거시/정책, 수급/수출입, 기타)",
  "title": "이벤트 한 줄 제목 (50자 이내)",
  "tickers": ["종목명 (종목코드)" 형식 리스트, 코드 모르면 종목명만],
  "themes": ["관련 테마 키워드 리스트"],
  "what_changed": "무엇이 바뀌었는가 (사실 중심, 3문장 이내)",
  "direct_impact": "직접 영향 — 해당 종목/섹터에 미치는 즉각적 영향",
  "second_order_impact": "2차 영향 — 공급망/경쟁사/연관 테마 영향 (없으면 빈 문자열)",
  "time_horizon": "short (1개월) | medium (3~6개월) | long (6개월+)",
  "confidence": "high | medium | low",
  "source": "출처 정보 (원문에 명시된 매체/날짜)"
}}
"""


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s가-힣-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:40]


def _read_raw(path: Path) -> tuple[str, dict]:
    """raw 파일에서 (body_text, frontmatter_dict) 반환."""
    content = path.read_text(encoding="utf-8")
    # YAML frontmatter 파싱
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
            return body, fm
    return content, {}


def _extract_raw_text(body: str) -> str:
    """## Raw Text 섹션 아래 텍스트 추출."""
    if "## Raw Text" in body:
        return body.split("## Raw Text", 1)[1].strip()
    return body


def _update_raw_frontmatter(path: Path, event_card_path: Path) -> None:
    """raw 파일의 processed, event_card_created 플래그 업데이트."""
    content = path.read_text(encoding="utf-8")
    content = content.replace("processed: false", "processed: true")
    content = content.replace("event_card_created: false", "event_card_created: true")
    # event_card_ref 추가 (없을 때만)
    if "event_card_ref:" not in content:
        content = content.replace(
            "needs_review: true",
            f"needs_review: true\nevent_card_ref: \"{event_card_path}\""
        )
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.rename(tmp.name, path)
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _write_event_card(data: dict, raw_path: Path) -> Path:
    """추출된 JSON으로 events/ Event Card 생성."""
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)

    event_date = data.get("event_date") or datetime.now().strftime("%Y-%m-%d")
    title = data.get("title", "Unknown Event")
    slug = _slugify(title)
    filename = f"{event_date}_{slug}.md"
    out_path = EVENTS_DIR / filename

    tickers_str = ", ".join(data.get("tickers") or []) or ""
    themes_list = data.get("themes") or []
    themes_str = ", ".join(themes_list)

    content = (
        "---\n"
        f"event_date: {event_date}\n"
        f"event_type: {data.get('event_type', '')}\n"
        f"source: \"{data.get('source', '')}\"\n"
        f"tickers: [{tickers_str}]\n"
        f"themes: [{themes_str}]\n"
        "status: DRAFT\n"
        f"raw_input_ref: \"{raw_path}\"\n"
        f"created_at: \"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"\n"
        "---\n\n"
        f"# [Event] {title}\n\n"
        f"## 1. What Changed\n{data.get('what_changed', '')}\n\n"
        f"## 2. Direct Impact\n{data.get('direct_impact', '')}\n\n"
        f"## 3. Second Order Impact\n{data.get('second_order_impact', '')}\n\n"
        f"## 4. Metadata\n"
        f"- **Time Horizon:** {data.get('time_horizon', '')}\n"
        f"- **Confidence:** {data.get('confidence', '')}\n"
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=EVENTS_DIR, delete=False, suffix=".tmp"
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.rename(tmp.name, out_path)
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

    return out_path


def extract(raw_path: Path) -> Path | None:
    """raw 파일 1개 처리 → Event Card 경로 반환."""
    if not raw_path.exists():
        log.error(f"파일 없음: {raw_path}")
        return None

    body, fm = _read_raw(raw_path)
    if fm.get("processed"):
        log.info(f"이미 처리됨: {raw_path}")
        return None

    raw_text = _extract_raw_text(body)
    if not raw_text.strip():
        log.error(f"빈 raw text: {raw_path}")
        return None

    prompt = EXTRACT_PROMPT_TEMPLATE.format(raw_text=raw_text)
    json_str = claude_runner.run_json(prompt, "event_extractor", model="sonnet")
    if not json_str:
        log.error("LLM 추출 실패")
        return None

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        log.error(f"JSON 파싱 실패: {e}\n{json_str[:300]}")
        return None

    event_path = _write_event_card(data, raw_path)
    _update_raw_frontmatter(raw_path, event_path)

    return event_path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python event_extractor.py <raw_file_path>", file=sys.stderr)
        sys.exit(1)

    raw_path = Path(sys.argv[1])
    if not raw_path.is_absolute():
        raw_path = BASE / raw_path

    result = extract(raw_path)
    if result:
        print(f"event_card: {result}")
    else:
        print("ERROR: Event Card 생성 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

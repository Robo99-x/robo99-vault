#!/usr/bin/env python3
"""
vault_writer.py — LLM stdout → 검증 → 렌더링 → atomic write → 텔레그램 전송

CTO 원칙: "LLM 은 파일을 직접 쓰지 않는다."
LLM 은 JSON stdout 만 반환하고, 이 모듈이 아래를 전담한다:
  1. output schema 검증 (schema_models.py)
  2. frontmatter 생성
  3. canonical wikilink 렌더링 (ticker registry 기반)
  4. temp → fsync → rename atomic write
  5. invalid output quarantine
  6. 텔레그램 전송

사용:
  from vault_writer import VaultWriter
  w = VaultWriter(base_dir=Path("~/robo99_hq").expanduser())
  w.write_premarket(validated_dict, run_id="premarket_20260410")
  w.write_theme_screener(validated_dict, run_id="theme_20260410")
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import sys as _sys

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import yaml

from schema_models import (
    SCHEMA_VERSION,
    ValidationError,
    validate_premarket,
    validate_theme_screener,
)

from lib import telegram as _tg  # noqa: E402
from lib.config import TG_CHAT_ID  # noqa: E402

log = logging.getLogger("vault_writer")

# ---------------------------------------------------------------------------
# 텔레그램 — lib.telegram 으로 위임
# ---------------------------------------------------------------------------


def send_telegram(text: str, chat_id: str = TG_CHAT_ID) -> bool:
    """텔레그램 메시지 전송. 성공 여부 반환.

    구현은 lib.telegram.send 에 위임 (4000자 자동 분할, 4레벨 토큰 fallback 포함).
    """
    try:
        return _tg.send(text, chat_id=chat_id)
    except Exception as e:
        log.error(f"텔레그램 전송 예외: {e}")
        return False


# ---------------------------------------------------------------------------
# Ticker Registry — .state 파일명에서 code ↔ name 매핑
# ---------------------------------------------------------------------------

class TickerRegistry:
    """tickers/.state/*.yaml 파일명 규칙(code-name.yaml)에서 레지스트리 구성."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self._code_to_name: dict[str, str] = {}
        self._name_to_code: dict[str, str] = {}
        self._reload()

    def _reload(self):
        self._code_to_name.clear()
        self._name_to_code.clear()
        if not self.state_dir.exists():
            return
        for f in self.state_dir.glob("*.yaml"):
            stem = f.stem  # "005930-삼성전자" or "삼성전자"
            if "-" in stem:
                code, name = stem.split("-", 1)
                self._code_to_name[code] = name
                self._name_to_code[name] = code
            else:
                # name-only file — yaml 내부에서 code 읽기
                try:
                    data = yaml.safe_load(f.read_text()) or {}
                    code = str(data.get("ticker", "")).strip()
                    name = str(data.get("name", stem)).strip()
                    if code:
                        self._code_to_name[code] = name
                    self._name_to_code[name] = code
                except Exception:
                    pass

    def resolve(self, identifier: str) -> tuple[str, str]:
        """code 또는 name → (code, name). 못 찾으면 ("", identifier)."""
        identifier = identifier.strip()
        if identifier in self._code_to_name:
            return identifier, self._code_to_name[identifier]
        if identifier in self._name_to_code:
            return self._name_to_code[identifier], identifier
        return "", identifier

    def wikilink(self, identifier: str) -> str:
        """identifier → [[종목명]] 형태. name 을 우선."""
        _, name = self.resolve(identifier)
        return f"[[{name}]]"

    @property
    def all_names(self) -> set[str]:
        return set(self._name_to_code.keys()) | set(self._code_to_name.values())


# ---------------------------------------------------------------------------
# Atomic write + quarantine
# ---------------------------------------------------------------------------

def atomic_write(path: Path, content: str) -> None:
    """temp → fsync → rename. 중간 실패 시 원본 보존."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.stem}_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except Exception:
        # 실패 시 temp 정리
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def quarantine_output(
    base_dir: Path,
    raw: str,
    task_name: str,
    error: str,
    run_id: str = "",
) -> Path:
    """검증 실패한 LLM 출력을 alerts/quarantine/ 에 보존."""
    q_dir = base_dir / "alerts" / "quarantine"
    q_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rid = run_id or uuid.uuid4().hex[:8]
    fname = f"{ts}_{task_name}_{rid}.json"
    payload = {
        "task_name": task_name,
        "run_id": rid,
        "error": error,
        "raw_output": raw,
        "quarantined_at": datetime.now().isoformat(),
    }
    path = q_dir / fname
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    log.warning(f"quarantine 저장: {path.relative_to(base_dir)}")
    return path


# ---------------------------------------------------------------------------
# 렌더러 — Premarket Briefing
# ---------------------------------------------------------------------------

def render_premarket(data: dict, registry: TickerRegistry) -> tuple[str, str]:
    """검증된 premarket dict → (markdown_full, telegram_text).
    markdown_full 에는 YAML frontmatter + [[wikilink]] 포함.
    telegram_text 에는 wikilink 괄호 제거한 plain text.
    """
    bdate = data["briefing_date"]
    macro = data.get("macro_context", "")
    items = data.get("items", [])
    unchanged = data.get("unchanged_tickers", [])
    top5 = data.get("screener_top5", [])
    scr_date = data.get("screener_date", "")

    # -- frontmatter --
    all_tickers = []
    for it in items:
        name = it.get("ticker_name") or it.get("ticker_code", "")
        if name:
            all_tickers.append(name)
    all_tickers.extend(unchanged)
    for s in top5:
        name = s.get("ticker_name") or s.get("ticker_code", "")
        if name:
            all_tickers.append(name)

    fm = {
        "schema_version": SCHEMA_VERSION,
        "date": bdate,
        "briefing_type": "premarket",
        "generated_at": datetime.now().isoformat(),
        "watchlist_tickers": list(dict.fromkeys(all_tickers)),  # dedup, order-preserving
        "screener_date": scr_date,
    }
    fm_str = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()

    # -- body --
    lines = [f"# 장전 브리핑 — {bdate}", ""]
    if macro:
        lines += ["## 매크로 컨텍스트", "", macro, "", "---", ""]

    lines.append("## Section 1 — ACTIVE 워치리스트 델타")
    lines.append("")

    changed = [it for it in items if it.get("change_type") != "no_change"]
    no_change = [it for it in items if it.get("change_type") == "no_change"]

    if not changed and not unchanged and not no_change:
        lines.append("오늘 장전 기준 신규 정보 없음 — 전일 브리핑과 동일한 관찰 포인트 유지")
        lines.append("")
    else:
        # 변동 있는 종목
        for it in changed:
            name = it.get("ticker_name") or it.get("ticker_code", "???")
            wl = registry.wikilink(name)
            ct = it.get("change_type", "")
            prio = it.get("priority", "")
            reason = it.get("reason", "")
            label = {
                "new_news": "NEW OVERNIGHT NEWS",
                "status_change": "STATUS CHANGE",
                "scheduled": "SCHEDULED TODAY",
            }.get(ct, ct.upper())
            header = f"[{prio}] {label}" if prio else label
            lines.append(f"### {header} — {wl}")
            lines.append("")
            if reason:
                lines.append(f"- {reason}")
            themes = it.get("themes", [])
            if themes:
                lines.append(f"- 테마: {', '.join(themes)}")
            hint = it.get("action_hint", "")
            if hint:
                lines.append(f"- 체크포인트: {hint}")
            lines.append("")

        # 변동 없는 종목
        all_unchanged_names = []
        for it in no_change:
            n = it.get("ticker_name") or it.get("ticker_code", "")
            if n:
                all_unchanged_names.append(n)
        all_unchanged_names.extend(unchanged)
        if all_unchanged_names:
            wikilinks = [registry.wikilink(n) for n in all_unchanged_names]
            lines.append("### 변동없음")
            lines.append("")
            lines.append(" · ".join(wikilinks))
            lines.append("")

    # Section 2 — TOP5
    if top5:
        lines += ["---", "", f"## Section 2 — 전일 특징주 TOP5 ({scr_date} 스크리너)", ""]
        for i, s in enumerate(top5, 1):
            name = s.get("ticker_name") or s.get("ticker_code", "???")
            wl = registry.wikilink(name)
            chg = s.get("change_pct", 0)
            sign = "+" if chg >= 0 else ""
            tv = s.get("trade_value_억", 0)
            tag = s.get("tag", "")
            reapp = " (재등장)" if s.get("is_reappearance") else ""
            cat = s.get("catalyst", "")
            line_parts = [f"{i}. {wl} {sign}{chg}%"]
            if tv:
                line_parts.append(f"거래대금 {tv:,.0f}억")
            if tag:
                line_parts.append(tag)
            line_parts.append(reapp)
            lines.append(" / ".join(p for p in line_parts if p))
            if cat:
                lines.append(f"   {cat}")
        lines.append("")

    lines += [
        "---",
        f"*생성: {datetime.now().strftime('%Y-%m-%d %H:%M')} | vault_writer v{SCHEMA_VERSION} | Delta-only*",
    ]

    md = f"---\n{fm_str}\n---\n\n" + "\n".join(lines)
    tg = _strip_wikilinks("\n".join(lines))
    return md, tg


# ---------------------------------------------------------------------------
# 렌더러 — Theme Screener Briefing
# ---------------------------------------------------------------------------

def render_theme_screener(data: dict, registry: TickerRegistry) -> tuple[str, str]:
    """검증된 theme screener dict → (markdown, telegram_text)."""
    bdate = data["briefing_date"]
    header = data.get("header", f"[{bdate} 특징주 테마별 분류]")
    groups = data.get("groups", [])
    misc = data.get("misc_stocks", [])

    # collect all theme names and ticker names for frontmatter
    all_themes = []
    all_tickers = []
    for g in groups:
        t = g.get("theme", "")
        if t:
            all_themes.append(t)
        for s in g.get("stocks", []):
            n = s.get("ticker_name") or s.get("ticker_code", "")
            if n:
                all_tickers.append(n)
    for s in misc:
        n = s.get("ticker_name") or s.get("ticker_code", "")
        if n:
            all_tickers.append(n)

    fm = {
        "schema_version": SCHEMA_VERSION,
        "briefing_date": bdate,
        "briefing_type": "theme_screener",
        "generated_at": datetime.now().isoformat(),
        "themes": all_themes,
        "tickers": list(dict.fromkeys(all_tickers)),
        "source": "alerts/theme_screener.json",
    }
    fm_str = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()

    lines = [header, "기준: 시총1조↑ +5%↑ / 시총1조↓ +7%↑ | 거래량 20일평균 1.5배↑", ""]

    for g in groups:
        theme = g.get("theme", "???")
        narrative = g.get("narrative", "")
        lines.append(f"━━━ {theme} ━━━")
        if narrative:
            lines.append(narrative)
        for s in g.get("stocks", []):
            lines.append(_format_stock_line(s, registry))
        lines.append("")

    if misc:
        lines.append("━━━ 📌 기타 단독 주요주 ━━━")
        for s in misc:
            cat = s.get("catalyst", "")
            line = _format_stock_line(s, registry)
            if cat:
                line += f" — {cat}"
            lines.append(line)
        lines.append("")

    md = f"---\n{fm_str}\n---\n\n" + "\n".join(lines)
    tg = _strip_wikilinks("\n".join(lines))
    return md, tg


def _format_stock_line(s: dict, registry: TickerRegistry) -> str:
    name = s.get("ticker_name") or s.get("ticker_code", "???")
    wl = registry.wikilink(name)
    chg = s.get("change_pct", 0)
    sign = "+" if chg >= 0 else ""
    vol = s.get("vol_ratio", 0)
    tv = s.get("trade_value_억", 0)
    mc = s.get("market_cap_조", 0)
    tag = s.get("tag", "")
    reapp = " 재등장" if s.get("is_reappearance") else ""
    parts = [f"• {wl} {sign}{chg}%"]
    if vol:
        parts.append(f"거래량 {vol}배")
    if tv:
        parts.append(f"대금 {tv:,.0f}억")
    if mc:
        parts.append(f"(시총 {mc}조)")
    if tag:
        parts.append(tag)
    if reapp:
        parts.append(reapp)
    return " / ".join(parts)


def _strip_wikilinks(text: str) -> str:
    """[[종목명]] → 종목명 (텔레그램 plain text 용)."""
    return re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)


# ---------------------------------------------------------------------------
# VaultWriter — 통합 인터페이스
# ---------------------------------------------------------------------------

class VaultWriter:
    """LLM stdout JSON 을 받아 검증 → 렌더 → 저장 → 전송하는 파이프라인."""

    def __init__(self, base_dir: Path):
        self.base = base_dir
        self.alerts = base_dir / "alerts"
        self.registry = TickerRegistry(base_dir / "tickers" / ".state")

    def process_premarket(
        self,
        raw_json: str,
        run_id: str = "",
    ) -> dict[str, Any]:
        """premarket stdout JSON → 파일 저장 + 텔레그램.

        Returns:
            {"success": bool, "file": str|None, "telegram": bool,
             "warnings": list, "error": str|None, "quarantine": str|None}
        """
        return self._process(
            raw_json=raw_json,
            task_name="premarket",
            validator=validate_premarket,
            renderer=render_premarket,
            path_fn=lambda d: self.alerts / f"premarket_briefing_{d['briefing_date']}.md",
            run_id=run_id,
        )

    def process_theme_screener(
        self,
        raw_json: str,
        run_id: str = "",
    ) -> dict[str, Any]:
        """theme screener stdout JSON → 파일 저장 + 텔레그램."""
        return self._process(
            raw_json=raw_json,
            task_name="theme_screener",
            validator=validate_theme_screener,
            renderer=render_theme_screener,
            path_fn=lambda d: self.alerts / f"theme_briefing_{d['briefing_date']}.md",
            run_id=run_id,
        )

    def _process(
        self,
        raw_json: str,
        task_name: str,
        validator: Callable,
        renderer: Callable,
        path_fn: Callable,
        run_id: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "file": None,
            "telegram": False,
            "warnings": [],
            "error": None,
            "quarantine": None,
        }
        rid = run_id or f"{task_name}_{uuid.uuid4().hex[:8]}"

        # 1. JSON 파싱
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError) as e:
            result["error"] = f"JSON 파싱 실패: {e}"
            qp = quarantine_output(self.base, raw_json, task_name, result["error"], rid)
            result["quarantine"] = str(qp.relative_to(self.base))
            self._alert_failure(task_name, result["error"], rid)
            return result

        # 2. 스키마 검증
        try:
            data, warnings = validator(data)
            result["warnings"] = warnings
        except ValidationError as e:
            result["error"] = f"스키마 검증 실패: {e}"
            qp = quarantine_output(self.base, raw_json, task_name, result["error"], rid)
            result["quarantine"] = str(qp.relative_to(self.base))
            self._alert_failure(task_name, result["error"], rid)
            return result

        # 3. 렌더링
        try:
            self.registry._reload()  # 최신 registry
            md, tg_text = renderer(data, self.registry)
        except Exception as e:
            result["error"] = f"렌더링 실패: {e}"
            qp = quarantine_output(self.base, raw_json, task_name, result["error"], rid)
            result["quarantine"] = str(qp.relative_to(self.base))
            self._alert_failure(task_name, result["error"], rid)
            return result

        # 4. Atomic write
        try:
            out_path = path_fn(data)
            atomic_write(out_path, md)
            result["file"] = str(out_path.relative_to(self.base))
            log.info(f"[{task_name}] 파일 저장: {result['file']}")
        except Exception as e:
            result["error"] = f"파일 저장 실패: {e}"
            self._alert_failure(task_name, result["error"], rid)
            return result

        # 5. 텔레그램 전송
        tg_ok = send_telegram(tg_text)
        result["telegram"] = tg_ok
        if not tg_ok:
            log.warning(f"[{task_name}] 텔레그램 전송 실패 — 파일은 정상 저장됨")

        result["success"] = True
        if warnings:
            log.info(f"[{task_name}] 경고 {len(warnings)}건: {warnings}")
        return result

    def _alert_failure(self, task_name: str, error: str, run_id: str):
        """치명적 실패 시 텔레그램으로 즉시 알림."""
        msg = f"⚠️ vault_writer 실패\n작업: {task_name}\nrun_id: {run_id}\n오류: {error[:400]}"
        send_telegram(msg)

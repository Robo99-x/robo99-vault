#!/usr/bin/env python3
"""
entity_syncer.py — 사람(.md) 과 기계(.state/*.yaml) 영역을 잇는 동기화 엔진.

매일 launchd 로 1회 깨어나 다음을 수행한다:

  (a) alerts/theme_briefing_YYYY-MM-DD.md 및 alerts/theme_screener.json 파싱
      → tickers/.state/<코드>-<이름>.yaml 의 last_seen / appearances 갱신
  (b) reviews/YYYY-MM-DD_*_CIO.md 파싱
      → tickers/.state/*.yaml 의 status / thesis / next_review 갱신
  (c) events/*.md frontmatter + events/.state/*.yaml 비교
      → phase 자동 전이 (active → fading → resolved) 및 누락 yaml 생성
  (d) themes/active/*.md frontmatter 읽어 themes/active/.state/*.yaml 갱신

LLM 호출 0. 순수 Python + PyYAML.
결과 요약은 alerts/entity_syncer_report_YYYY-MM-DD.md 에 기록한다.

사용:
  uv run python scripts/entity_syncer.py
  uv run python scripts/entity_syncer.py --dry-run
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from lib import config as _cfg  # noqa: E402

BASE = _cfg.BASE
TODAY = date.today()
TODAY_S = TODAY.isoformat()
RUN_ID = f"sync_{TODAY_S}_{uuid.uuid4().hex[:6]}"

TICKERS_DIR = BASE / "tickers"
TICKERS_STATE = TICKERS_DIR / ".state"
EVENTS_DIR = BASE / "events"
EVENTS_STATE = EVENTS_DIR / ".state"
THEMES_ACTIVE_DIR = BASE / "themes" / "active"
THEMES_ACTIVE_STATE = THEMES_ACTIVE_DIR / ".state"
ALERTS_DIR = BASE / "alerts"
REVIEWS_DIR = BASE / "reviews"
STATE_EVENTS_DIR = BASE / "state_events"

DEFAULT_EVENT_HORIZON_DAYS = 180
DORMANT_DAYS = 30
FADING_DAYS = 14


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        print(f"  ! YAML 파싱 실패 {path.name}: {e}", file=sys.stderr)
        return {}


def dump_yaml(
    path: Path,
    data: dict,
    dry_run: bool = False,
    *,
    entity_type: str = "",
    entity_id: str = "",
    change_type: str = "update",
    source_ref: str = "",
    old_data: dict | None = None,
) -> None:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    # before_hash 계산
    before_hash = ""
    if old_data is not None:
        before_hash = hashlib.sha256(
            yaml.safe_dump(old_data, allow_unicode=True, sort_keys=True).encode()
        ).hexdigest()[:12]
    after_hash = hashlib.sha256(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=True).encode()
    ).hexdigest()[:12]

    path.write_text(text)

    # append-only event log
    if entity_type and before_hash != after_hash:
        _append_event(
            entity_type=entity_type,
            entity_id=entity_id or path.stem,
            change_type=change_type,
            source_ref=source_ref,
            before_hash=before_hash,
            after_hash=after_hash,
            patch_summary=_diff_summary(old_data or {}, data),
        )


def _append_event(
    entity_type: str,
    entity_id: str,
    change_type: str,
    source_ref: str,
    before_hash: str,
    after_hash: str,
    patch_summary: str,
) -> None:
    """state_events/YYYY-MM.jsonl 에 이벤트 1줄 append."""
    STATE_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    month_file = STATE_EVENTS_DIR / f"{TODAY_S[:7]}.jsonl"
    event = {
        "timestamp": datetime.now().isoformat(),
        "run_id": RUN_ID,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "change_type": change_type,
        "source_ref": source_ref,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "patch_summary": patch_summary,
    }
    with open(month_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _diff_summary(old: dict, new: dict) -> str:
    """변경된 키만 요약 (최대 200자)."""
    changed = []
    all_keys = set(old.keys()) | set(new.keys())
    for k in sorted(all_keys):
        ov = old.get(k)
        nv = new.get(k)
        if ov != nv:
            changed.append(f"{k}: {ov!r} → {nv!r}")
    return "; ".join(changed)[:200]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + 5:]
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def extract_tickers(text: str) -> set[str]:
    """본문에서 [[삼성전자]] 스타일 wikilink 와 'XXXXXX-이름' 코드 추출."""
    names = set(re.findall(r"\[\[([^\[\]|#]+?)(?:\|[^\]]+)?\]\]", text))
    # 단순 한글 종목명 보존
    return {n.strip() for n in names if n.strip()}


def days_between(a: str, b: str) -> int:
    try:
        da = datetime.strptime(a, "%Y-%m-%d").date()
        db = datetime.strptime(b, "%Y-%m-%d").date()
        return (db - da).days
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# (a) theme_briefing / screener → ticker .state
# ---------------------------------------------------------------------------

@dataclass
class SyncReport:
    ticker_touched: list[str] = field(default_factory=list)
    ticker_created: list[str] = field(default_factory=list)
    event_transitions: list[str] = field(default_factory=list)
    theme_touched: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_ticker_state(name: str) -> tuple[Path, dict]:
    """이름으로 .state yaml 찾거나 새로 만든다.

    파일명 규칙: `<코드>-<이름>.yaml` 또는 name 만 있는 경우 `<이름>.yaml`.
    """
    # 기존 파일 탐색 — 이름 매치
    for p in TICKERS_STATE.glob("*.yaml"):
        data = load_yaml(p)
        if data.get("name") == name or p.stem.endswith(f"-{name}"):
            return p, data
    # 신규 — 코드 모르면 이름만 파일명으로
    new_path = TICKERS_STATE / f"{name}.yaml"
    return new_path, {}


TICKER_MD_SECTION = "## 수급 특징주"
_TICKER_MD_SECTION_LEGACY = "## 특징주 기록"   # 구버전 섹션명 (읽기 호환용)
_TICKER_MD_COMMENT = "<!-- entity_syncer가 자동 기록. 아래 내용은 수동 편집 가능. -->"


def _theme_entry(date_str: str, row: dict, themes: list) -> str:
    """테마 스크리너 결과를 날짜별 한 줄로 압축.

    형식: YY/MM/DD [테마] +11.7% 대금463억 거래량4.1x 🚀55일신고가
    """
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(date_str[:10], "%Y-%m-%d")
        date_display = d.strftime("%y/%m/%d")
    except Exception:
        date_display = date_str[:10]

    change    = row.get("change", 0) or 0
    vol_ratio = row.get("vol_ratio", 0) or 0
    trade     = row.get("trade_value_억", 0) or 0
    theme_str = row.get("theme", "") or ", ".join(themes)
    tag       = (row.get("tag") or "").strip()

    theme_part = f" [{theme_str}]" if theme_str else ""
    trade_part = f" 대금{trade:.0f}억" if trade else ""
    tag_part   = f" {tag}" if tag else ""

    return f"{date_display}{theme_part} {change:+.1f}%{trade_part} 거래량{vol_ratio:.1f}x{tag_part}\n"


def ensure_ticker_md(
    name: str,
    ticker: str,
    themes: list,
    screener_row: dict,
    kind: str = "screener",
) -> None:
    """tickers/<name>.md 의 '수급 특징주' 섹션에 날짜별 한 줄 기록을 추가한다.
    테마 스크리너(kind=screener) 이벤트만 기록한다.
    """
    if kind != "screener":
        return  # stage2 등은 .md에 기록하지 않음

    md_path = TICKERS_DIR / f"{name}.md"
    when     = screener_row.get("date", TODAY_S)
    date_key = when[:10]

    entry = _theme_entry(when, screener_row, themes)

    template_path = TICKERS_DIR / "_TEMPLATE.md"
    if not md_path.exists():
        if not template_path.exists():
            return
        body = template_path.read_text(encoding="utf-8")
        body = (
            body
            .replace("{{name}}", name)
            .replace("{{ticker}}", ticker)
            .replace('ticker: ""', f'ticker: "{ticker}"')
            .replace("name: 종목명", f"name: {name}")
            .replace("status: watchlist", "status: monitoring")
        )
        theme_links = " ".join(f"[[{t}]]" for t in themes) if themes else "<!-- 없음 -->"
        body = body.replace("<!-- [[themes/테마명]] -->", theme_links)
        body = body.replace(_TICKER_MD_SECTION_LEGACY, TICKER_MD_SECTION)
        body = body.replace(_TICKER_MD_COMMENT, _TICKER_MD_COMMENT + "\n" + entry)
        md_path.write_text(body, encoding="utf-8")
        return

    content = md_path.read_text(encoding="utf-8")

    # 중복 방지: 같은 날짜 이미 있으면 스킵
    try:
        from datetime import datetime as _dt
        date_display_check = _dt.strptime(date_key, "%Y-%m-%d").strftime("%y/%m/%d")
    except Exception:
        date_display_check = date_key

    if date_display_check and date_display_check in content:
        return

    # 구버전 섹션명을 신규로 마이그레이션
    if _TICKER_MD_SECTION_LEGACY in content and TICKER_MD_SECTION not in content:
        content = content.replace(_TICKER_MD_SECTION_LEGACY, TICKER_MD_SECTION)

    if TICKER_MD_SECTION in content:
        # 섹션 바로 뒤(첫 줄)에 새 항목 삽입
        idx = content.index(TICKER_MD_SECTION) + len(TICKER_MD_SECTION)
        content = content[:idx] + "\n" + entry + content[idx:]
    else:
        content += f"\n{TICKER_MD_SECTION}\n{_TICKER_MD_COMMENT}\n" + entry

    md_path.write_text(content, encoding="utf-8")


def touch_ticker(
    name: str,
    *,
    kind: str,
    ref: str,
    when: str,
    report: SyncReport,
    dry_run: bool,
    extra: dict | None = None,
) -> None:
    path, data = load_ticker_state(name)
    old_data = dict(data)  # snapshot for event log
    created = not path.exists()

    # transient 키 분리 (YAML에 저장하지 않음)
    screener_row = None
    if extra:
        screener_row = extra.pop("_screener_row", None)

    # 코드가 새로 들어오면 파일명을 <코드>-<이름>.yaml 로 표준화
    code_in = (extra or {}).get("ticker")
    if code_in and path.stem == name:
        new_path = TICKERS_STATE / f"{code_in}-{name}.yaml"
        if new_path != path:
            if path.exists() and not dry_run:
                path.rename(new_path)
            path = new_path

    data.setdefault("ticker", "")
    data["name"] = name
    data.setdefault("status", "monitoring")
    data.setdefault("status_since", when)
    data.setdefault("thesis", "")
    data.setdefault("themes", [])
    data.setdefault("catalysts_pending", [])
    data.setdefault("invalidation", "")
    data.setdefault("appearances", [])

    data["last_seen"] = when
    if kind == "theme_briefing":
        data["last_briefed"] = when
    if extra:
        for k, v in extra.items():
            if v:
                data[k] = v

    # appearances 중복 제거 (같은 날 같은 kind 는 1회만)
    app = {"date": when, "kind": kind, "ref": ref}
    if app not in data["appearances"]:
        data["appearances"].append(app)
        # 최근 10개만 유지 (전체 이력은 state_events/ 에)
        data["appearances"] = data["appearances"][-10:]

    dump_yaml(
        path, data, dry_run=dry_run,
        entity_type="ticker",
        entity_id=name,
        change_type="create" if created else "update",
        source_ref=ref,
        old_data=old_data if not created else None,
    )
    if created:
        report.ticker_created.append(name)
    report.ticker_touched.append(name)

    # per-ticker MD 자동 기록 (screener / stage2 이벤트, dry_run 제외)
    if kind in ("screener", "stage2") and screener_row and not dry_run:
        try:
            ensure_ticker_md(
                name=name,
                ticker=data.get("ticker", ""),
                themes=data.get("themes", []),
                screener_row=screener_row,
                kind=kind,
            )
        except Exception as _e:
            report.warnings.append(f"ensure_ticker_md({name}) 실패: {_e}")


def sync_theme_briefing(report: SyncReport, dry_run: bool) -> None:
    """오늘(또는 최근) theme_briefing_*.md 에서 ticker 언급 수집."""
    briefing = ALERTS_DIR / f"theme_briefing_{TODAY_S}.md"
    if not briefing.exists():
        # fallback: 가장 최신
        cands = sorted(ALERTS_DIR.glob("theme_briefing_*.md"))
        if not cands:
            report.warnings.append("theme_briefing 파일 없음")
            return
        briefing = cands[-1]

    text = briefing.read_text()
    m = re.search(r"theme_briefing_(\d{4}-\d{2}-\d{2})", briefing.name)
    when = m.group(1) if m else TODAY_S
    ref = f"alerts/{briefing.name}"

    for name in extract_tickers(text):
        touch_ticker(
            name,
            kind="theme_briefing",
            ref=ref,
            when=when,
            report=report,
            dry_run=dry_run,
        )

    # screener json 병행
    screener = ALERTS_DIR / "theme_screener.json"
    if screener.exists():
        try:
            js = json.loads(screener.read_text())
            # 호환: list | {stocks:[...]} | {results:[...]}
            rows = (
                js if isinstance(js, list)
                else js.get("stocks") or js.get("results") or []
            )
            scr_date = (js.get("date") if isinstance(js, dict) else None) or when
            for row in rows[:30]:
                nm = row.get("name") or row.get("종목명")
                code = str(row.get("ticker") or row.get("code") or "").strip()
                if not nm:
                    continue
                extra: dict = {}
                if code:
                    extra["ticker"] = code
                theme_str = row.get("theme") or ""
                themes: list = []
                if theme_str:
                    # "테마A, 테마B(설명)" → ["테마A","테마B"]
                    themes = [t.split("(")[0].strip() for t in re.split(r"[,/]", theme_str) if t.strip()]
                    if themes:
                        extra["themes"] = themes
                # screener 전체 데이터 전달 (ensure_ticker_md 에서 사용, YAML에는 저장 안 함)
                extra["_screener_row"] = {
                    "date": scr_date,
                    "change": row.get("change"),
                    "vol_ratio": row.get("vol_ratio"),
                    "trade_value_억": row.get("trade_value_억"),
                    "market_cap_조": row.get("market_cap_조"),
                    "rs_proxy": row.get("rs_proxy"),
                    "tag": row.get("tag", ""),
                    "theme": theme_str,
                }
                touch_ticker(
                    nm,
                    kind="screener",
                    ref="alerts/theme_screener.json",
                    when=scr_date,
                    report=report,
                    dry_run=dry_run,
                    extra=extra,
                )
        except json.JSONDecodeError as e:
            report.warnings.append(f"screener json 파싱 실패: {e}")


# ---------------------------------------------------------------------------
# (b) reviews → ticker .state (CIO write-back)
# ---------------------------------------------------------------------------

REVIEW_STATUS_PAT = re.compile(r"(?:^|\n)\s*-?\s*\*{0,2}Decision\*{0,2}\s*:\s*\*{0,2}\s*([A-Za-z_ ]+)")
REVIEW_THESIS_PAT = re.compile(r"(?:^|\n)#+\s*Thesis\s*\n(.+?)(?:\n#+\s|\Z)", re.DOTALL)
REVIEW_INVALID_PAT = re.compile(r"(?:^|\n)#+\s*Invalidat(?:ion|ors?)\s*\n(.+?)(?:\n#+\s|\Z)", re.DOTALL)


def sync_stage2(report: SyncReport, dry_run: bool) -> None:
    """stage2_geek_filtered.json → 각 종목 .md 수급 특징주 섹션에 한 줄 기록."""
    geek_path = ALERTS_DIR / "stage2_geek_filtered.json"
    if not geek_path.exists():
        return
    try:
        rows = json.loads(geek_path.read_text(encoding="utf-8"))
    except Exception as e:
        report.warnings.append(f"stage2_geek_filtered.json 읽기 실패: {e}")
        return

    if not isinstance(rows, list):
        return

    scr_date = TODAY_S
    for row in rows:
        code = str(row.get("ticker") or "").strip()
        nm   = row.get("name") or ""
        if not nm and code:
            # .state에서 이름 역조회
            for sf in TICKERS_STATE.glob("*.yaml"):
                try:
                    sd = __import__("yaml").safe_load(sf.read_text(encoding="utf-8")) or {}
                    if str(sd.get("ticker", "")) == code:
                        nm = sd.get("name", "")
                        break
                except Exception:
                    pass
        if not nm:
            continue

        screener_row = {
            "date":       scr_date,
            "change":     row.get("change", 0),
            "vol_ratio":  row.get("vol_ratio", 0),
            "rs_pct":     row.get("rs_pct", 0),
            "turtle":     row.get("turtle", ""),
            "foreign_5d": row.get("foreign_5d", 0),
            "tag":        row.get("tag", ""),
        }
        extra = {"_screener_row": screener_row}
        if code:
            extra["ticker"] = code

        touch_ticker(
            nm,
            kind="stage2",
            ref="alerts/stage2_geek_filtered.json",
            when=scr_date,
            report=report,
            dry_run=dry_run,
            extra=extra,
        )


def sync_reviews(report: SyncReport, dry_run: bool) -> None:
    if not REVIEWS_DIR.exists():
        return
    # 지난 7일 내 리뷰만
    cutoff = TODAY - timedelta(days=7)
    for p in sorted(REVIEWS_DIR.glob("*CIO*.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_", p.name)
        if not m:
            continue
        try:
            rdate = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if rdate < cutoff:
            continue

        text = p.read_text()
        # 파일명에서 종목 코드/이름 추출: 2026-04-08_005930_000660_CIO.md
        codes = re.findall(r"_(\d{6})", p.name)

        sm = REVIEW_STATUS_PAT.search(text)
        decision = sm.group(1).strip().lower() if sm else ""
        status_map = {
            "enter": "entered",
            "entered": "entered",
            "hold": "hold",
            "exit": "retired",
            "retire": "retired",
            "pass": "monitoring",
            "watch": "monitoring",
        }
        new_status = status_map.get(decision, "")

        thesis_m = REVIEW_THESIS_PAT.search(text)
        thesis = thesis_m.group(1).strip()[:500] if thesis_m else ""
        inv_m = REVIEW_INVALID_PAT.search(text)
        invalidation = inv_m.group(1).strip()[:500] if inv_m else ""

        # 본문에서 wikilink 로 종목명 추출
        names = extract_tickers(text)
        if not names and codes:
            names = set(codes)

        extra = {}
        if new_status:
            extra["status"] = new_status
            extra["status_since"] = rdate.isoformat()
        if thesis:
            extra["thesis"] = thesis
        if invalidation:
            extra["invalidation"] = invalidation
        extra["next_review"] = (rdate + timedelta(days=7)).isoformat()

        for name in names:
            touch_ticker(
                name,
                kind="cio_review",
                ref=f"reviews/{p.name}",
                when=rdate.isoformat(),
                report=report,
                dry_run=dry_run,
                extra=extra,
            )


# ---------------------------------------------------------------------------
# (c) events phase 자동 전이
# ---------------------------------------------------------------------------

def sync_events(report: SyncReport, dry_run: bool) -> None:
    for md in sorted(EVENTS_DIR.glob("*.md")):
        if md.name.startswith("_"):
            continue
        text = md.read_text()
        fm, _body = parse_frontmatter(text)
        if not fm:
            continue

        event_id = md.stem  # 2026-03-17_Murata_MLCC_Price_Hike
        yaml_path = EVENTS_STATE / f"{event_id}.yaml"
        state = load_yaml(yaml_path)

        event_date = fm.get("event_date", state.get("event_date", TODAY_S))
        state.setdefault("event_id", event_id)
        state["event_date"] = event_date
        state.setdefault("phase", "active")
        state.setdefault("last_reviewed", TODAY_S)

        # expires_on 기본값
        if "expires_on" not in state:
            try:
                ed = datetime.strptime(str(event_date), "%Y-%m-%d").date()
                state["expires_on"] = (ed + timedelta(days=DEFAULT_EVENT_HORIZON_DAYS)).isoformat()
            except ValueError:
                state["expires_on"] = (TODAY + timedelta(days=DEFAULT_EVENT_HORIZON_DAYS)).isoformat()

        # 본문 frontmatter 의 status=INVALIDATED 는 기계상태에도 반영
        fm_status = str(fm.get("status", "")).upper()
        if fm_status == "INVALIDATED" and state["phase"] != "invalidated":
            state["phase"] = "invalidated"
            report.event_transitions.append(f"{event_id}: → invalidated (본문 status)")

        # linked_tickers_seen: 본 이벤트 frontmatter 의 tickers 각각에 대해
        # ticker .state 의 last_seen 과 비교
        linked = []
        all_stale = True
        for tname in fm.get("tickers", []) or []:
            tpath, tdata = load_ticker_state(tname)
            last_seen = tdata.get("last_seen", "")
            linked.append({"ticker": tname, "last_seen": last_seen or ""})
            if last_seen and days_between(last_seen, TODAY_S) <= FADING_DAYS:
                all_stale = False
        state["linked_tickers_seen"] = linked

        # phase 전이
        prev_phase = state["phase"]
        if state["phase"] == "active":
            last_cat = state.get("last_catalyst") or event_date
            if days_between(str(last_cat), TODAY_S) > 30 and all_stale:
                state["phase"] = "fading"
        if state["phase"] == "fading":
            if state.get("expires_on") and state["expires_on"] < TODAY_S:
                state["phase"] = "resolved"
        if state["phase"] != prev_phase:
            report.event_transitions.append(f"{event_id}: {prev_phase} → {state['phase']}")

        state["last_reviewed"] = TODAY_S
        change_type = "phase_transition" if state["phase"] != prev_phase else "review"
        dump_yaml(
            yaml_path, state, dry_run=dry_run,
            entity_type="event",
            entity_id=event_id,
            change_type=change_type,
            source_ref=f"events/{md.name}",
            old_data=load_yaml(yaml_path) if yaml_path.exists() else None,
        )


# ---------------------------------------------------------------------------
# (d) themes/active .state
# ---------------------------------------------------------------------------

def _parse_briefing_themes(text: str) -> list[dict]:
    """theme_briefing_*.md 본문에서 테마 섹션 파싱.
    반환: [{"name": str, "catalyst": str, "stocks": [str], "lines": [str]}]
    """
    # ━━━ 테마명 ━━━ 패턴 (📌 기타 제외)
    section_pat = re.compile(r"━━━\s+(.+?)\s+━━━")
    stock_pat = re.compile(r"•\s+\[\[([^\]]+)\]\]([^\n]*)")

    results = []
    sections = section_pat.split(text)
    # sections: [pre, name1, body1, name2, body2, ...]
    for i in range(1, len(sections), 2):
        name = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        if "기타" in name or "단독" in name:
            continue
        lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
        catalyst = next((l for l in lines if not l.startswith("•") and not l.startswith("#")), "")
        stocks = []
        stock_lines = []
        for l in lines:
            m = stock_pat.match(l)
            if m:
                stocks.append(m.group(1).strip())
                stock_lines.append(l)
        results.append({"name": name, "catalyst": catalyst, "stocks": stocks, "stock_lines": stock_lines})
    return results


def _build_theme_md(name: str, catalyst: str, stocks: list[str], stock_lines: list[str], date_str: str) -> str:
    frontmatter = f"""---
theme: "{name}"
phase: active
created: {date_str}
last_updated: {date_str}
status_note: "{catalyst[:80].replace('"', "'")}"
---"""
    winners = "\n".join(f"- [[{s}]]" for s in stocks) if stocks else "<!-- 수동 입력 -->"
    history_row = f"| {date_str} | {len(stocks)} | {catalyst[:60]} |"
    return f"""{frontmatter}

# [Theme] {name}

## 1. 핵심 동인 (Core Drivers)
- {catalyst}

## 2. 관련 이벤트 (Linked Events)
<!-- [[events/날짜_제목]] -->

## 3. 밸류체인 및 수혜/피해 종목 (Value Chain)

### 직접 수혜 (Direct Winners)
{winners}

### 간접 수혜 (Second Order Winners)
<!-- 수동 입력 -->

### 리스크 (Losers)
<!-- 수동 입력 -->

## 4. 모니터링 지표 (Key Metrics to Track)
<!-- 수동 입력 -->

## 5. 리스크 요인 / 무효화 조건 (Risks / Invalidators)
<!-- 수동 입력 -->

## 등장 이력
| 날짜 | 종목수 | 주요 촉매 |
|------|--------|---------|
{history_row}
"""


def _append_theme_history(md_path: Path, date_str: str, stocks: list[str], catalyst: str, dry_run: bool) -> bool:
    """기존 테마 파일에 등장 이력 1행 추가. 이미 해당 날짜 있으면 스킵."""
    text = md_path.read_text(encoding="utf-8")
    if date_str in text:
        return False
    new_row = f"| {date_str} | {len(stocks)} | {catalyst[:60]} |"
    if "## 등장 이력" in text:
        text = text.rstrip() + f"\n{new_row}\n"
    else:
        text = text.rstrip() + f"\n\n## 등장 이력\n| 날짜 | 종목수 | 주요 촉매 |\n|------|--------|------|\n{new_row}\n"
    # last_updated 갱신
    text = re.sub(r"last_updated: [\d-]+", f"last_updated: {date_str}", text)
    if not dry_run:
        md_path.write_text(text, encoding="utf-8")
    return True


def sync_theme_files(report: SyncReport, dry_run: bool) -> None:
    """theme_briefing_*.md → themes/active/테마명.md 자동 생성·갱신."""
    briefing = ALERTS_DIR / f"theme_briefing_{TODAY_S}.md"
    if not briefing.exists():
        cands = sorted(ALERTS_DIR.glob("theme_briefing_*.md"))
        if not cands:
            return
        briefing = cands[-1]

    m = re.search(r"theme_briefing_(\d{4}-\d{2}-\d{2})", briefing.name)
    when = m.group(1) if m else TODAY_S
    text = briefing.read_text(encoding="utf-8")
    themes = _parse_briefing_themes(text)

    created, updated = 0, 0
    for t in themes:
        name, catalyst, stocks = t["name"], t["catalyst"], t["stocks"]
        safe_name = name.replace("/", "·").replace(":", "-")
        md_path = THEMES_ACTIVE_DIR / f"{safe_name}.md"
        if not md_path.exists():
            content = _build_theme_md(name, catalyst, stocks, t["stock_lines"], when)
            if not dry_run:
                md_path.write_text(content, encoding="utf-8")
            report.theme_touched.append(name)
            created += 1
        else:
            changed = _append_theme_history(md_path, when, stocks, catalyst, dry_run)
            if changed:
                report.theme_touched.append(name)
                updated += 1

    print(f"   themes/active 신규 {created}개 / 이력 추가 {updated}개")


def sync_active_themes(report: SyncReport, dry_run: bool) -> None:
    for md in sorted(THEMES_ACTIVE_DIR.glob("*.md")):
        if md.name.startswith("_"):
            continue
        fm, _ = parse_frontmatter(md.read_text())
        if not fm:
            continue
        theme = fm.get("theme", md.stem)
        yaml_path = THEMES_ACTIVE_STATE / f"{theme}.yaml"
        state = load_yaml(yaml_path)
        state["theme"] = theme
        state["phase"] = fm.get("phase", state.get("phase", "active"))
        state.setdefault("first_seen", fm.get("created", TODAY_S))
        state["last_updated"] = fm.get("last_updated", TODAY_S)
        state.setdefault("related_tickers", [])
        state.setdefault("related_events", [])
        state["appearance_count_30d"] = state.get("appearance_count_30d", 0)
        old_state = load_yaml(yaml_path) if yaml_path.exists() else None
        dump_yaml(
            yaml_path, state, dry_run=dry_run,
            entity_type="theme",
            entity_id=theme,
            change_type="update",
            source_ref=f"themes/active/{md.name}",
            old_data=old_state,
        )
        report.theme_touched.append(theme)


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------

def write_report(report: SyncReport, dry_run: bool) -> Path:
    path = ALERTS_DIR / f"entity_syncer_report_{TODAY_S}.md"
    lines = [
        f"# entity_syncer 리포트 — {TODAY_S}",
        "",
        f"- 터치한 ticker: {len(set(report.ticker_touched))}개",
        f"- 신규 ticker .state: {len(report.ticker_created)}개",
        f"- event phase 전이: {len(report.event_transitions)}건",
        f"- 터치한 active theme: {len(set(report.theme_touched))}개",
        "",
    ]
    if report.ticker_created:
        lines += ["## 신규 ticker", *(f"- {n}" for n in report.ticker_created), ""]
    if report.event_transitions:
        lines += ["## 이벤트 전이", *(f"- {t}" for t in report.event_transitions), ""]
    if report.warnings:
        lines += ["## 경고", *(f"- {w}" for w in report.warnings), ""]
    text = "\n".join(lines)
    if not dry_run:
        path.write_text(text)
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    dry_run = "--dry-run" in sys.argv
    TICKERS_STATE.mkdir(parents=True, exist_ok=True)
    EVENTS_STATE.mkdir(parents=True, exist_ok=True)
    THEMES_ACTIVE_STATE.mkdir(parents=True, exist_ok=True)

    report = SyncReport()
    print(f"{'[DRY] ' if dry_run else ''}entity_syncer 시작 — {TODAY_S}")
    print("-" * 60)

    print("(a) theme_briefing / screener → tickers/.state + .md 수급 특징주")
    sync_theme_briefing(report, dry_run)

    print("(b) reviews → tickers/.state")
    sync_reviews(report, dry_run)

    print("(c) events phase 전이")
    sync_events(report, dry_run)

    print("(d) themes/active → themes/active/.state")
    sync_active_themes(report, dry_run)

    print("(e) theme_briefing → themes/active/*.md 자동 생성·갱신")
    sync_theme_files(report, dry_run)

    rp = write_report(report, dry_run)
    print("-" * 60)
    print(f"리포트: {rp.relative_to(BASE)}")
    print(
        f"ticker {len(set(report.ticker_touched))} / 신규 {len(report.ticker_created)} / "
        f"event 전이 {len(report.event_transitions)} / theme {len(set(report.theme_touched))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

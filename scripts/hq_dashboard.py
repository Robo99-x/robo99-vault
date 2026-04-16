#!/usr/bin/env python3
"""
hq_dashboard.py — 로보99 HQ 대시보드 (새버전)
실행: cd ~/robo99_hq/scripts && uv run streamlit run hq_dashboard.py
"""
import json
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
    HAS_AGGRID = True
except ImportError:
    HAS_AGGRID = False

try:
    from streamlit_lightweight_charts import renderLightweightCharts
    HAS_CHARTS = True
except ImportError:
    HAS_CHARTS = False

# ── 경로 ──────────────────────────────────────────────────────────────────────
import sys as _sys
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPTS_DIR)
from lib import config as _cfg  # noqa: E402

HQ             = _cfg.BASE
REVIEWS        = HQ / "reviews"
EVENTS         = HQ / "events"
TICKERS        = HQ / "tickers"
ALERTS         = _cfg.ALERTS
WATCHLIST      = HQ / "watchlist.md"
SCHEDULER_LOG  = ALERTS / "scheduler.log"
PORTFOLIO_FILE = ALERTS / "portfolio.json"
STAGE2_FILE    = ALERTS / "stage2_geek_filtered.json"
UNIVERSE_FILE  = ALERTS / "universe_scan.json"
CACHE_DB       = _cfg.CACHE_DB

KST_NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="로보99 HQ",
    page_icon="🐭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* ── 기본 배경 ── */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stSidebar"],
section[data-testid="stSidebarContent"] { background: #0d1117 !important; }

/* ── 전체 폰트 크기 타이트하게 ── */
html, body, [class*="css"] { font-size: 13px !important; }

/* ── 헤더 (h1) ── */
h1 { font-size: 1.3rem !important; font-weight: 700; color: #e6edf3 !important; }
h2 { font-size: 1.05rem !important; font-weight: 600; color: #e6edf3 !important; }
h3 { font-size: 0.95rem !important; font-weight: 600; color: #e6edf3 !important; }

/* ── 탭 ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #161b22 !important;
    border-bottom: 1px solid #30363d;
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    font-size: 12px !important;
    padding: 8px 14px !important;
    color: #8b949e !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #58a6ff !important;
    border-bottom: 2px solid #58a6ff !important;
}

/* ── 메트릭 카드 ── */
[data-testid="stMetric"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 16px !important;
}
[data-testid="stMetricLabel"] { font-size: 11px !important; color: #8b949e !important; }
[data-testid="stMetricValue"] { font-size: 1.4rem !important; color: #e6edf3 !important; font-weight: 700; }
[data-testid="stMetricDelta"] { font-size: 11px !important; }

/* ── 데이터프레임 ── */
[data-testid="stDataFrame"] { font-size: 12px !important; }
[data-testid="stDataFrame"] thead th {
    background: #161b22 !important;
    color: #8b949e !important;
    font-size: 11px !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="stDataFrame"] tbody td { color: #e6edf3 !important; font-size: 12px !important; }

/* ── 입력 필드 ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    font-size: 12px !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 2px rgba(88,166,255,0.15) !important;
}

/* ── 버튼 ── */
[data-testid="stFormSubmitButton"] button,
[data-testid="stButton"] button {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    font-size: 12px !important;
    padding: 5px 14px !important;
    border-radius: 6px !important;
    font-weight: 500;
}
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stButton"] button:hover {
    background: #30363d !important;
    border-color: #58a6ff !important;
}

/* ── 익스팬더 ── */
[data-testid="stExpander"] {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    font-size: 12px !important;
    color: #8b949e !important;
    padding: 8px 14px !important;
}

/* ── 셀렉트박스 ── */
[data-testid="stSelectbox"] > div > div {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #e6edf3 !important;
    font-size: 12px !important;
    border-radius: 6px !important;
}

/* ── 슬라이더 ── */
[data-testid="stSlider"] [data-baseweb="slider"] { font-size: 12px !important; }

/* ── 디바이더 ── */
hr { border-color: #30363d !important; margin: 12px 0 !important; }

/* ── 인포 박스 ── */
[data-testid="stAlert"] { font-size: 12px !important; border-radius: 6px !important; }

/* ── 커스텀 카드 클래스 ── */
.event-active { border-left: 3px solid #f85149; padding: 8px 12px; background: #161b22; border-radius: 6px; margin: 5px 0; }
.event-monitor { border-left: 3px solid #d29922; padding: 8px 12px; background: #161b22; border-radius: 6px; margin: 5px 0; }
.review-card  { border-left: 3px solid #3fb950; padding: 8px 12px; background: #161b22; border-radius: 6px; margin: 5px 0; }

/* ── 특징주/대장판독기 ── */
.theme-card { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:14px 16px; margin-bottom:10px; }
.theme-card:hover { border-color:#58a6ff; }
.theme-card-title { font-size:13px; font-weight:700; color:#e6edf3; }
.theme-card-meta  { font-size:11px; color:#8b949e; margin:4px 0 6px; }
.badge-leader { display:inline-block; background:rgba(240,136,62,0.15); border:1px solid rgba(240,136,62,0.4); color:#f0883e; font-size:11px; font-weight:600; border-radius:20px; padding:2px 10px; margin-left:6px; }
.score-high { color:#3fb950 !important; font-weight:700; }
.score-mid  { color:#d29922 !important; font-weight:700; }
.score-low  { color:#8b949e !important; }
.leader-sidebar-item { background:#161b22; border:1px solid #30363d; border-radius:6px; padding:8px 12px; margin-bottom:5px; }
.leader-sidebar-item.active { border-color:#f0883e; background:rgba(240,136,62,0.07); }
.daejang-banner { background:linear-gradient(135deg,rgba(240,136,62,0.15) 0%,rgba(88,166,255,0.08) 100%); border:1px solid rgba(240,136,62,0.35); border-radius:10px; padding:12px 16px; margin-bottom:10px; }
[data-testid="stRadio"] > div { flex-direction:row !important; gap:8px; }
[data-testid="stRadio"] label { background:#161b22 !important; border:1px solid #30363d !important; border-radius:20px !important; padding:4px 14px !important; font-size:12px !important; cursor:pointer; }
[data-testid="stRadio"] label:has(input:checked) { border-color:#f0883e !important; color:#f0883e !important; }
</style>
""", unsafe_allow_html=True)

# ── 헤더 ─────────────────────────────────────────────────────────────────────
st.markdown(f"# 🐭 로보99 HQ &nbsp;&nbsp; <span style='font-size:0.55em;color:#666'>{KST_NOW} KST</span>", unsafe_allow_html=True)

# ── 탭 ───────────────────────────────────────────────────────────────────────
tab_features, tab_overview, tab_theme, tab_watchlist, tab_reviews, tab_events, tab_portfolio, tab_scanner, tab_system = st.tabs([
    "🗂️ 기능정리", "📊 Overview", "🔥 특징주", "👁️ 워치리스트", "🤖 AI 분석", "📰 이벤트",
    "💼 포트폴리오", "🚀 마켓 스캐너", "⚙️ 시스템"
])


# ════════════════════════════════════════════════════════════════════════════
# 헬퍼
# ════════════════════════════════════════════════════════════════════════════
def parse_frontmatter(path: Path) -> dict:
    """YAML frontmatter 파싱"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def read_reviews() -> list[dict]:
    rows = []
    for p in sorted(REVIEWS.glob("*.md"), reverse=True):
        if p.name.startswith("_"):
            continue
        meta = parse_frontmatter(p)
        if not meta:
            continue
        rows.append({
            "파일": p.name,
            "날짜": meta.get("date", ""),
            "종목": meta.get("tickers", ""),
            "에이전트": meta.get("agents", ""),
            "결론": meta.get("conclusion", ""),
            "전체": p.read_text(encoding="utf-8"),
        })
    return rows


def read_events() -> list[dict]:
    rows = []
    for p in sorted(EVENTS.glob("*.md"), reverse=True):
        if p.name.startswith("_"):
            continue
        meta = parse_frontmatter(p)
        rows.append({
            "파일": p.name,
            "날짜": meta.get("date", ""),
            "유형": meta.get("event_type", meta.get("type", "")),
            "상태": meta.get("status", ""),
            "종목": meta.get("tickers", ""),
            "전체": p.read_text(encoding="utf-8"),
        })
    return rows


def parse_watchlist() -> tuple[list, list, list]:
    """watchlist.md에서 ACTIVE / MONITORING / RESOLVED 추출"""
    if not WATCHLIST.exists():
        return [], [], []
    text = WATCHLIST.read_text(encoding="utf-8")

    def extract_table(section_text):
        rows = []
        for line in section_text.splitlines():
            if line.startswith("|") and not line.startswith("| ---") and "이벤트" not in line:
                cols = [c.strip() for c in line.strip("|").split("|")]
                # 링크 텍스트만 추출
                cols = [re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", c) for c in cols]
                cols = [re.sub(r"\[\[([^\]]+)\]\]", r"\1", c) for c in cols]
                if any(c for c in cols):
                    rows.append(cols)
        return rows

    active, monitoring, resolved = [], [], []
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    for sec in sections:
        lower = sec.lower()
        if "active" in lower:
            active = extract_table(sec)
        elif "monitoring" in lower or "관찰" in lower:
            monitoring = extract_table(sec)
        elif "resolved" in lower:
            resolved = extract_table(sec)
    return active, monitoring, resolved


def tmux_status() -> dict:
    """tmux 세션 상태 확인"""
    try:
        out = subprocess.check_output(["tmux", "list-sessions"], text=True, stderr=subprocess.DEVNULL)
        sessions = [line.split(":")[0] for line in out.strip().splitlines()]
        return {"sessions": sessions, "ok": True}
    except Exception:
        return {"sessions": [], "ok": False}


def scheduler_log_tail(n=15) -> str:
    if not SCHEDULER_LOG.exists():
        return "로그 없음"
    lines = SCHEDULER_LOG.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-n:])


def cio_score_from_conclusion(conclusion: str) -> float | None:
    m = re.search(r"CIO Score[:\s]+([\d.]+)", conclusion)
    return float(m.group(1)) if m else None


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
with tab_overview:
    reviews = read_reviews()
    events = read_events()
    active_ev, monitor_ev, _ = parse_watchlist()
    tmux = tmux_status()

    # 메트릭 카드
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("AI 분석", f"{len(reviews)}건", "reviews/")
    with c2:
        st.metric("이벤트 카드", f"{len(events)}건", f"ACTIVE {len(active_ev)}")
    with c3:
        sched_ok = "scheduler" in tmux["sessions"]
        st.metric("스케줄러", "🟢 실행중" if sched_ok else "🔴 중지", "tmux scheduler")
    with c4:
        rs_path = ALERTS / "rs_rankings.json"
        if rs_path.exists():
            mtime = datetime.fromtimestamp(rs_path.stat().st_mtime).strftime("%m/%d %H:%M")
            st.metric("RS 랭킹", "최신", f"갱신: {mtime}")
        else:
            st.metric("RS 랭킹", "없음", "-")

    st.divider()

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("🔴 ACTIVE 이벤트")
        if active_ev:
            for row in active_ev:
                if len(row) >= 3:
                    st.markdown(
                        f'<div class="event-active"><b>{row[0]}</b><br>'
                        f'<span style="color:#aaa;font-size:0.85em">{row[1]} &nbsp;|&nbsp; {row[2] if len(row)>2 else ""}</span></div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("ACTIVE 이벤트 없음")

    with col_right:
        st.subheader("🤖 최근 AI 분석")
        for r in reviews[:5]:
            score = cio_score_from_conclusion(r["결론"])
            score_str = f"Score {score}" if score else ""
            st.markdown(
                f'<div class="review-card"><b>{r["종목"]}</b> &nbsp;<span style="color:#666;font-size:0.8em">{r["날짜"]}</span><br>'
                f'<span style="color:#aaa;font-size:0.85em">{r["결론"][:60]}...</span></div>',
                unsafe_allow_html=True,
            )

    # CIO Score 차트
    if reviews:
        scores = [(r["날짜"], r["종목"], cio_score_from_conclusion(r["결론"])) for r in reviews if cio_score_from_conclusion(r["결론"])]
        if scores:
            st.divider()
            st.subheader("📈 CIO Score 히스토리")
            df_score = pd.DataFrame(scores, columns=["날짜", "종목", "CIO Score"])
            fig = px.bar(df_score, x="종목", y="CIO Score", color="CIO Score",
                         color_continuous_scale="RdYlGn", range_color=[0, 10],
                         text="CIO Score", template="plotly_dark")
            fig.update_layout(
                height=260,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="#1e2130",
                plot_bgcolor="#1e2130",
                font=dict(color="#e0e0e0", size=12),
                xaxis=dict(gridcolor="#2a2d3e"),
                yaxis=dict(gridcolor="#2a2d3e"),
            )
            st.plotly_chart(fig, use_container_width=True)

    # (특징주는 별도 탭으로 이동됨)


# ════════════════════════════════════════════════════════════════════════════
# 특징주 헬퍼 함수
# ════════════════════════════════════════════════════════════════════════════

_THEME_NOTES_PATH = ALERTS / "theme_notes.json"


def load_theme_notes() -> dict:
    """alerts/theme_notes.json 로드. 없으면 빈 dict."""
    if _THEME_NOTES_PATH.exists():
        try:
            return json.loads(_THEME_NOTES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_theme_note(theme: str, desc: str) -> None:
    """alerts/theme_notes.json 에 테마 설명 저장."""
    notes = load_theme_notes()
    notes[theme] = {"desc": desc, "updated": KST_NOW.split()[0]}
    _THEME_NOTES_PATH.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@st.cache_data(ttl=300)
def fetch_ohlcv_batch(tickers: tuple) -> dict:
    """SQLite에서 종목별 최근 26일(close>0) 배치 조회. {ticker: [today, ..., 25일전]}"""
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    with sqlite3.connect(str(CACHE_DB)) as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, close FROM (
                SELECT ticker, close,
                    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                FROM ohlcv
                WHERE ticker IN ({placeholders}) AND close > 0
            ) WHERE rn <= 26
            """,
            list(tickers),
        ).fetchall()
    result: dict = {t: [] for t in tickers}
    for ticker, close in rows:
        result[ticker].append(close)
    return result


def _calc_rsi(closes: list, period: int = 14) -> float | None:
    """closes[0]=최신. period+1 미만 시 None 반환"""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(period):
        diff = closes[i] - closes[i + 1]  # closes[0]=최신이므로 역순
        (gains if diff > 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _calc_returns(closes: list) -> dict:
    """{'1w': float|None, '1m': float|None}  closes[0]=오늘"""
    r1w = (closes[0] / closes[4] - 1) * 100 if len(closes) >= 5 and closes[4] else None
    r1m = (closes[0] / closes[21] - 1) * 100 if len(closes) >= 22 and closes[21] else None
    return {"1w": round(r1w, 1) if r1w is not None else None,
            "1m": round(r1m, 1) if r1m is not None else None}


def _minmax_norm(values: list, lo: float, hi: float) -> list:
    """min-max 정규화 → [0, 100]"""
    rng = hi - lo
    if rng == 0:
        return [50.0] * len(values)
    return [max(0.0, min(100.0, (v - lo) / rng * 100)) for v in values]


def compute_scores(stocks: list, ohlcv: dict) -> "pd.DataFrame":
    """종합점수 계산. 전체 유니버스(40종목) 대상 min-max 정규화."""
    rows = []
    for s in stocks:
        closes = ohlcv.get(s["ticker"], [])
        ret = _calc_returns(closes)
        rows.append({
            **s,
            "rsi": _calc_rsi(closes),
            "return_1w": ret["1w"],
            "return_1m": ret["1m"],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    rs_vals   = df["rs_proxy"].tolist()
    chg_vals  = df["change"].tolist()
    vol_vals  = [min(v, 15.0) for v in df["vol_ratio"].tolist()]
    w1_vals   = [min(v, 150.0) if v is not None else 0.0 for v in df["return_1w"].tolist()]
    m1_vals   = [min(max(v, -20.0), 150.0) if v is not None else None for v in df["return_1m"].tolist()]

    rs_n  = _minmax_norm(rs_vals,  min(rs_vals),  max(rs_vals))
    chg_n = _minmax_norm(chg_vals, min(chg_vals), max(chg_vals))
    vol_n = _minmax_norm(vol_vals, 1.0, 15.0)
    w1_n  = _minmax_norm(w1_vals,  min(w1_vals),  max(w1_vals))

    has_m1 = [v is not None for v in m1_vals]
    m1_filled = [v if v is not None else 0.0 for v in m1_vals]
    m1_n = _minmax_norm(m1_filled, min(m1_filled), max(m1_filled)) if any(has_m1) else [0.0] * len(df)

    scores = []
    for i, row_has_m1 in enumerate(has_m1):
        if row_has_m1:
            s = rs_n[i]*0.40 + w1_n[i]*0.25 + chg_n[i]*0.15 + vol_n[i]*0.10 + m1_n[i]*0.10
        else:
            s = rs_n[i]*0.50 + w1_n[i]*0.25 + chg_n[i]*0.15 + vol_n[i]*0.10
        scores.append(round(s, 1))

    df["score"] = scores
    df["score_color"] = df["score"].apply(
        lambda x: "#3fb950" if x >= 70 else ("#d29922" if x >= 50 else "#8b949e")
    )
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def build_theme_groups(df: "pd.DataFrame") -> tuple:
    """테마별 그룹핑. 정렬: 종목수×평균점수 내림차순."""
    from collections import defaultdict as _dd
    groups: dict = _dd(list)
    for _, row in df.iterrows():
        themes = [t.strip() for t in str(row.get("theme", "기타")).split(",")]
        primary = themes[0] if themes else "기타"
        if primary == "미분류":
            primary = "기타"
        groups[primary].append(row.to_dict())

    theme_list = []
    singles = []
    for name, stocks in groups.items():
        sub_df = pd.DataFrame(stocks).sort_values("score", ascending=False).reset_index(drop=True)
        theme_list.append((name, sub_df))

    theme_list.sort(key=lambda x: -(len(x[1]) * x[1]["score"].mean()), reverse=False)
    theme_list.sort(key=lambda x: len(x[1]) * x[1]["score"].mean(), reverse=True)
    return theme_list


def render_theme_rank_table(theme_df: "pd.DataFrame") -> None:
    """테마 내 랭킹 테이블 렌더링."""
    cols = ["종목명", "시총(조)", "점수", "RS", "RSI", "1W%", "1M%", "등락%", "거래량배율", "대금(억)", "태그"]
    display = pd.DataFrame({
        "종목명":     theme_df["name"],
        "시총(조)":   theme_df["market_cap_조"].map("{:.1f}".format),
        "점수":       theme_df["score"].map("{:.0f}".format),
        "RS":         theme_df["rs_proxy"].map("{:.0f}".format),
        "RSI":        theme_df["rsi"].apply(lambda x: f"{x:.0f}" if x is not None else "—"),
        "1W%":        theme_df["return_1w"].apply(lambda x: f"{x:+.1f}%" if x is not None else "—"),
        "1M%":        theme_df["return_1m"].apply(lambda x: f"{x:+.1f}%" if x is not None else "—"),
        "등락%":      theme_df["change"].map("{:+.1f}%".format),
        "거래량배율": theme_df["vol_ratio"].map("{:.1f}x".format),
        "대금(억)":   theme_df["trade_value_억"].map("{:,.0f}".format),
        "태그":       theme_df["tag"].fillna(""),
    })
    display.index = [f"#{i+1}" for i in range(len(display))]

    def _score_color(val):
        try:
            v = float(val)
            if v >= 70: return "color: #3fb950; font-weight:700"
            if v >= 50: return "color: #d29922; font-weight:700"
            return "color: #8b949e"
        except Exception:
            return ""

    def _pct_color(val):
        try:
            v = float(str(val).replace("%", "").replace("—", ""))
            return "color: #3fb950" if v > 0 else ("color: #f85149" if v < 0 else "")
        except Exception:
            return ""

    styled = display.style \
        .map(_score_color, subset=["점수"]) \
        .map(_pct_color, subset=["1W%", "1M%", "등락%"])

    st.dataframe(styled, use_container_width=True, height=min(500, 45 + len(display) * 36))


# ════════════════════════════════════════════════════════════════════════════
# TAB — 🔥 특징주 (테마별 분류)
# ════════════════════════════════════════════════════════════════════════════
with tab_theme:
    _theme_path = ALERTS / "theme_screener.json"
    if not _theme_path.exists():
        st.subheader("🔥 특징주 테마별 분류")
        st.info("데이터 없음 — 장마감(15:40) 후 자동 생성됩니다")
    else:
        _th = json.loads(_theme_path.read_text(encoding="utf-8"))
        _th_stocks = _th.get("stocks", [])
        _th_date   = _th.get("date", "")
        _th_crit   = _th.get("criteria", "")

        st.subheader(f"🔥 특징주 테마별 분류 — {_th_date}")
        st.caption(f"기준: {_th_crit}")

        if not _th_stocks:
            st.info("필터 통과 종목 없음")
        else:
            # ── 점수 계산 (SQLite 배치 조회) ──
            _tickers_tuple = tuple(s["ticker"] for s in _th_stocks)
            _ohlcv = fetch_ohlcv_batch(_tickers_tuple)
            _df_scored = compute_scores(_th_stocks, _ohlcv)
            _theme_list = build_theme_groups(_df_scored)
            _theme_notes = load_theme_notes()

            # ── 뷰 선택 ──
            _view = st.radio("", ["📋 테마 카드", "🏆 대장판독기"], horizontal=True, key="theme_view_mode")
            st.divider()

            # ════════════════════════════════════════
            # VIEW A — 📋 테마 카드 (수직 expander)
            # ════════════════════════════════════════
            if _view == "📋 테마 카드":
                for _tname, _tdf in _theme_list:
                    _leader       = _tdf.iloc[0]
                    _total_val    = _tdf["trade_value_억"].sum()
                    _total_cap    = _tdf["market_cap_조"].sum()
                    _top_chg      = _tdf["change"].max()
                    _sc           = _leader["score"]
                    _sc_color     = "#3fb950" if _sc >= 70 else ("#d29922" if _sc >= 50 else "#8b949e")
                    _note_data    = _theme_notes.get(_tname, {})
                    _desc         = _note_data.get("desc", "")
                    _edit_key     = f"editing_{_tname}"

                    # expander 레이블: 테마명 + 요약 메타
                    _exp_label = (
                        f"**{_tname}** &nbsp; "
                        f"<span style='color:{_sc_color};font-size:12px'>{_sc:.0f}점</span> &nbsp; "
                        f"<span style='color:#8b949e;font-size:11px'>대장 {_leader['name']} · "
                        f"합산대금 {_total_val:,.0f}억 · {len(_tdf)}종목</span>"
                    )
                    with st.expander(_exp_label, expanded=False):
                        # ── 설명 영역 ──
                        _c_desc, _c_btn = st.columns([10, 1])
                        with _c_desc:
                            if st.session_state.get(_edit_key):
                                _new_desc = st.text_area(
                                    "테마 설명",
                                    value=_desc,
                                    height=80,
                                    key=f"textarea_{_tname}",
                                    label_visibility="collapsed",
                                )
                            else:
                                if _desc:
                                    st.markdown(
                                        f"<div style='color:#c9d1d9;font-size:12px;padding:6px 0'>{_desc}</div>",
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    st.caption("설명 없음 — ✏️ 버튼으로 추가")
                        with _c_btn:
                            if not st.session_state.get(_edit_key):
                                if st.button("✏️", key=f"edit_btn_{_tname}", help="설명 편집"):
                                    st.session_state[_edit_key] = True
                                    st.rerun()
                            else:
                                if st.button("💾", key=f"save_btn_{_tname}", help="저장"):
                                    save_theme_note(_tname, st.session_state.get(f"textarea_{_tname}", ""))
                                    st.session_state[_edit_key] = False
                                    st.rerun()

                        st.divider()

                        # ── 종목 테이블 ──
                        _tbl = pd.DataFrame({
                            "종목명":     _tdf["name"],
                            "등락%":      _tdf["change"].map("{:+.1f}%".format),
                            "거래량배율": _tdf["vol_ratio"].map("{:.1f}x".format),
                            "대금(억)":   _tdf["trade_value_억"].map("{:,.0f}".format),
                            "시총(조)":   _tdf["market_cap_조"].map("{:.1f}".format),
                            "RS":         _tdf["rs_proxy"].map("{:.0f}".format),
                            "점수":       _tdf["score"].map("{:.0f}".format),
                            "태그":       _tdf["tag"].fillna(""),
                        })
                        _tbl.index = [f"#{i+1}" for i in range(len(_tbl))]

                        def _card_score_color(val):
                            try:
                                v = float(val)
                                if v >= 70: return "color:#3fb950;font-weight:700"
                                if v >= 50: return "color:#d29922;font-weight:700"
                                return "color:#8b949e"
                            except Exception:
                                return ""

                        def _card_chg_color(val):
                            try:
                                v = float(str(val).replace("%",""))
                                return "color:#3fb950" if v > 0 else ("color:#f85149" if v < 0 else "")
                            except Exception:
                                return ""

                        st.dataframe(
                            _tbl.style
                                .map(_card_score_color, subset=["점수"])
                                .map(_card_chg_color, subset=["등락%"]),
                            use_container_width=True,
                            height=min(400, 45 + len(_tbl) * 36),
                        )

                        # 대장판독기로 이동
                        if st.button(
                            f"🏆 {_tname} 대장판독기 →",
                            key=f"goto_dj_{_tname}",
                            use_container_width=False,
                        ):
                            st.session_state["selected_theme"] = _tname
                            st.session_state["theme_view_mode"] = "🏆 대장판독기"
                            st.rerun()

            # ════════════════════════════════════════
            # VIEW B — 🏆 대장판독기
            # ════════════════════════════════════════
            else:
                _theme_names = [t for t, _ in _theme_list]
                if "selected_theme" not in st.session_state or st.session_state["selected_theme"] not in _theme_names:
                    st.session_state["selected_theme"] = _theme_names[0] if _theme_names else ""

                _left, _right = st.columns([1, 3])

                with _left:
                    # 대장 of 대장 배너
                    _overall_leader = _df_scored.iloc[0]
                    _ol_sc  = _overall_leader["score"]
                    _ol_col = "#3fb950" if _ol_sc >= 70 else ("#d29922" if _ol_sc >= 50 else "#8b949e")
                    st.markdown(f"""
<div class='daejang-banner'>
  <div style='font-size:10px;color:#8b949e;margin-bottom:3px'>🏆 대장 of 대장</div>
  <div style='font-size:15px;font-weight:700;color:#e6edf3'>{_overall_leader['name']}</div>
  <div style='margin-top:3px;font-size:11px'>
    <span style='color:{_ol_col};font-weight:700'>{_ol_sc:.0f}점</span>
    <span style='color:#8b949e;margin-left:6px'>{_overall_leader['change']:+.1f}% · RS {_overall_leader['rs_proxy']:.0f}</span>
  </div>
</div>""", unsafe_allow_html=True)

                    if st.button("📊 전체 테마 비교", key="btn_daejang_all", use_container_width=True):
                        st.session_state["selected_theme"] = "__ALL__"

                    st.markdown("<div style='margin-bottom:6px'></div>", unsafe_allow_html=True)

                    # 테마 버튼 목록
                    for _tname, _tdf in _theme_list:
                        _lr  = _tdf.iloc[0]
                        _sc  = _lr["score"]
                        _act = st.session_state.get("selected_theme") == _tname
                        _sc_col = "#3fb950" if _sc >= 70 else ("#d29922" if _sc >= 50 else "#8b949e")
                        _border = "#f0883e" if _act else "#30363d"
                        _bg = "rgba(240,136,62,0.07)" if _act else "#161b22"
                        st.markdown(f"""
<div style='background:{_bg};border:1px solid {_border};border-radius:6px;padding:7px 10px;margin-bottom:3px'>
  <div style='font-size:10px;color:#8b949e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{_tname}</div>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-top:2px'>
    <span style='font-size:12px;font-weight:600;color:#e6edf3'>{_lr['name']}</span>
    <span style='font-size:11px;font-weight:700;color:{_sc_col}'>{_sc:.0f}점</span>
  </div>
</div>""", unsafe_allow_html=True)
                        if st.button(_tname, key=f"dj_btn_{_tname}", use_container_width=True):
                            st.session_state["selected_theme"] = _tname
                            st.rerun()

                with _right:
                    _sel = st.session_state.get("selected_theme", "")

                    if _sel == "__ALL__":
                        # 전체 테마 대장주 비교표
                        st.markdown("### 📊 테마별 대장주 비교")
                        _all_leaders = []
                        for _tname, _tdf in _theme_list:
                            _lr = _tdf.iloc[0].to_dict()
                            _lr["테마"] = _tname
                            _all_leaders.append(_lr)
                        _df_all = pd.DataFrame(_all_leaders)
                        _df_all_disp = pd.DataFrame({
                            "테마":     _df_all["테마"],
                            "대장주":   _df_all["name"],
                            "점수":     _df_all["score"].map("{:.0f}".format),
                            "RS":       _df_all["rs_proxy"].map("{:.0f}".format),
                            "1W%":      _df_all["return_1w"].apply(lambda x: f"{x:+.1f}%" if x is not None else "—"),
                            "등락%":    _df_all["change"].map("{:+.1f}%".format),
                            "대금(억)": _df_all["trade_value_억"].map("{:,.0f}".format),
                            "시총(조)": _df_all["market_cap_조"].map("{:.1f}".format),
                        })

                        def _sc_all(val):
                            try:
                                v = float(val)
                                if v >= 70: return "color:#3fb950;font-weight:700"
                                if v >= 50: return "color:#d29922;font-weight:700"
                                return "color:#8b949e"
                            except Exception:
                                return ""

                        st.dataframe(
                            _df_all_disp.style.map(_sc_all, subset=["점수"]),
                            use_container_width=True,
                            hide_index=True,
                            height=min(600, 45 + len(_df_all_disp) * 36),
                        )

                    else:
                        # 선택된 테마 랭킹 테이블
                        _sel_dict = {t: df for t, df in _theme_list}
                        _sel_df   = _sel_dict.get(_sel, _theme_list[0][1] if _theme_list else pd.DataFrame())
                        if not _sel_df.empty:
                            _ldr      = _sel_df.iloc[0]
                            _sc       = _ldr["score"]
                            _sc_col   = "#3fb950" if _sc >= 70 else ("#d29922" if _sc >= 50 else "#8b949e")
                            _total_v  = _sel_df["trade_value_억"].sum()
                            _total_c  = _sel_df["market_cap_조"].sum()
                            # 테마 설명
                            _note     = _theme_notes.get(_sel, {}).get("desc", "")

                            st.markdown(f"""
<div style='margin-bottom:8px'>
  <span style='font-size:16px;font-weight:700;color:#e6edf3'>{_sel}</span>
  <span class='badge-leader'>대장주: {_ldr['name']} ({_sc:.0f}점)</span>
</div>
<div style='font-size:11px;color:#8b949e;margin-bottom:6px'>
  합산대금 {_total_v:,.0f}억 &nbsp;·&nbsp; 합산시총 {_total_c:.1f}조 &nbsp;·&nbsp; {len(_sel_df)}종목
</div>""", unsafe_allow_html=True)

                            if _note:
                                st.markdown(
                                    f"<div style='color:#c9d1d9;font-size:12px;margin-bottom:10px;"
                                    f"background:#161b22;border:1px solid #30363d;border-radius:6px;"
                                    f"padding:8px 12px'>{_note}</div>",
                                    unsafe_allow_html=True,
                                )

                            render_theme_rank_table(_sel_df)

            # ── 원본 데이터 테이블 (접이식) ──
            st.divider()
            with st.expander("📊 원본 데이터 테이블", expanded=False):
                _df_th_raw = _df_scored[["ticker","name","change","vol_ratio","trade_value_억","market_cap_조","theme","tag","rs_proxy","score"]].copy()
                _df_th_raw.columns = ["코드","종목명","등락(%)","거래량배율","거래대금(억)","시총(조)","테마","태그","RS프록시","점수"]
                _df_th_raw = _df_th_raw.sort_values("점수", ascending=False).reset_index(drop=True)
                st.dataframe(
                    _df_th_raw.style
                        .background_gradient(subset=["등락(%)"], cmap="RdYlGn", vmin=0, vmax=15)
                        .background_gradient(subset=["거래량배율"], cmap="Blues", vmin=1, vmax=5)
                        .background_gradient(subset=["점수"], cmap="RdYlGn", vmin=0, vmax=100),
                    use_container_width=True,
                    hide_index=True,
                    height=min(500, 35 + len(_df_th_raw) * 35),
                )


# ════════════════════════════════════════════════════════════════════════════
# TAB — 워치리스트
# ════════════════════════════════════════════════════════════════════════════
with tab_watchlist:
    active, monitoring, resolved = parse_watchlist()
    st.subheader("🔴 ACTIVE")
    if active:
        headers = ["이벤트", "핵심 종목", "다음 촉매", "타임라인"]
        df_a = pd.DataFrame(active, columns=headers[:len(active[0])] if active else headers)
        st.dataframe(df_a, use_container_width=True, hide_index=True)
    else:
        st.info("없음")

    st.subheader("🟡 MONITORING")
    if monitoring:
        df_m = pd.DataFrame(monitoring)
        st.dataframe(df_m, use_container_width=True, hide_index=True)
    else:
        st.info("없음")

    if WATCHLIST.exists():
        with st.expander("📄 watchlist.md 원문"):
            st.text(WATCHLIST.read_text(encoding="utf-8"))

    st.divider()
    st.subheader("📈 차트")
    _col1, _col2 = st.columns([3, 1])
    with _col1:
        _nv_ticker = st.text_input("종목코드",
                                   value=st.session_state.get("_chart_shared", ""),
                                   placeholder="예: 005930",
                                   key="naver_chart_ticker")
    with _col2:
        _nv_period = st.select_slider(
            "기간", ["D", "W", "M"],
            format_func=lambda x: {"D": "일봉", "W": "주봉", "M": "월봉"}[x],
            key="naver_chart_period",
        )
    if _nv_ticker.strip():
        import streamlit.components.v1 as _wl_comp
        _wl_comp.html(
            f'<iframe src="https://finance.naver.com/item/fchart.nhn?code={_nv_ticker.strip()}" '
            f'width="100%" height="500" frameborder="0" scrolling="no" style="border:none;background:#fff"></iframe>',
            height=510,
            scrolling=False,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — AI 분석 히스토리
# ════════════════════════════════════════════════════════════════════════════
with tab_reviews:
    reviews = read_reviews()
    if not reviews:
        st.info("reviews/ 폴더에 분석 파일이 없습니다.")
    else:
        # 필터
        tickers_list = sorted(set(r["종목"] for r in reviews if r["종목"]))
        col1, col2 = st.columns([2, 1])
        with col1:
            search = st.text_input("🔍 종목 검색", placeholder="예: 리가켐, ISC")
        with col2:
            sort_order = st.selectbox("정렬", ["최신순", "오래된순"])

        filtered = reviews
        if search:
            filtered = [r for r in reviews if search.lower() in r["종목"].lower() or search.lower() in r["결론"].lower()]
        if sort_order == "오래된순":
            filtered = list(reversed(filtered))

        st.markdown(f"**{len(filtered)}건**")
        for idx, r in enumerate(filtered):
            score = cio_score_from_conclusion(r["결론"])
            score_color = "#00d4aa" if score and score >= 6 else "#ffa500" if score and score >= 4 else "#ff4b4b"
            border_color = score_color if score else "#4c8bf5"
            score_bar = ""
            if score:
                pct = int(score / 10 * 100)
                score_bar = (
                    f'<div style="margin:8px 0 4px">'
                    f'<div style="background:#2a2d3e;border-radius:4px;height:6px;width:100%">'
                    f'<div style="background:{score_color};border-radius:4px;height:6px;width:{pct}%"></div>'
                    f'</div></div>'
                )
            conclusion_short = r["결론"][:100] + ("..." if len(r["결론"]) > 100 else "")
            agents_html = "".join(
                f'<span style="background:#2a2d3e;color:#888;border-radius:4px;padding:1px 7px;font-size:0.75em;margin-right:4px">{a.strip()}</span>'
                for a in r["에이전트"].split(",")
            )
            st.markdown(
                f'<div style="background:#1e2130;border-radius:10px;padding:16px 20px;border-left:4px solid {border_color};margin-bottom:8px">'
                f'<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px">'
                f'<div style="flex:1">'
                f'<div style="font-weight:700;color:#e0e0e0;font-size:1em">{r["종목"]}</div>'
                f'<div style="color:#555;font-size:0.8em;margin:2px 0 6px">{r["날짜"]} &nbsp;{agents_html}</div>'
                f'<div style="color:#aaa;font-size:0.84em;line-height:1.5">{conclusion_short}</div>'
                f'{score_bar}'
                f'</div>'
                + (f'<div style="text-align:right;min-width:56px"><div style="font-size:1.6em;font-weight:800;color:{score_color}">{score}</div><div style="color:#555;font-size:0.72em">/ 10</div></div>' if score else "")
                + f'</div></div>',
                unsafe_allow_html=True,
            )
            with st.expander("전체 브리핑 보기"):
                st.markdown(r["전체"])


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — 이벤트
# ════════════════════════════════════════════════════════════════════════════
def build_events_html(ev_list):
    import html as html_mod
    cards_html = ""
    for idx, e in enumerate(ev_list):
        status = e["상태"].upper()
        color = "#ff4b4b" if status == "ACTIVE" else "#555"
        badge_bg = "#3a1515" if status == "ACTIVE" else "#2a2d3e"
        title = e["파일"].replace(".md", "").replace("_", " ")
        # 종목 태그
        tickers_raw = e["종목"].strip("[]").replace("'", "").replace('"', "")
        ticker_tags = "".join(
            f'<span style="background:#1e3a5f;color:#a8d8ea;border-radius:4px;padding:1px 7px;font-size:0.78em;margin-right:4px">{t.strip()}</span>'
            for t in tickers_raw.split(",") if t.strip()
        ) if tickers_raw else ""
        content_escaped = html_mod.escape(e["전체"])
        cards_html += f"""
        <div class="ev-card" style="border-left:3px solid {color}">
          <div class="ev-header">
            <span class="ev-badge" style="background:{badge_bg};color:{color}">{status}</span>
            <span class="ev-type" style="color:#888">{e['유형']}</span>
            <span class="ev-date" style="color:#555">{e['날짜']}</span>
          </div>
          <div class="ev-title">{title}</div>
          <div style="margin:6px 0">{ticker_tags}</div>
          <div class="toggle-row">
            <button class="toggle-btn" onclick="toggle('ev-{idx}')">상세보기 ▾</button>
          </div>
          <div class="toggle-content" id="ev-{idx}">
            <pre class="ev-body">{content_escaped}</pre>
          </div>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ background:transparent; font-family:-apple-system,sans-serif; margin:0; padding:0; }}
  .ev-card {{
    background:#1e2130; border-radius:10px; padding:16px 20px 12px;
    margin-bottom:10px; box-sizing:border-box;
  }}
  .ev-header {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  .ev-badge {{ border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:700; }}
  .ev-type {{ font-size:0.82em; }}
  .ev-date {{ font-size:0.82em; margin-left:auto; }}
  .ev-title {{ font-size:0.97em; font-weight:700; color:#e0e0e0; }}
  .toggle-row {{ margin-top:10px; border-top:1px solid #2a2d3e; padding-top:8px; }}
  .toggle-btn {{
    background:none; border:none; cursor:pointer;
    color:#4c8bf5; font-size:0.84em; padding:0; font-family:inherit;
  }}
  .toggle-btn:hover {{ color:#7ab3ff; }}
  .toggle-content {{ display:none; margin-top:10px; }}
  .toggle-content.open {{ display:block; }}
  .ev-body {{
    background:#0d1117; border-radius:6px; padding:12px 14px;
    color:#ccc; font-size:0.8em; line-height:1.6;
    white-space:pre-wrap; word-break:break-word; margin:0;
    max-height:400px; overflow-y:auto;
  }}
</style></head><body>
<div>{cards_html}</div>
<script>
function toggle(id) {{
  var el = document.getElementById(id);
  el.classList.toggle('open');
  var btn = el.previousElementSibling.querySelector('button');
  btn.textContent = el.classList.contains('open') ? '닫기 ▴' : '상세보기 ▾';
}}
</script>
</body></html>"""

with tab_events:
    import streamlit.components.v1 as components
    events = read_events()
    if not events:
        st.info("events/ 폴더에 이벤트 파일이 없습니다.")
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            ev_search = st.text_input("🔍 이벤트 검색", placeholder="예: 구리, 광섬유, 바이오")
        with col2:
            ev_status = st.selectbox("상태 필터", ["전체", "ACTIVE", "CLOSED"])

        filtered_ev = events
        if ev_search:
            filtered_ev = [e for e in events if ev_search.lower() in e["파일"].lower() or ev_search.lower() in e["전체"].lower()]
        if ev_status != "전체":
            filtered_ev = [e for e in filtered_ev if e["상태"].upper() == ev_status]

        st.markdown(f"**{len(filtered_ev)}건**")
        ev_height = len(filtered_ev) * 130 + 80
        components.html(build_events_html(filtered_ev), height=ev_height, scrolling=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — 기능정리
# ════════════════════════════════════════════════════════════════════════════
FEATURE_CARDS = [
    {
        "name": "미장 마감 리포트",
        "type": "자동화",
        "badge_color": "#4c8bf5",
        "schedule": "화~토 07:02",
        "desc": [
            "미국 시장 전일 마감 데이터 수집",
            "watchlist ACTIVE 종목 오버나이트 동향",
            "시장 요약 리포트 텔레그램 발송",
            "저장: alerts/report_YYYYMMDD.md",
        ],
        "logic": "scheduler_daemon.py의 job_market_report()가 07:02에 호출 → collect_market_data.py로 시장 데이터 수집 → Claude /market-report 스킬로 리포트 생성 → 텔레그램 발송",
        "scripts": ["collect_market_data.py", "scheduler_daemon.py"],
    },
    {
        "name": "장전 브리핑",
        "type": "자동화",
        "badge_color": "#4c8bf5",
        "schedule": "평일 08:30",
        "desc": [
            "ACTIVE 워치리스트 오버나이트 뉴스 체크",
            "당일 A/B/C 워치리스트 분류",
            "장중 체크포인트 목록 생성",
            "텔레그램 발송",
        ],
        "logic": "scheduler_daemon.py의 job_premarket()이 08:30에 호출 → Claude가 watchlist.md 읽고 /trade-research premarket 스킬 실행 → 오버나이트 뉴스 체크 후 A/B/C 분류 → 텔레그램 발송",
        "scripts": ["scheduler_daemon.py"],
    },
    {
        "name": "장초반 스크리닝",
        "type": "자동화",
        "badge_color": "#4c8bf5",
        "schedule": "평일 09:20",
        "desc": [
            "RS 랭킹 갱신 (전 종목 상대강도 계산)",
            "Stage2 패턴 스캔",
            "Geek 필터 (수급·리스크 2차 검증)",
            "VCP 패턴 스캐너 자동 발송",
            "watchlist 교차 확인 후 알림",
        ],
        "logic": "rs_ranking.py → 전 종목 RS 점수 계산 후 alerts/rs_rankings.json 저장. stage2_scanner.py → KRX DB에서 Stage2 조건(이평선 정렬·박스권) 스캔. geek_filter.py → 수급·리스크 2차 필터. stage2_briefing.py → 결과 텔레그램 발송. vcp_scanner.py → VCP 패턴 자동 발송.",
        "scripts": ["rs_ranking.py", "stage2_scanner.py", "geek_filter.py", "stage2_briefing.py", "vcp_scanner.py"],
    },
    {
        "name": "장중 스크리닝",
        "type": "자동화",
        "badge_color": "#4c8bf5",
        "schedule": "평일 14:00",
        "desc": [
            "Stage2 재스캔 (중복 방지 해시 처리)",
            "Geek 필터 2차 실행",
            "VCP 스캐너 자동 발송",
        ],
        "logic": "오전 스크리닝과 동일 파이프라인 재실행. stage2_briefing.py의 sent_hashes로 오전에 발송된 종목 중복 제거 후 신규 진입 종목만 발송.",
        "scripts": ["stage2_scanner.py", "geek_filter.py", "stage2_briefing.py", "vcp_scanner.py"],
    },
    {
        "name": "특징주 테마별 분류",
        "type": "자동화",
        "badge_color": "#4c8bf5",
        "schedule": "평일 15:40",
        "desc": [
            "시총1조↑ +5%↑ / 시총1조↓ +7%↑ | 거래량 1.5배↑ 필터",
            "AI 기반 촉매별 테마 자동 그룹핑",
            "신고가(20일/55일) 태깅",
            "텔레그램 발송",
        ],
        "logic": "theme_volume_screener.py → pykrx로 당일 등락률·거래량·시총 조회 → 필터 적용 → SQLite에서 20일 거래량 평균·신고가 계산 → theme_map.json 참조 → alerts/theme_screener.json 저장. Claude → JSON 읽고 AI 기반 테마 그룹핑 + 내러티브 생성 → 텔레그램 발송.",
        "scripts": ["theme_volume_screener.py", "update_themes.py", "scheduler_daemon.py"],
    },
    {
        "name": "Commander / CIO 에이전트",
        "type": "서비스",
        "badge_color": "#00d4aa",
        "schedule": "상시 (텔레그램 트리거)",
        "desc": [
            "Commander: 시스템 운영·설계·라우팅 (항상 활성)",
            "CIO: 투자 판단 전담 (트리거 스코어 ≥6 시 활성)",
            "옵티머스 (드러켄밀러 거시·모멘텀) + Geek (퀀트·리스크) 병렬",
            "CIO Score = Conviction×0.6 + RiskScore×0.4 → 비중 = Score×2%",
        ],
        "logic": "텔레그램 메시지 수신 → Commander가 트리거 스코어 계산(종목+3, 매수/매도+3, 거시+2, 리스크+2). 점수 ≥6이면 CIO 모드: agents/optimus.md + agents/geek.md 읽고 워커 병렬 호출 → CIO Score 산출 → reviews/ 저장 + 텔레그램 발송.",
        "scripts": ["agents/commander.md", "agents/optimus.md", "agents/geek.md"],
    },
    {
        "name": "KRX 데이터 파이프라인",
        "type": "서비스",
        "badge_color": "#00d4aa",
        "schedule": "스크리닝 시 자동 갱신",
        "desc": [
            "pykrx → SQLite (krx_cache.sqlite) 캐싱",
            "OHLCV + 시가총액 + 거래대금 전 종목 저장",
            "RS 계산 / 신고가 / 20일 거래량 기준 데이터 제공",
            "테마맵: 네이버 금융 스크래핑 (theme_map.json)",
        ],
        "logic": "rs_ranking.py / stage2_scanner.py 실행 시 pykrx API로 전 종목 OHLCV + 시총 조회 → alerts/cache/krx_cache.sqlite에 날짜별 저장. update_themes.py(주 1회 수동)는 네이버 금융 테마 페이지 스크래핑 → theme_map.json 갱신.",
        "scripts": ["rs_ranking.py", "stage2_scanner.py", "update_themes.py"],
    },
    {
        "name": "DART 사업보고서 연동",
        "type": "서비스",
        "badge_color": "#00d4aa",
        "schedule": "CIO 분석 시 호출",
        "desc": [
            "OpenDartReader로 최신 사업보고서 조회",
            "주요사항보고서 / 분기보고서 자동 파싱",
            "CIO 분석 시 펀더멘털 데이터 소스로 활용",
        ],
        "logic": "CIO 모드에서 종목 분석 시 OpenDartReader 라이브러리로 DART API 호출 → 최신 사업보고서·분기보고서 텍스트 파싱 → Geek 워커의 펀더멘털 분석 입력값으로 사용. API 키: secrets/config.json.",
        "scripts": ["secrets/config.json"],
    },
    {
        "name": "HQ 대시보드",
        "type": "서비스",
        "badge_color": "#00d4aa",
        "schedule": "상시 (tmux: dashboard)",
        "desc": [
            "Streamlit 기반 로컬 웹 대시보드",
            "기능정리 / AI 분석 히스토리 / 워치리스트 / 이벤트 / 시스템 현황",
            "포트: 8502",
        ],
        "logic": "hq_dashboard.py를 tmux dashboard 세션에서 상시 실행. reviews/, events/, watchlist.md를 실시간 파싱해 대시보드 렌더링. 같은 WiFi 환경에서 Mac IP:8502로 접속 가능.",
        "scripts": ["hq_dashboard.py"],
    },
]

def badge(label, color):
    return f'<span style="background:{color};color:#fff;border-radius:4px;padding:2px 8px;font-size:0.75em;font-weight:600">{label}</span>'

def build_features_html(cards):
    """기능정리 카드 전체를 JS 토글 방식으로 렌더링"""
    cards_html = ""
    for idx, card in enumerate(cards):
        bullets = "".join(f"<li>{d}</li>" for d in card["desc"])
        logic_items = card.get("logic", "—")
        file_items = "".join(f'<li><span>{s}</span></li>' for s in card["scripts"])
        cards_html += f"""
        <div class="card" style="border-top:3px solid {card['badge_color']}">
          <div class="card-meta">
            <span class="badge" style="background:{card['badge_color']}">{card['type']}</span>
            <span class="schedule">{card['schedule']}</span>
          </div>
          <div class="card-title">{card['name']}</div>
          <ul class="desc-list">{bullets}</ul>
          <div class="toggle-row">
            <button class="toggle-btn" onclick="toggle('logic-{idx}')">로직</button>
            <button class="toggle-btn" onclick="toggle('files-{idx}')">파일</button>
          </div>
          <div class="toggle-content" id="logic-{idx}">
            <p>{logic_items}</p>
          </div>
          <div class="toggle-content" id="files-{idx}">
            <ul class="file-list">{file_items}</ul>
          </div>
        </div>"""

    return f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ background: transparent; font-family: -apple-system, sans-serif; margin: 0; padding: 0; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 4px 0; }}
  .card {{
    background: #1e2130; border-radius: 10px; padding: 18px 20px 14px;
    box-sizing: border-box;
  }}
  .card-meta {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .badge {{
    color: #fff; border-radius: 4px; padding: 2px 8px;
    font-size: 0.75em; font-weight: 600;
  }}
  .schedule {{ color: #888; font-size: 0.82em; }}
  .card-title {{ font-size: 1em; font-weight: 700; color: #e0e0e0; margin-bottom: 10px; }}
  .desc-list {{ margin: 0 0 12px 16px; padding: 0; color: #bbb; font-size: 0.85em; line-height: 1.7; }}
  .toggle-row {{
    border-top: 1px solid #2a2d3e; padding-top: 10px;
    display: flex; gap: 14px;
  }}
  .toggle-btn {{
    background: none; border: none; cursor: pointer;
    color: #4c8bf5; font-size: 0.85em; padding: 0;
    font-family: inherit;
  }}
  .toggle-btn:hover {{ color: #7ab3ff; text-decoration: underline; }}
  .toggle-content {{
    display: none; margin-top: 10px;
    border-top: 1px solid #2a2d3e; padding-top: 10px;
  }}
  .toggle-content.open {{ display: block; }}
  .toggle-content p {{
    color: #ccc; font-size: 0.84em; line-height: 1.65;
    margin: 0;
  }}
  .file-list {{
    list-style: none; margin: 0; padding: 0;
  }}
  .file-list li {{
    margin: 3px 0;
  }}
  .file-list li span {{
    background: #2a2d3e; color: #a8d8ea;
    padding: 3px 10px; border-radius: 4px;
    font-size: 0.83em; font-family: monospace;
    display: inline-block;
  }}
</style>
</head><body>
<div class="grid">{cards_html}</div>
<script>
function toggle(id) {{
  var el = document.getElementById(id);
  el.classList.toggle('open');
}}
</script>
</body></html>"""

with tab_features:
    import streamlit.components.v1 as components

    filter_opts = ["전체", "자동화", "서비스"]
    sel = st.radio("", filter_opts, horizontal=True, label_visibility="collapsed")
    filtered_cards = FEATURE_CARDS if sel == "전체" else [c for c in FEATURE_CARDS if c["type"] == sel]

    card_height = 200 + max(len(c["desc"]) for c in filtered_cards) * 22
    total_rows = (len(filtered_cards) + 1) // 2
    estimated_height = total_rows * card_height + 100
    components.html(build_features_html(filtered_cards), height=estimated_height, scrolling=False)

    # 상시 서비스 (tmux 세션 상태)
    st.divider()
    st.markdown("### ⚙️ 상시 서비스 (tmux)")
    tmux_info = tmux_status()
    svc_cols = st.columns(3)
    services = [
        ("scheduler", "스케줄러 데몬", "자동화 잡 관리"),
        ("dashboard", "HQ 대시보드", "Streamlit :8502"),
        ("robo99", "Commander 세션", "텔레그램 에이전트"),
    ]
    for idx, (sess, title, desc) in enumerate(services):
        running = sess in tmux_info["sessions"]
        with svc_cols[idx]:
            color = "#00d4aa" if running else "#ff4b4b"
            status = "🟢 실행중" if running else "🔴 중지"
            st.markdown(
                f'<div style="background:#1e2130;border-radius:8px;padding:14px 16px;border-left:3px solid {color}">'
                f'<div style="font-weight:700;color:#e0e0e0">{title}</div>'
                f'<div style="color:#888;font-size:0.83em">{desc}</div>'
                f'<div style="margin-top:6px;font-size:0.9em">{status}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — 포트폴리오
# ════════════════════════════════════════════════════════════════════════════
with tab_portfolio:
    import json as _json

    def load_portfolio():
        try:
            return _json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8")) if PORTFOLIO_FILE.exists() else []
        except Exception:
            return []

    def save_portfolio(data):
        PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTFOLIO_FILE.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    portfolio = load_portfolio()

    with st.expander("➕ 종목 추가 / 수정", expanded=False):
        with st.form("portfolio_form"):
            pc1, pc2, pc3, pc4 = st.columns([1, 2, 1, 2])
            with pc1:
                p_ticker = st.text_input("종목코드", placeholder="005930")
            with pc2:
                p_name = st.text_input("종목명", placeholder="삼성전자")
            with pc3:
                p_size = st.number_input("비중(%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
            with pc4:
                p_memo = st.text_input("메모", placeholder="CIO Score 7.2 진입")
            if st.form_submit_button("저장") and p_ticker and p_name:
                idx = next((i for i, p in enumerate(portfolio) if p.get("ticker") == p_ticker), -1)
                entry = {
                    "ticker": p_ticker,
                    "name": p_name,
                    "size_pct": p_size,
                    "memo": p_memo,
                    "added_at": datetime.now().strftime("%Y-%m-%d"),
                }
                if idx >= 0:
                    portfolio[idx] = entry
                    st.success(f"{p_name} 수정 완료")
                else:
                    portfolio.append(entry)
                    st.success(f"{p_name} 추가 완료")
                save_portfolio(portfolio)
                st.rerun()

    if portfolio:
        # 비중 합계
        total_size = sum(p.get("size_pct", 0) for p in portfolio)
        cash = max(0, 100 - total_size)
        m1, m2, m3 = st.columns(3)
        m1.metric("보유 종목", f"{len(portfolio)}개")
        m2.metric("총 익스포저", f"{total_size:.1f}%")
        m3.metric("현금 비중", f"{cash:.1f}%")

        st.markdown("---")

        # 비중 차트
        if total_size > 0:
            chart_data = [{"종목": p["name"], "비중": p.get("size_pct", 0)} for p in portfolio if p.get("size_pct", 0) > 0]
            if cash > 0:
                chart_data.append({"종목": "현금", "비중": cash})
            df_chart = pd.DataFrame(chart_data)
            fig_pie = px.pie(
                df_chart, names="종목", values="비중",
                template="plotly_dark",
                color_discrete_sequence=["#4c8bf5", "#00d4aa", "#ffa94d", "#ff6b6b", "#bc8cff", "#58a6ff"],
            )
            fig_pie.update_layout(
                height=240,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="#1e2130",
                plot_bgcolor="#1e2130",
                legend=dict(font=dict(color="#aaa", size=12)),
                font=dict(color="#e0e0e0"),
            )
            fig_pie.update_traces(textfont_color="#e0e0e0", textfont_size=12)
            st.plotly_chart(fig_pie, use_container_width=True)

        # 종목 테이블
        df_port = pd.DataFrame([{
            "종목코드": p.get("ticker", ""),
            "종목명": p.get("name", ""),
            "비중(%)": p.get("size_pct", 0),
            "메모": p.get("memo", ""),
            "추가일": p.get("added_at", ""),
        } for p in portfolio])
        st.dataframe(df_port, use_container_width=True, hide_index=True)

        # 삭제
        with st.expander("🗑️ 종목 삭제", expanded=False):
            del_ticker = st.selectbox("삭제할 종목", ["선택"] + [f"{p['ticker']} {p['name']}" for p in portfolio])
            if st.button("삭제 확인") and del_ticker != "선택":
                del_code = del_ticker.split()[0]
                portfolio = [p for p in portfolio if p.get("ticker") != del_code]
                save_portfolio(portfolio)
                st.rerun()
    else:
        st.info("보유 종목이 없습니다. 위에서 종목을 추가하세요.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 8 — 마켓 스캐너
# ════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    import sqlite3 as _sqlite3

    @st.cache_data(ttl=60)
    def load_stage2():
        if not STAGE2_FILE.exists():
            return pd.DataFrame()
        try:
            return pd.DataFrame(_json.loads(STAGE2_FILE.read_text(encoding="utf-8")))
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=60)
    def load_universe():
        if not UNIVERSE_FILE.exists():
            return pd.DataFrame()
        try:
            d = _json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
            return pd.DataFrame(d.get("stocks", []))
        except Exception:
            return pd.DataFrame()

    # 데이터 소스 선택
    _src_col1, _src_col2 = st.columns([3, 1])
    with _src_col2:
        _scan_src = st.radio("데이터 소스", ["정밀필터 (geek)", "전체 유니버스"], horizontal=False, key="scan_src_radio")

    df_universe = load_universe()
    df_stage2 = load_stage2()

    if _scan_src == "전체 유니버스":
        _base_df = df_universe
        _src_label = f"universe_scan.json ({len(df_universe)}종목)" if not df_universe.empty else "universe_scan.json — 없음"
    else:
        _base_df = df_stage2
        _src_label = f"stage2_geek_filtered.json ({len(df_stage2)}종목)" if not df_stage2.empty else "stage2_geek_filtered.json — 없음"

    with _src_col1:
        st.caption(f"소스: {_src_label}")

    if _base_df.empty:
        if _scan_src == "전체 유니버스":
            st.info("전체 유니버스 스캔 없음 — 실행: uv run python stage2_scanner.py --full")
        else:
            st.info(f"스캐너 데이터 없음 ({STAGE2_FILE.name})")
    else:
        # 필터 바
        fc1, fc2, fc3 = st.columns([2, 1, 1])
        with fc1:
            scan_search = st.text_input("🔍 종목 검색", placeholder="예: ISC, 기가비스")
        with fc2:
            if _scan_src == "전체 유니버스":
                _cond_opts = ["전체", "전체통과(cond_all)", "MA만(cond_ma)", "52주만(cond_52w)", "워치리스트"]
                _cond_filter = st.selectbox("조건 필터", _cond_opts)
                turtle_filter = "전체"
            else:
                turtle_opts = ["전체"] + sorted(_base_df["turtle"].dropna().unique().tolist()) if "turtle" in _base_df.columns else ["전체"]
                turtle_filter = st.selectbox("터틀 신호", turtle_opts)
                _cond_filter = "전체"
        with fc3:
            rs_min = st.slider("RS 최소(%)", 0, 100, 70 if _scan_src != "전체 유니버스" else 0)

        filtered_scan = _base_df.copy()
        if scan_search:
            name_col = "name" if "name" in filtered_scan.columns else filtered_scan.columns[0]
            filtered_scan = filtered_scan[filtered_scan[name_col].astype(str).str.contains(scan_search, case=False, na=False)]
        if turtle_filter != "전체" and "turtle" in filtered_scan.columns:
            filtered_scan = filtered_scan[filtered_scan["turtle"] == turtle_filter]
        if "rs_rank" in filtered_scan.columns:
            filtered_scan = filtered_scan[filtered_scan["rs_rank"] >= rs_min]
        # 유니버스 모드 조건 필터
        if _scan_src == "전체 유니버스":
            if _cond_filter == "전체통과(cond_all)" and "cond_all" in filtered_scan.columns:
                filtered_scan = filtered_scan[filtered_scan["cond_all"] == True]
            elif _cond_filter == "MA만(cond_ma)" and "cond_ma" in filtered_scan.columns:
                filtered_scan = filtered_scan[filtered_scan["cond_ma"] == True]
            elif _cond_filter == "52주만(cond_52w)" and "cond_52w" in filtered_scan.columns:
                filtered_scan = filtered_scan[filtered_scan["cond_52w"] == True]
            elif _cond_filter == "워치리스트" and "in_watchlist" in filtered_scan.columns:
                filtered_scan = filtered_scan[filtered_scan["in_watchlist"] == True]

        st.markdown(f"**{len(filtered_scan)}개 종목**")

        # 유니버스 모드: 조건 달성 현황 컬럼 포함
        if _scan_src == "전체 유니버스":
            display_cols = [c for c in ["ticker", "name", "price", "change", "vol_ratio", "turtle",
                                        "cond_count", "cond_ma", "cond_52w", "cond_turtle", "cond_all", "in_watchlist"]
                            if c in filtered_scan.columns]
        else:
            display_cols = [c for c in ["ticker", "name", "price", "change_pct", "vol_ratio", "turtle", "rs_rank", "tag"]
                            if c in filtered_scan.columns]

        # ── 종목 리스트 ──────────────────────────────────────────────────────
        _df_display = (filtered_scan[display_cols] if display_cols else filtered_scan).reset_index(drop=True)

        if HAS_AGGRID:
            from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
            _gb = GridOptionsBuilder.from_dataframe(_df_display)
            _gb.configure_selection("single", use_checkbox=False)
            _gb.configure_default_column(resizable=True, sortable=True, filterable=False)
            _grid_resp = AgGrid(
                _df_display,
                gridOptions=_gb.build(),
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                fit_columns_on_grid_load=True,
                height=300,
                key="scanner_aggrid_v3",
            )
            _sel_rows = _grid_resp.get("selected_rows", [])
            _picked = ""
            if isinstance(_sel_rows, pd.DataFrame) and not _sel_rows.empty:
                _picked = str(_sel_rows.iloc[0].get("ticker", ""))
            elif isinstance(_sel_rows, list) and _sel_rows:
                _picked = str(_sel_rows[0].get("ticker", ""))
            import re as _re_ag
            if _picked and _re_ag.fullmatch(r"[0-9A-Za-z]{4,9}", _picked.strip()):
                st.session_state["selected_symbol"] = _picked.strip()
        else:
            st.dataframe(_df_display, use_container_width=True, hide_index=True)

        # ── 차트 영역 ─────────────────────────────────────────────────────────
        st.markdown("---")
        import sqlite3 as _sqlite3
        import streamlit.components.v1 as _components
        import requests as _req

        # 선택 종목 표시 + 직접 입력
        import re as _re_val
        def _valid_ticker(t: str) -> bool:
            return bool(_re_val.fullmatch(r"[0-9A-Za-z]{4,9}", t.strip()))

        _sym = st.session_state.get("selected_symbol", "")
        if _sym and _valid_ticker(_sym):
            st.info(f"현재 선택된 종목: **{_sym}**")
            # text_input key와 동기화 (value= 충돌 우회)
            st.session_state["scanner_chart_direct"] = _sym

        cc1, cc2, cc3 = st.columns([3, 1, 1])
        with cc1:
            _raw_input = st.text_input("종목코드 직접 입력",
                                        placeholder="005930",
                                        key="scanner_chart_direct").strip()
            chart_ticker = _raw_input if _valid_ticker(_raw_input) else ""
            if _raw_input and not chart_ticker:
                st.caption("⚠️ 유효하지 않은 종목코드")
        with cc2:
            chart_days = st.selectbox("기간", [60, 120, 200, 365], index=1,
                                      format_func=lambda x: f"{x}일")
        with cc3:
            chart_source = st.radio("차트", ["Naver", "DB"], horizontal=True, key="scanner_chart_src")

        # selectbox는 제거 — AgGrid 행 클릭이 선택 역할을 대체
        _scan_opts = {}
        if not filtered_scan.empty and "ticker" in filtered_scan.columns and "name" in filtered_scan.columns:
            _scan_opts = {r["ticker"]: r["name"] for _, r in filtered_scan.iterrows()}
        _nv_name = _scan_opts.get(chart_ticker, chart_ticker)

        def _fetch_naver_ohlcv(ticker: str, count: int = 200):
            """네이버 차트 API → OHLCV list [{time,open,high,low,close,volume}]"""
            url = (f"https://fchart.stock.naver.com/siseJson.nhn"
                   f"?symbol={ticker}&requestType=0&timeframe=day&count={count}&version=2.1")
            try:
                r = _req.get(url, headers={"Referer": "https://finance.naver.com/"}, timeout=8)
                import re as _re
                rows = _re.findall(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)', r.text)
                return [{"time": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                         "open": int(o), "high": int(h), "low": int(l),
                         "close": int(c), "volume": int(v)}
                        for d, o, h, l, c, v in rows]
            except Exception:
                return []

        if chart_ticker and chart_source == "Naver":
            import json as _json2
            # 일/주/월별 count
            _tf_map = {"day": chart_days, "week": 200, "month": 120}

            # 각 timeframe 데이터 미리 fetch
            _all_tf = {}
            for _tf, _cnt in _tf_map.items():
                _d = _fetch_naver_ohlcv(chart_ticker, _cnt) if _tf == "day" else []
                if _tf == "day":
                    _all_tf["day"] = _d
                else:
                    # week/month는 별도 API
                    try:
                        _url2 = (f"https://fchart.stock.naver.com/siseJson.nhn"
                                 f"?symbol={chart_ticker}&requestType=0&timeframe={_tf}&count={_cnt}&version=2.1")
                        import re as _re2
                        _r2 = _req.get(_url2, headers={"Referer":"https://finance.naver.com/"}, timeout=8)
                        _rows2 = _re2.findall(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)', _r2.text)
                        _all_tf[_tf] = [{"time": f"{d[:4]}-{d[4:6]}-{d[6:]}","open":int(o),"high":int(h),"low":int(l),"close":int(c),"volume":int(v)} for d,o,h,l,c,v in _rows2]
                    except Exception:
                        _all_tf[_tf] = []

            _nv_data = _all_tf.get("day", [])
            if _nv_data:
                def _prep(data):
                    df = pd.DataFrame(data)
                    for m in [5, 20, 60, 120]:
                        df[f"ma{m}"] = df["close"].rolling(m).mean().round(0)
                    return df
                _dfs = {k: _prep(v) for k, v in _all_tf.items() if v}
                _df_nv = _dfs["day"]
                _last = _df_nv.iloc[-1]; _prev = _df_nv.iloc[-2] if len(_df_nv)>1 else _last
                _chg = (_last["close"]-_prev["close"])/_prev["close"]*100
                _chg_color = "#ef5350" if _chg >= 0 else "#4472c4"

                def _to_js(df):
                    candles = df[["time","open","high","low","close"]].to_dict("records")
                    vols = [{"time":r["time"],"value":int(r["volume"]),"color":"rgba(239,83,80,0.7)" if r["close"]>=r["open"] else "rgba(68,114,196,0.7)"} for _,r in df.iterrows()]
                    mas = {m:[{"time":r["time"],"value":float(r[f"ma{m}"])} for _,r in df.iterrows() if pd.notna(r[f"ma{m}"])] for m in [5,20,60,120]}
                    return _json2.dumps(candles), _json2.dumps(vols), {m:_json2.dumps(v) for m,v in mas.items()}

                _c_d, _v_d, _m_d = _to_js(_dfs["day"])
                _c_w, _v_w, _m_w = _to_js(_dfs["week"]) if "week" in _dfs else (_json2.dumps([]),_json2.dumps([]),{5:"[]",20:"[]",60:"[]",120:"[]"})
                _c_mo, _v_mo, _m_mo = _to_js(_dfs["month"]) if "month" in _dfs else (_json2.dumps([]),_json2.dumps([]),{5:"[]",20:"[]",60:"[]",120:"[]"})

                def _ma_val(df, m):
                    v = df[f"ma{m}"].iloc[-1]
                    return f"{int(v):,}" if pd.notna(v) else "-"

                _nv_chart_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#fff;font-family:-apple-system,'Malgun Gothic',sans-serif;font-size:12px}}
#header{{padding:8px 12px 5px;border-bottom:1px solid #e8e8e8;background:#fff}}
#title-row{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
#price{{font-size:20px;font-weight:700;color:{_chg_color}}}
#chg{{font-size:12px;color:{_chg_color}}}
#ohlc{{margin-top:4px;display:flex;gap:12px;color:#555;font-size:11px}}
.ma5{{color:#ff6b35}}.ma20{{color:#1fa0d4}}.ma60{{color:#6c4bdb}}.ma120{{color:#ff69b4}}
#tb{{display:flex;gap:4px;margin:6px 12px;border-bottom:1px solid #eee;padding-bottom:4px}}
.tbtn{{padding:3px 10px;border:1px solid #ddd;border-radius:3px;cursor:pointer;background:#fff;font-size:12px;color:#333}}
.tbtn.active{{background:#1fa0d4;color:#fff;border-color:#1fa0d4;font-weight:600}}
#chart{{width:100%;height:340px}}
#vol{{width:100%;height:70px}}
</style></head><body>
<div id="header">
  <div id="title-row">
    <span style="font-weight:700;font-size:14px;color:#111">{_nv_name}</span>
    <span style="color:#888;font-size:11px">{chart_ticker}</span>
    <span id="price">{int(_last['close']):,}</span>
    <span id="chg">▲{int(_last['close']-_prev['close']):,} ({_chg:+.2f}%)</span>
  </div>
  <div id="ohlc">
    <span>시 <b>{int(_last['open']):,}</b></span>
    <span>고 <b style="color:#ef5350">{int(_last['high']):,}</b></span>
    <span>저 <b style="color:#4472c4">{int(_last['low']):,}</b></span>
    <span>종 <b>{int(_last['close']):,}</b></span>
    <span class="ma5">이평5 {_ma_val(_df_nv,5)}</span>
    <span class="ma20">이평20 {_ma_val(_df_nv,20)}</span>
    <span class="ma60">이평60 {_ma_val(_df_nv,60)}</span>
    <span class="ma120">이평120 {_ma_val(_df_nv,120)}</span>
  </div>
</div>
<div id="tb">
  <button class="tbtn active" onclick="setTF('day',this)">일</button>
  <button class="tbtn" onclick="setTF('week',this)">주</button>
  <button class="tbtn" onclick="setTF('month',this)">월</button>
</div>
<div id="chart"></div><div id="vol"></div>
<script>
const DATA={{
  day:{{c:{_c_d},v:{_v_d},m5:{_m_d[5]},m20:{_m_d[20]},m60:{_m_d[60]},m120:{_m_d[120]}}},
  week:{{c:{_c_w},v:{_v_w},m5:{_m_w[5]},m20:{_m_w[20]},m60:{_m_w[60]},m120:{_m_w[120]}}},
  month:{{c:{_c_mo},v:{_v_mo},m5:{_m_mo[5]},m20:{_m_mo[20]},m60:{_m_mo[60]},m120:{_m_mo[120]}}}
}};
const chart=LightweightCharts.createChart(document.getElementById('chart'),{{
  width:document.body.clientWidth,height:340,
  layout:{{background:{{color:'#fff'}},textColor:'#333'}},
  grid:{{vertLines:{{color:'#f0f0f0'}},horzLines:{{color:'#f0f0f0'}}}},
  timeScale:{{borderColor:'#ddd',timeVisible:true}},
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}}
}});
const cs=chart.addCandlestickSeries({{upColor:'#ef5350',downColor:'#4472c4',borderUpColor:'#ef5350',borderDownColor:'#4472c4',wickUpColor:'#ef5350',wickDownColor:'#4472c4'}});
const lm5=chart.addLineSeries({{color:'#ff6b35',lineWidth:1,priceLineVisible:false,lastValueVisible:false}});
const lm20=chart.addLineSeries({{color:'#1fa0d4',lineWidth:1,priceLineVisible:false,lastValueVisible:false}});
const lm60=chart.addLineSeries({{color:'#6c4bdb',lineWidth:1,priceLineVisible:false,lastValueVisible:false}});
const lm120=chart.addLineSeries({{color:'#ff69b4',lineWidth:1,priceLineVisible:false,lastValueVisible:false}});
const vc=LightweightCharts.createChart(document.getElementById('vol'),{{
  width:document.body.clientWidth,height:70,
  layout:{{background:{{color:'#fff'}},textColor:'#999'}},
  grid:{{vertLines:{{color:'#f0f0f0'}},horzLines:{{visible:false}}}},
  timeScale:{{visible:false}}
}});
const vs=vc.addHistogramSeries({{priceFormat:{{type:'volume'}}}});
function setTF(tf,btn){{
  document.querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const d=DATA[tf];
  cs.setData(d.c);lm5.setData(d.m5);lm20.setData(d.m20);lm60.setData(d.m60);lm120.setData(d.m120);
  vs.setData(d.v);chart.timeScale().fitContent();
}}
setTF('day',document.querySelector('.tbtn'));
chart.timeScale().subscribeVisibleLogicalRangeChange(r=>{{if(r)vc.timeScale().setVisibleLogicalRange(r)}});
vc.timeScale().subscribeVisibleLogicalRangeChange(r=>{{if(r)chart.timeScale().setVisibleLogicalRange(r)}});
window.addEventListener('resize',()=>{{chart.applyOptions({{width:document.body.clientWidth}});vc.applyOptions({{width:document.body.clientWidth}})}});
</script></body></html>"""
                _components.html(_nv_chart_html, height=510, scrolling=False)
            else:
                st.warning(f"{chart_ticker} — 네이버 데이터 없음 (코드 확인)")
        elif chart_ticker and CACHE_DB.exists():
            try:
                conn = _sqlite3.connect(CACHE_DB)
                df_c = pd.read_sql(
                    "SELECT date, open, high, low, close, volume FROM ohlcv "
                    "WHERE ticker=? ORDER BY date DESC LIMIT ?",
                    conn, params=(chart_ticker.strip(), chart_days),
                )
                conn.close()

                if df_c.empty:
                    st.info(f"{chart_ticker} — DB에 데이터 없음")
                else:
                    df_c = df_c.sort_values("date").reset_index(drop=True)
                    df_c["time"] = pd.to_datetime(df_c["date"]).dt.strftime("%Y-%m-%d")

                    # 이동평균 계산
                    for m in [20, 60, 120]:
                        df_c[f"ma{m}"] = df_c["close"].rolling(m).mean().round(0)

                    # JSON 직렬화
                    candles = df_c[["time","open","high","low","close"]].to_dict("records")
                    volumes = [
                        {"time": r["time"], "value": int(r["volume"]),
                         "color": "rgba(239,83,80,0.7)" if r["close"] >= r["open"]
                                  else "rgba(68,114,196,0.7)"}
                        for _, r in df_c.iterrows()
                    ]
                    ma_series = {}
                    ma_colors_map = {20: "#f0b429", 60: "#ffd700", 120: "#4bc8e8"}
                    for m in [20, 60, 120]:
                        ma_series[m] = [
                            {"time": r["time"], "value": float(r[f"ma{m}"])}
                            for _, r in df_c.iterrows() if pd.notna(r[f"ma{m}"])
                        ]

                    name_label = auto_name if auto_name and auto_ticker == chart_ticker.strip() else chart_ticker.strip()
                    last = df_c.iloc[-1]
                    prev = df_c.iloc[-2] if len(df_c) > 1 else last
                    chg_pct = (last["close"] - prev["close"]) / prev["close"] * 100
                    chg_color = "#ef5350" if chg_pct >= 0 else "#4472c4"

                    candles_js   = _json.dumps(candles)
                    volumes_js   = _json.dumps(volumes)
                    ma20_js      = _json.dumps(ma_series[20])
                    ma60_js      = _json.dumps(ma_series[60])
                    ma120_js     = _json.dumps(ma_series[120])

                    chart_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#ffffff; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
#header {{ padding:10px 14px 6px; border-bottom:1px solid #f0f0f0; }}
#title {{ font-size:14px; font-weight:700; color:#1a1a1a; }}
#ohlc {{ font-size:11px; color:#666; margin-top:3px; display:flex; gap:12px; flex-wrap:wrap; }}
.ma-badge {{ font-size:11px; }}
#chart-wrap {{ position:relative; }}
#chart {{ width:100%; height:380px; }}
#vol-chart {{ width:100%; height:80px; }}
</style>
</head><body>
<div id="header">
  <div id="title">{name_label} <span style="color:#888;font-weight:400;font-size:12px">({chart_ticker.strip()})</span>
    <span style="margin-left:10px;font-size:13px;font-weight:700;color:{chg_color}">{int(last['close']):,}
      <span style="font-size:11px;font-weight:500">({chg_pct:+.2f}%)</span>
    </span>
  </div>
  <div id="ohlc">
    <span>시 <b>{int(last['open']):,}</b></span>
    <span>고 <b style="color:#ef5350">{int(last['high']):,}</b></span>
    <span>저 <b style="color:#4472c4">{int(last['low']):,}</b></span>
    <span>종 <b>{int(last['close']):,}</b></span>
    <span style="margin-left:8px" class="ma-badge">
      <span style="color:#f0b429">MA20 {int(df_c['ma20'].iloc[-1]) if pd.notna(df_c['ma20'].iloc[-1]) else '-':,}</span> &nbsp;
      <span style="color:#ffd700">MA60 {int(df_c['ma60'].iloc[-1]) if pd.notna(df_c['ma60'].iloc[-1]) else '-':,}</span> &nbsp;
      <span style="color:#4bc8e8">MA120 {int(df_c['ma120'].iloc[-1]) if pd.notna(df_c['ma120'].iloc[-1]) else '-':,}</span>
    </span>
  </div>
</div>
<div id="chart-wrap">
  <div id="chart"></div>
  <div id="vol-chart"></div>
</div>
<script>
const candleData  = {candles_js};
const volumeData  = {volumes_js};
const ma20Data    = {ma20_js};
const ma60Data    = {ma60_js};
const ma120Data   = {ma120_js};

// ── 메인 차트 ──
const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  width: document.body.clientWidth,
  height: 380,
  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#333' }},
  grid: {{ vertLines: {{ color: '#f5f5f5' }}, horzLines: {{ color: '#f5f5f5' }} }},
  rightPriceScale: {{ borderColor: '#e0e0e0' }},
  timeScale: {{ borderColor: '#e0e0e0', timeVisible: true }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
}});

const candleSeries = chart.addCandlestickSeries({{
  upColor: '#ef5350', downColor: '#4472c4',
  borderUpColor: '#ef5350', borderDownColor: '#4472c4',
  wickUpColor: '#ef5350', wickDownColor: '#4472c4',
}});
candleSeries.setData(candleData);

const ma20 = chart.addLineSeries({{ color: '#f0b429', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false }});
ma20.setData(ma20Data);
const ma60 = chart.addLineSeries({{ color: '#ffd700', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false }});
ma60.setData(ma60Data);
const ma120 = chart.addLineSeries({{ color: '#4bc8e8', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false }});
ma120.setData(ma120Data);

// ── 거래량 차트 ──
const volChart = LightweightCharts.createChart(document.getElementById('vol-chart'), {{
  width: document.body.clientWidth,
  height: 80,
  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#999' }},
  grid: {{ vertLines: {{ color: '#f5f5f5' }}, horzLines: {{ visible: false }} }},
  rightPriceScale: {{ borderColor: '#e0e0e0', scaleMargins: {{ top: 0.1, bottom: 0 }} }},
  timeScale: {{ borderColor: '#e0e0e0', visible: false }},
}});
const volSeries = volChart.addHistogramSeries({{ priceFormat: {{ type: 'volume' }} }});
volSeries.setData(volumeData);

// 두 차트 시간축 동기화
chart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
  if (range) volChart.timeScale().setVisibleLogicalRange(range);
}});
volChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
  if (range) chart.timeScale().setVisibleLogicalRange(range);
}});

// 리사이즈 대응
window.addEventListener('resize', () => {{
  chart.applyOptions({{ width: document.body.clientWidth }});
  volChart.applyOptions({{ width: document.body.clientWidth }});
}});

chart.timeScale().fitContent();
</script>
</body></html>"""

                    _components.html(chart_html, height=510, scrolling=False)

            except Exception as e:
                st.error(f"차트 오류: {e}")

        elif chart_ticker.strip() and not CACHE_DB.exists():
            st.info("KRX 캐시 DB 없음 — 스캐너 실행 후 차트 사용 가능")
        else:
            st.info("종목 리스트에서 클릭하거나 종목코드를 직접 입력하세요.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — 시스템
# ════════════════════════════════════════════════════════════════════════════
with tab_system:
    tmux = tmux_status()

    # ── 서비스 상태 ──────────────────────────────────────────────────────────
    KNOWN_SESSIONS = {
        "scheduler": ("스케줄러", "자동화 잡 전담"),
        "dashboard": ("HQ 대시보드", "Streamlit :8502"),
        "robo99":    ("Commander", "텔레그램 에이전트"),
    }
    import socket as _socket
    def _port_open(port):
        try:
            with _socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except Exception:
            return False

    all_sessions = {s: False for s in KNOWN_SESSIONS}
    for s in tmux["sessions"]:
        if s in all_sessions:
            all_sessions[s] = True
    # dashboard는 tmux 세션 대신 포트 8502 실제 응답 여부로 판단
    all_sessions["dashboard"] = _port_open(8502)

    cols = st.columns(len(KNOWN_SESSIONS))
    for idx, (sess, (title, desc)) in enumerate(KNOWN_SESSIONS.items()):
        running = all_sessions[sess]
        color = "#00d4aa" if running else "#ff4b4b"
        status_text = "실행중" if running else "중지"
        dot = "●"
        with cols[idx]:
            st.markdown(
                f'<div style="background:#1e2130;border-radius:10px;padding:16px 18px;border-top:3px solid {color}">'
                f'<div style="font-weight:700;color:#e0e0e0;font-size:0.97em">{title}</div>'
                f'<div style="color:#666;font-size:0.8em;margin:2px 0 10px">{desc}</div>'
                f'<div style="color:{color};font-size:0.88em;font-weight:600">{dot} {status_text}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # 알려지지 않은 세션
    unknown = [s for s in tmux["sessions"] if s not in KNOWN_SESSIONS]
    if unknown:
        st.markdown(
            f'<div style="margin-top:8px;color:#666;font-size:0.82em">기타 세션: '
            + ", ".join(f'<code>{s}</code>' for s in unknown) + "</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── 워크스페이스 현황 ─────────────────────────────────────────────────────
    st.markdown("#### 📁 워크스페이스")
    db_path = ALERTS / "cache" / "krx_cache.sqlite"
    r_count = max(0, len(list(REVIEWS.glob("*.md"))) - 1)
    e_count = max(0, len(list(EVENTS.glob("*.md"))) - 1)
    t_count = max(0, len(list(TICKERS.glob("*.md"))) - 1) if TICKERS.exists() else 0
    a_count = len(list(ALERTS.glob("*.json")))
    db_info = f"{db_path.stat().st_size/1024/1024:.1f} MB · {datetime.fromtimestamp(db_path.stat().st_mtime).strftime('%m/%d %H:%M')}" if db_path.exists() else "없음"

    ws_items = [
        ("AI 분석", f"{r_count}개", "reviews/"),
        ("이벤트", f"{e_count}개", "events/"),
        ("Tickers", f"{t_count}개", "tickers/"),
        ("Alert JSON", f"{a_count}개", "alerts/"),
        ("KRX DB", db_info, "alerts/cache/krx_cache.sqlite"),
    ]
    ws_cols = st.columns(5)
    for idx, (label, val, path) in enumerate(ws_items):
        with ws_cols[idx]:
            st.markdown(
                f'<div style="background:#1e2130;border-radius:8px;padding:12px 14px;text-align:center">'
                f'<div style="color:#888;font-size:0.75em;margin-bottom:4px">{label}</div>'
                f'<div style="color:#e0e0e0;font-size:1.05em;font-weight:700">{val}</div>'
                f'<div style="color:#555;font-size:0.72em;margin-top:4px;word-break:break-all">{path}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── 스케줄러 로그 ─────────────────────────────────────────────────────────
    st.markdown("#### 📋 스케줄러 로그")
    log = scheduler_log_tail(15)
    log_lines = "".join(
        f'<div style="padding:2px 0;color:{"#ff6b6b" if "[ERROR]" in line else "#ffa94d" if "[WARNING]" in line else "#a8d8ea"};'
        f'font-size:0.82em;font-family:monospace;white-space:pre">{line}</div>'
        for line in log.splitlines()
    )
    st.markdown(
        f'<div style="background:#0d1117;border-radius:8px;padding:14px 16px;border:1px solid #2a2d3e;max-height:320px;overflow-y:auto">'
        f'{log_lines}'
        f'</div>',
        unsafe_allow_html=True,
    )

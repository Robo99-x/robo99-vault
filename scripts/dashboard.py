import sys
import streamlit as st
import pandas as pd
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

# ── lib/ import 보장 ─────────────────────────────────
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib import config, db  # noqa: E402

try:
    from st_aggrid import AgGrid, GridOptionsBuilder
    HAS_AGGRID = True
except ImportError:
    HAS_AGGRID = False

try:
    from streamlit_lightweight_charts import renderLightweightCharts
    HAS_CHARTS = True
except ImportError:
    HAS_CHARTS = False

st.set_page_config(page_title="Robo99 HQ Dashboard", layout="wide", page_icon="🐭")

# ── Paths ──────────────────────────────────────────────────────────────────
HQ = Path.home() / "robo99_hq"
CACHE_DB     = HQ / "alerts/cache/krx_cache.sqlite"
STAGE2_FILE  = HQ / "alerts/stage2_geek_filtered.json"
PORTFOLIO_FILE = HQ / "alerts/portfolio.json"
WATCHLIST    = HQ / "watchlist.md"
EVENTS_DIR   = HQ / "events"
REVIEWS_DIR  = HQ / "reviews"
MEMORY_DIR   = HQ / "memory"
LAUNCHD_DIR  = HQ / "launchd"

# ── Helpers ────────────────────────────────────────────────────────────────

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_watchlist():
    """watchlist.md에서 ACTIVE/MONITORING 테이블 파싱."""
    if not WATCHLIST.exists():
        return [], []
    text = WATCHLIST.read_text()
    active, monitoring = [], []

    def parse_table(section_text):
        rows = []
        for line in section_text.splitlines():
            line = line.strip()
            if line.startswith("|") and not line.startswith("| 이벤트") and not line.startswith("|---"):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 3:
                    rows.append(cols)
        return rows

    active_match = re.search(r"## 🔴 ACTIVE.*?\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    monitor_match = re.search(r"## 🟡 MONITORING.*?\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if active_match:
        active = parse_table(active_match.group(1))
    if monitor_match:
        monitoring = parse_table(monitor_match.group(1))
    return active, monitoring

def list_event_cards():
    """events/ 디렉토리에서 이벤트카드 목록 반환."""
    if not EVENTS_DIR.exists():
        return []
    cards = []
    for f in sorted(EVENTS_DIR.glob("*.md"), reverse=True):
        if f.name.startswith("_"):
            continue
        name = f.stem
        # YYYY-MM-DD_제목 파싱
        parts = name.split("_", 1)
        date = parts[0] if len(parts) == 2 else ""
        title = parts[1].replace("_", " ") if len(parts) == 2 else name
        cards.append({"date": date, "title": title, "file": f})
    return cards

def read_md_frontmatter(path):
    """마크다운 파일에서 --- frontmatter와 본문 분리."""
    text = path.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_raw = parts[1]
            body = parts[2].strip()
            fm = {}
            for line in fm_raw.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            return fm, body
    return {}, text

def list_reviews():
    """reviews/ 디렉토리에서 AI 분석 기록 반환."""
    if not REVIEWS_DIR.exists():
        return []
    reviews = []
    for f in sorted(REVIEWS_DIR.glob("*.md"), reverse=True):
        if f.name.startswith("_"):
            continue
        fm, body = read_md_frontmatter(f)
        name = f.stem
        parts = name.split("_", 2)
        reviews.append({
            "date": fm.get("date", parts[0] if parts else ""),
            "tickers": fm.get("tickers", parts[1] if len(parts) > 1 else ""),
            "agents": fm.get("agents", parts[2] if len(parts) > 2 else ""),
            "conclusion": fm.get("conclusion", ""),
            "file": f,
            "body": body,
        })
    return reviews

def list_launchd_jobs():
    """launchd plist 파일 목록과 상태 반환."""
    jobs = []
    # HQ launchd 폴더
    for plist_dir in [LAUNCHD_DIR, HQ / "scripts"]:
        if not plist_dir.exists():
            continue
        for f in plist_dir.glob("*.plist"):
            label = f.stem
            # launchctl 상태 조회
            try:
                result = subprocess.run(
                    ["launchctl", "list", label],
                    capture_output=True, text=True, timeout=3
                )
                running = "PID" in result.stdout and result.returncode == 0
                status = "🟢 Running" if running else "⚫ Stopped"
            except Exception:
                status = "❓ Unknown"
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            jobs.append({"label": label, "status": status, "file": str(f), "modified": mtime})
    return jobs

# ══════════════════════════════════════════════════════════════════════════════
st.title("🐭 Robo99 HQ Dashboard")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview",
    "🗂️ 리서치 OS",
    "🤖 AI 분석 히스토리",
    "⏰ 스케줄러",
    "💼 포트폴리오",
    "🚀 마켓 스캐너",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("시스템 현황")

    col1, col2, col3, col4 = st.columns(4)

    active, monitoring = parse_watchlist()
    event_cards = list_event_cards()
    reviews = list_reviews()

    with col1:
        st.metric("ACTIVE 이벤트", len(active))
    with col2:
        st.metric("MONITORING", len(monitoring))
    with col3:
        st.metric("이벤트 카드", len(event_cards))
    with col4:
        st.metric("AI 분석 기록", len(reviews))

    st.markdown("---")

    # System Health
    st.subheader("🖥️ 인프라 상태")
    hcol1, hcol2, hcol3 = st.columns(3)

    with hcol1:
        if CACHE_DB.exists():
            mtime = datetime.fromtimestamp(CACHE_DB.stat().st_mtime).strftime("%m-%d %H:%M")
            st.metric("KRX Cache DB", "🟢 Online", mtime)
        else:
            st.metric("KRX Cache DB", "🔴 Offline", "파일 없음")

    with hcol2:
        if STAGE2_FILE.exists():
            mtime = datetime.fromtimestamp(STAGE2_FILE.stat().st_mtime).strftime("%m-%d %H:%M")
            st.metric("Stage2/VCP Pipeline", "🟢 Ready", mtime)
        else:
            st.metric("Stage2/VCP Pipeline", "🔴 없음", "")

    with hcol3:
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8888", timeout=2)
            st.metric("SearXNG", "🟢 Online", "localhost:8888")
        except Exception:
            st.metric("SearXNG", "🔴 Offline", "localhost:8888")

    st.markdown("---")

    # Recent activity
    st.subheader("🕐 최근 활동")
    rcol1, rcol2 = st.columns(2)

    with rcol1:
        st.markdown("**최근 이벤트카드 (5개)**")
        for c in event_cards[:5]:
            st.markdown(f"- `{c['date']}` {c['title']}")

    with rcol2:
        st.markdown("**최근 AI 분석 (5개)**")
        if reviews:
            for r in reviews[:5]:
                st.markdown(f"- `{r['date']}` {r['tickers']} — {r['conclusion'][:40] if r['conclusion'] else '내용없음'}")
        else:
            st.caption("아직 저장된 분석 없음. CIO 모드 실행 시 자동 저장됩니다.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 리서치 OS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("📋 Watchlist")

    active, monitoring = parse_watchlist()

    if active:
        st.markdown("**🔴 ACTIVE**")
        df_active = pd.DataFrame(active, columns=["이벤트", "핵심 종목", "다음 촉매", "타임라인"][:len(active[0])])
        st.dataframe(df_active, use_container_width=True)
    else:
        st.info("ACTIVE 이벤트 없음")

    if monitoring:
        st.markdown("**🟡 MONITORING**")
        df_mon = pd.DataFrame(monitoring, columns=["이벤트", "핵심 종목", "조건", "비고"][:len(monitoring[0])])
        st.dataframe(df_mon, use_container_width=True)

    st.markdown("---")
    st.subheader("📁 이벤트 카드")

    event_cards = list_event_cards()
    if event_cards:
        search_term = st.text_input("검색", placeholder="종목명 또는 키워드")
        filtered = [c for c in event_cards if not search_term or search_term.lower() in c["title"].lower()]

        for c in filtered[:30]:
            with st.expander(f"`{c['date']}` {c['title']}"):
                try:
                    content = c["file"].read_text()
                    st.markdown(content)
                except Exception as e:
                    st.error(str(e))
    else:
        st.info("이벤트 카드 없음")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AI 분석 히스토리
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🤖 AI 분석 기록")

    reviews = list_reviews()

    if not reviews:
        st.info("저장된 AI 분석 없음.\n\nCIO 모드에서 분석이 완료되면 `~/robo99_hq/reviews/` 에 자동 저장됩니다.")
    else:
        # 필터
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            ticker_filter = st.text_input("종목 필터", placeholder="예: SK하이닉스")
        with fcol2:
            agent_options = list({r["agents"] for r in reviews if r["agents"]})
            agent_filter = st.selectbox("에이전트", ["전체"] + agent_options)

        filtered_reviews = reviews
        if ticker_filter:
            filtered_reviews = [r for r in filtered_reviews if ticker_filter.lower() in r["tickers"].lower()]
        if agent_filter != "전체":
            filtered_reviews = [r for r in filtered_reviews if agent_filter in r["agents"]]

        # 요약 테이블
        if filtered_reviews:
            df_rev = pd.DataFrame([{
                "날짜": r["date"],
                "종목": r["tickers"],
                "에이전트": r["agents"],
                "결론": r["conclusion"][:60] if r["conclusion"] else ""
            } for r in filtered_reviews])
            st.dataframe(df_rev, use_container_width=True)

            st.markdown("---")
            st.markdown("**상세 보기**")
            selected_idx = st.selectbox(
                "분석 선택",
                range(len(filtered_reviews)),
                format_func=lambda i: f"{filtered_reviews[i]['date']} | {filtered_reviews[i]['tickers']}"
            )
            selected = filtered_reviews[selected_idx]
            with st.expander("전체 분석 내용", expanded=True):
                st.markdown(selected["body"])
        else:
            st.info("검색 결과 없음")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — 스케줄러
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("⏰ 자동화 작업 현황")

    jobs = list_launchd_jobs()

    if jobs:
        df_jobs = pd.DataFrame([{
            "Label": j["label"],
            "Status": j["status"],
            "파일 수정일": j["modified"],
        } for j in jobs])
        st.dataframe(df_jobs, use_container_width=True)
    else:
        st.info("등록된 launchd 작업 없음")

    st.markdown("---")
    st.subheader("📝 스케줄 작업 설명")
    job_descriptions = {
        "com.robo99.krx_cache_daily": "KRX 일별 주가 캐시 (장마감 후 자동 수집)",
        "com.robo99.quarterly_backtest": "분기별 백테스트 실행",
        "com.robo99.weekly_market_upgrade": "주간 시장 리포트 생성",
    }
    for label, desc in job_descriptions.items():
        st.markdown(f"- **{label}**: {desc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — 포트폴리오 (기존)
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("💼 포트폴리오 관리")

    portfolio = load_json(PORTFOLIO_FILE, [])

    with st.expander("종목 추가/수정"):
        with st.form("portfolio_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                p_ticker = st.text_input("종목코드")
            with col2:
                p_name = st.text_input("종목명")
            with col3:
                p_memo = st.text_input("메모")
            if st.form_submit_button("추가/수정") and p_ticker and p_name:
                idx = next((i for i, p in enumerate(portfolio) if p["ticker"] == p_ticker), -1)
                entry = {"ticker": p_ticker, "name": p_name, "memo": p_memo,
                         "added_at": datetime.now().strftime("%Y-%m-%d")}
                if idx >= 0:
                    portfolio[idx] = entry
                else:
                    portfolio.append(entry)
                save_json(PORTFOLIO_FILE, portfolio)
                st.success("저장 완료!")
                st.rerun()

    if portfolio:
        st.dataframe(pd.DataFrame(portfolio), use_container_width=True)
        del_ticker = st.selectbox("삭제", [""] + [p["ticker"] for p in portfolio])
        if st.button("삭제") and del_ticker:
            portfolio = [p for p in portfolio if p["ticker"] != del_ticker]
            save_json(PORTFOLIO_FILE, portfolio)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — 마켓 스캐너 (기존)
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("🚀 Stage 2 & VCP Breakout Candidates")

    @st.cache_data(ttl=60)
    def load_stage2():
        if not STAGE2_FILE.exists():
            return pd.DataFrame()
        with open(STAGE2_FILE) as f:
            return pd.DataFrame(json.load(f))

    df_stage2 = load_stage2()

    if not df_stage2.empty:
        display_cols = [c for c in ["ticker", "name", "price", "change", "vol_ratio", "turtle", "tag"]
                        if c in df_stage2.columns]
        if HAS_AGGRID:
            gb = GridOptionsBuilder.from_dataframe(df_stage2[display_cols])
            gb.configure_selection("single", use_checkbox=False)
            gb.configure_pagination(paginationAutoPageSize=True)
            grid_response = AgGrid(df_stage2[display_cols], gridOptions=gb.build(),
                                   fit_columns_on_grid_load=True, height=320, theme="streamlit")
            selected_rows = grid_response.get("selected_rows", [])
        else:
            st.dataframe(df_stage2[display_cols], use_container_width=True)
            selected_rows = []

        # Chart
        if HAS_CHARTS and CACHE_DB.exists():
            st.markdown("---")
            st.subheader("📈 차트")
            has_sel = (isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty) or \
                      (isinstance(selected_rows, list) and len(selected_rows) > 0)
            if has_sel:
                row = selected_rows.iloc[0] if isinstance(selected_rows, pd.DataFrame) else selected_rows[0]
                sel_ticker = row.get("ticker") if isinstance(row, dict) else row["ticker"]
                sel_name = row.get("name", sel_ticker) if isinstance(row, dict) else row["name"]
                st.markdown(f"**{sel_name} ({sel_ticker}) — 최근 200일**")
                try:
                    df_c = db.query_df(
                        "SELECT date,open,high,low,close,volume FROM ohlcv WHERE ticker=? ORDER BY date DESC LIMIT 200",
                        params=(sel_ticker,))
                    conn.close()
                    if not df_c.empty:
                        df_c = df_c.sort_values("date")
                        df_c["time"] = pd.to_datetime(df_c["date"]).dt.strftime("%Y-%m-%d")
                        candle = df_c[["time", "open", "high", "low", "close"]].to_dict("records")
                        volume = [{"time": r["time"], "value": r["volume"],
                                   "color": "rgba(239,83,80,.5)" if r["close"] < r["open"]
                                   else "rgba(38,166,154,.5)"}
                                  for _, r in df_c.iterrows()]
                        renderLightweightCharts([{
                            "chart": {"layout": {"textColor": "black", "background": {"type": "solid", "color": "white"}}},
                            "series": [
                                {"type": "Candlestick", "data": candle,
                                 "options": {"upColor": "#26a69a", "downColor": "#ef5350",
                                             "borderVisible": False, "wickUpColor": "#26a69a", "wickDownColor": "#ef5350"}},
                                {"type": "Histogram", "data": volume,
                                 "options": {"priceFormat": {"type": "volume"}, "priceScaleId": ""},
                                 "priceScale": {"scaleMargins": {"top": 0.8, "bottom": 0}}}
                            ]
                        }], "candlestick")
                except Exception as e:
                    st.error(str(e))
            else:
                st.info("위 리스트에서 종목을 클릭하면 차트가 표시됩니다.")
    else:
        st.info("스캐너 데이터 없음 (stage2_geek_filtered.json)")

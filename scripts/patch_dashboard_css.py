#!/usr/bin/env python3
"""
Robo99 HQ 대시보드 CSS 패치 스크립트
실행: python3 patch_dashboard_css.py

hq_dashboard.py 의 st.markdown(<style>...) 블록을 새 디자인으로 교체합니다.
Python 로직은 전혀 건드리지 않습니다.
"""
from pathlib import Path
import re, shutil, sys

# ── 경로 설정 ──────────────────────────────────────────────────────────────
CANDIDATES = [
    Path.home() / "robo99_hq" / "scripts" / "hq_dashboard.py",
    Path.home() / "robo99-vault" / "scripts" / "hq_dashboard.py",
    Path(__file__).resolve().parent / "hq_dashboard.py",
    Path("hq_dashboard.py"),
]
TARGET = next((p for p in CANDIDATES if p.exists()), None)
if not TARGET:
    print("❌ hq_dashboard.py 를 찾을 수 없습니다.")
    print("   이 스크립트를 hq_dashboard.py 와 같은 폴더에 두고 실행하세요.")
    sys.exit(1)

print(f"📄 대상: {TARGET}")

# ── 백업 ───────────────────────────────────────────────────────────────────
backup = TARGET.with_suffix(".py.bak")
shutil.copy2(TARGET, backup)
print(f"💾 백업: {backup}")

# ── 새 CSS ─────────────────────────────────────────────────────────────────
NEW_CSS = '''st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

/* ── 기본 배경 / 폰트 ── */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stSidebar"],
section[data-testid="stSidebarContent"] {
    background: #07090d !important;
}
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, sans-serif !important;
    font-size: 13px !important;
    color: #e2e8f4 !important;
}

/* ── 헤더 ── */
h1 { font-size: 1.25rem !important; font-weight: 700; color: #e2e8f4 !important; letter-spacing: -0.3px; }
h2 { font-size: 1.0rem !important; font-weight: 600; color: #e2e8f4 !important; }
h3 { font-size: 0.92rem !important; font-weight: 600; color: #e2e8f4 !important; }

/* ── 탭 ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #0c1018 !important;
    border-bottom: 1px solid #1e2a3a !important;
    gap: 0;
    padding: 0 4px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 10px 16px !important;
    color: #7a8ba3 !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    transition: color .15s !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: #e2e8f4 !important;
    background: rgba(255,255,255,.03) !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #4d9eff !important;
    border-bottom: 2px solid #4d9eff !important;
    font-weight: 600 !important;
}

/* ── 메트릭 카드 ── */
[data-testid="stMetric"] {
    background: #111720 !important;
    border: 1px solid #1e2a3a !important;
    border-radius: 10px !important;
    padding: 14px 16px !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 10px !important;
    color: #4a5a72 !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.5rem !important;
    color: #e2e8f4 !important;
    font-weight: 700 !important;
}
[data-testid="stMetricDelta"] { font-size: 11px !important; }

/* ── 데이터프레임 ── */
[data-testid="stDataFrame"] {
    border: 1px solid #1e2a3a !important;
    border-radius: 10px !important;
    overflow: hidden;
}
[data-testid="stDataFrame"] thead th {
    background: #1a2130 !important;
    color: #4a5a72 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
    border-bottom: 1px solid #1e2a3a !important;
}
[data-testid="stDataFrame"] tbody td {
    color: #e2e8f4 !important;
    font-size: 12px !important;
    border-bottom: 1px solid #111720 !important;
}
[data-testid="stDataFrame"] tbody tr:hover td {
    background: #1a2130 !important;
}

/* ── 입력 필드 ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    background: #111720 !important;
    border: 1px solid #2a3a50 !important;
    color: #e2e8f4 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    border-radius: 7px !important;
    padding: 7px 11px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #4d9eff !important;
    box-shadow: 0 0 0 2px rgba(77,158,255,0.15) !important;
}

/* ── 버튼 ── */
[data-testid="stFormSubmitButton"] button,
[data-testid="stButton"] button {
    background: #1a2130 !important;
    border: 1px solid #2a3a50 !important;
    color: #e2e8f4 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    border-radius: 7px !important;
    transition: all .15s !important;
}
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stButton"] button:hover {
    background: #222d3e !important;
    border-color: #4d9eff !important;
    color: #4d9eff !important;
}

/* ── 익스팬더 ── */
[data-testid="stExpander"] {
    background: #111720 !important;
    border: 1px solid #1e2a3a !important;
    border-radius: 10px !important;
    margin-bottom: 6px !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    color: #e2e8f4 !important;
    padding: 10px 14px !important;
}
[data-testid="stExpander"] summary:hover {
    background: rgba(255,255,255,.02) !important;
}

/* ── 셀렉트박스 ── */
[data-testid="stSelectbox"] > div > div {
    background: #111720 !important;
    border: 1px solid #2a3a50 !important;
    color: #e2e8f4 !important;
    font-size: 12px !important;
    border-radius: 7px !important;
}

/* ── 라디오 버튼 ── */
[data-testid="stRadio"] > div { flex-direction: row !important; gap: 6px !important; }
[data-testid="stRadio"] label {
    background: #111720 !important;
    border: 1px solid #2a3a50 !important;
    border-radius: 20px !important;
    padding: 4px 14px !important;
    font-size: 12px !important;
    color: #7a8ba3 !important;
    cursor: pointer;
    transition: all .15s !important;
}
[data-testid="stRadio"] label:hover { color: #e2e8f4 !important; border-color: #4d9eff40 !important; }
[data-testid="stRadio"] label:has(input:checked) {
    border-color: #ff7a45 !important;
    color: #ff7a45 !important;
    background: rgba(255,122,69,.08) !important;
}

/* ── 슬라이더 ── */
[data-testid="stSlider"] [data-baseweb="slider"] { font-size: 12px !important; }

/* ── 캡션 ── */
[data-testid="stCaptionContainer"] { color: #4a5a72 !important; font-size: 11px !important; }

/* ── 구분선 ── */
hr { border-color: #1e2a3a !important; margin: 12px 0 !important; }

/* ── 알림 박스 ── */
[data-testid="stAlert"] {
    font-size: 12px !important;
    border-radius: 8px !important;
    border: 1px solid #2a3a50 !important;
}

/* ── 스크롤바 ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #2a3a50; border-radius: 3px; }

/* ── 커스텀 카드 클래스 ── */
.event-active {
    border-left: 3px solid #ff4d6a;
    padding: 10px 14px;
    background: #111720;
    border-radius: 8px;
    margin: 5px 0;
    border: 1px solid #1e2a3a;
    border-left-width: 3px;
}
.event-monitor {
    border-left: 3px solid #f0a832;
    padding: 10px 14px;
    background: #111720;
    border-radius: 8px;
    margin: 5px 0;
    border: 1px solid #1e2a3a;
    border-left-width: 3px;
}
.review-card {
    border-left: 3px solid #00d68f;
    padding: 10px 14px;
    background: #111720;
    border-radius: 8px;
    margin: 5px 0;
    border: 1px solid #1e2a3a;
    border-left-width: 3px;
    transition: border-color .15s;
}
.review-card:hover { border-color: #2a3a50; }

/* ── 특징주 / 대장판독기 ── */
.theme-card {
    background: #111720;
    border: 1px solid #1e2a3a;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: border-color .15s;
}
.theme-card:hover { border-color: #2a3a50; }
.theme-card-title { font-size: 13px; font-weight: 700; color: #e2e8f4; }
.theme-card-meta  { font-size: 11px; color: #7a8ba3; margin: 4px 0 6px; }
.badge-leader {
    display: inline-block;
    background: rgba(255,122,69,.12);
    border: 1px solid rgba(255,122,69,.35);
    color: #ff7a45;
    font-size: 11px;
    font-weight: 600;
    border-radius: 20px;
    padding: 2px 10px;
    margin-left: 8px;
}
.score-high { color: #00d68f !important; font-weight: 700; }
.score-mid  { color: #f0a832 !important; font-weight: 700; }
.score-low  { color: #7a8ba3 !important; }
.daejang-banner {
    background: linear-gradient(135deg, rgba(255,122,69,.12) 0%, rgba(77,158,255,.06) 100%);
    border: 1px solid rgba(255,122,69,.3);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)'''

# ── 기존 CSS 블록 찾아서 교체 ───────────────────────────────────────────────
original = TARGET.read_text(encoding="utf-8")

# st.markdown("""<style> ... </style>""", unsafe_allow_html=True) 패턴 탐색
pattern = re.compile(
    r'st\.markdown\("""[\s\S]*?<style>[\s\S]*?</style>[\s\S]*?""",\s*unsafe_allow_html=True\)',
    re.DOTALL
)
match = pattern.search(original)
if not match:
    print("❌ CSS 블록을 찾을 수 없습니다. hq_dashboard.py 구조를 확인하세요.")
    sys.exit(1)

updated = original[:match.start()] + NEW_CSS + original[match.end():]
TARGET.write_text(updated, encoding="utf-8")

print("✅ CSS 패치 완료!")
print()
print("▶ Streamlit 재시작:")
print("  tmux attach -t dashboard")
print("  (Ctrl+C → 위 방향키 → Enter)")
print()
print("  또는:")
print("  tmux send-keys -t dashboard C-c '' Enter 'uv run streamlit run hq_dashboard.py --server.port 8502' Enter")

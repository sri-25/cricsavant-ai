"""CricSavant AI -- visual theme.

v7 -- the production port of the approved design north star
(design/CricSavantDashboard.jsx): 2026 slate-glass aesthetic. One
cohesive dark system -- #0b0f17 canvas, #161b26 glass cards, slate
borders, franchise-colored ambient glow, progress-bar stat cards,
badge pills -- instead of the light theme's stark panels the user
called outdated. Base surfaces come from .streamlit/config.toml
(dark), so Streamlit internals (dataframe grid, dropdown menus) match;
this file layers the glass, glow, and motion on top.
"""

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

# ---- Tokens (mirror the .jsx prototype) ---------------------------
BG = "#0b0f17"
BG_PANEL = "#0e1420"
BG_CARD = "#161b26"
BG_CARD_ELEV = "#1b2130"
BORDER = "rgba(148,163,184,0.14)"
BORDER_STRONG = "rgba(148,163,184,0.28)"

PRIMARY = "#3b82f6"
PRIMARY_DARK = "#1d4ed8"
GOLD = "#f59e0b"
GOLD_SOFT = "#fbbf24"
BLUE = "#60a5fa"
GREEN = "#34d399"
RED = "#fb7185"
PURPLE = "#a78bfa"
TEAL = "#2dd4bf"

TEXT = "#f1f5f9"
TEXT_DIM = "#94a3b8"
TEXT_FAINT = "#64748b"

SHADOW = "0 8px 32px rgba(0,0,0,0.35), 0 0 0 1px rgba(148,163,184,0.06) inset"
SHADOW_SM = "0 2px 12px rgba(0,0,0,0.3)"

ROLE_COLOR = {
    "batter": GOLD,
    "bowler": PRIMARY,
    "all-rounder": PURPLE,
    "wicketkeeper": TEAL,
}

FRANCHISE_COLORS = {
    "Chennai Super Kings": "#eab308",
    "Mumbai Indians": "#3b82f6",
    "Royal Challengers Bengaluru": "#ef4444",
    "Kolkata Knight Riders": "#8b5cf6",
    "Delhi Capitals": "#60a5fa",
    "Punjab Kings": "#f43f5e",
    "Rajasthan Royals": "#ec4899",
    "Sunrisers Hyderabad": "#f97316",
    "Gujarat Titans": "#6366f1",
    "Lucknow Super Giants": "#22d3ee",
}

FRANCHISE_SHORT = {
    "Chennai Super Kings": "CSK",
    "Mumbai Indians": "MI",
    "Royal Challengers Bengaluru": "RCB",
    "Kolkata Knight Riders": "KKR",
    "Delhi Capitals": "DC",
    "Punjab Kings": "PBKS",
    "Rajasthan Royals": "RR",
    "Sunrisers Hyderabad": "SRH",
    "Gujarat Titans": "GT",
    "Lucknow Super Giants": "LSG",
}

ROLE_ICON = {"batter": "🏏", "bowler": "🎯", "all-rounder": "⚡", "wicketkeeper": "🧤"}

_LOGO_DIR = Path(__file__).resolve().parent.parent / "assets" / "team_logos"


@lru_cache(maxsize=16)
def _logo_b64(short_code: str):
    path = _LOGO_DIR / f"{short_code}.jpg"
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


def team_logo(franchise_name: str, size: int = 56, radius: int = 12) -> str:
    short = FRANCHISE_SHORT.get(franchise_name, "")
    b64 = _logo_b64(short) if short else None
    if b64:
        return (
            f'<img src="data:image/jpeg;base64,{b64}" alt="{short}" '
            f'style="width:{size}px;height:{size}px;object-fit:contain;border-radius:{radius}px;'
            f'background:#fff;padding:4px;border:1px solid rgba(148,163,184,0.2);'
            f'box-shadow:{SHADOW_SM};flex-shrink:0;"/>'
        )
    color = FRANCHISE_COLORS.get(franchise_name, PRIMARY)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:{radius}px;'
        f'background:linear-gradient(140deg,{color},{color}88);display:flex;align-items:center;'
        f'justify-content:center;color:#fff;font-weight:800;font-size:{int(size*0.3)}px;flex-shrink:0;">{short or "?"}</div>'
    )


def _initials(name: str) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_circle(name: str, color: str = GOLD, size: int = 72) -> str:
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;flex-shrink:0;'
        f'background:linear-gradient(145deg,{color},{color}66);display:flex;align-items:center;'
        f'justify-content:center;color:#fff;font-weight:800;font-size:{int(size*0.34)}px;'
        f'font-family:Space Grotesk,Inter,sans-serif;box-shadow:{SHADOW_SM};'
        f'text-shadow:0 1px 3px rgba(0,0,0,0.4);">{_initials(name)}</div>'
    )


def inject_css(accent: str = GOLD):
    """accent = active franchise color -- drives the ambient glow so
    the whole app subtly re-tints when you switch teams (the
    'surprise' factor: CSK feels gold, MI feels blue)."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700;800&display=swap');

        html, body, [class*="css"] {{ font-family: 'Inter', -apple-system, sans-serif; font-size: 16px; }}

        .stApp {{
            background:
                radial-gradient(1000px 560px at 88% -8%, {accent}1f 0%, transparent 60%),
                radial-gradient(800px 500px at -5% 8%, {PRIMARY}14 0%, transparent 55%),
                {BG};
            color: {TEXT};
        }}

        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; }}
        .main .block-container {{ animation: csv-fade-up 0.4s ease; padding-top: 2.2rem; }}
        @keyframes csv-fade-up {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* ============== SIDEBAR: glass rail ============== */
        section[data-testid="stSidebar"] {{
            background: rgba(14,20,32,0.92);
            backdrop-filter: blur(14px);
            border-right: 1px solid {BORDER};
        }}
        section[data-testid="stSidebar"] * {{ color: {TEXT}; }}
        section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p {{
            color: {TEXT_FAINT} !important;
            font-size: 10.5px !important; font-weight: 800 !important;
            text-transform: uppercase; letter-spacing: 0.1em;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
            background: {BG_CARD} !important;
            border: 1px solid {BORDER_STRONG} !important;
            border-radius: 12px !important;
        }}

        div[data-testid="stSidebarNav"] a {{
            border-radius: 12px;
            padding: 10px 14px !important;
            margin: 3px 10px;
            transition: all 0.15s ease;
        }}
        div[data-testid="stSidebarNav"] a span {{
            color: {TEXT_DIM} !important;
            font-size: 14.5px !important; font-weight: 600 !important;
        }}
        div[data-testid="stSidebarNav"] a:hover {{ background: rgba(148,163,184,0.08); }}
        div[data-testid="stSidebarNav"] a:hover span {{ color: {TEXT} !important; }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: {BG_CARD};
            box-shadow: inset 0 0 0 1px {BORDER_STRONG}, {SHADOW_SM};
        }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] span {{
            color: #ffffff !important; font-weight: 700 !important;
        }}
        div[data-testid="stSidebarNav"] a[aria-current="page"]::after {{
            content: ""; display: inline-block; width: 6px; height: 6px;
            border-radius: 50%; background: {accent}; margin-left: auto;
        }}

        div[data-testid="stSidebarCollapseButton"] {{ opacity: 1 !important; visibility: visible !important; }}
        div[data-testid="stSidebarCollapseButton"] button {{
            background: rgba(148,163,184,0.12) !important; border-radius: 8px !important;
        }}
        div[data-testid="stSidebarCollapseButton"] button svg {{ fill: {TEXT} !important; color: {TEXT} !important; }}
        div[data-testid="collapsedControl"] {{ opacity: 1 !important; visibility: visible !important; }}
        div[data-testid="collapsedControl"] button {{
            background: {BG_CARD} !important;
            border: 1px solid {BORDER_STRONG} !important;
            border-radius: 8px !important;
        }}

        /* ============== Typography ============== */
        h1, h2, h3, h4 {{
            font-family: 'Space Grotesk', 'Inter', sans-serif !important;
            letter-spacing: -0.015em; color: {TEXT} !important;
        }}
        h2 {{ font-size: 26px !important; font-weight: 800 !important; }}
        h3 {{ font-size: 19px !important; font-weight: 700 !important; }}
        h4 {{ font-size: 16.5px !important; font-weight: 700 !important; }}
        .main div[data-testid="stWidgetLabel"] p {{
            font-size: 11px !important; font-weight: 800 !important;
            color: {TEXT_FAINT} !important;
            text-transform: uppercase; letter-spacing: 0.1em;
        }}
        .stCaption, div[data-testid="stCaptionContainer"] {{
            font-size: 13.5px !important; color: {TEXT_DIM} !important; line-height: 1.6;
        }}
        .main div[data-baseweb="select"] > div, .main .stTextInput input, .main .stNumberInput input {{
            background: {BG_CARD} !important;
            border-color: {BORDER_STRONG} !important;
            color: {TEXT} !important;
            font-size: 14.5px !important;
            border-radius: 12px !important;
        }}

        /* ============== Glass cards ============== */
        .csv-card {{
            background: rgba(22,27,38,0.85);
            backdrop-filter: blur(10px);
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 18px 22px;
            margin-bottom: 14px;
            box-shadow: {SHADOW};
            transition: transform 0.18s ease, border-color 0.18s ease;
        }}
        .csv-card:hover {{ transform: translateY(-2px); border-color: {BORDER_STRONG}; }}
        .csv-metric-label {{
            color: {TEXT_FAINT}; font-size: 10.5px; text-transform: uppercase;
            letter-spacing: 0.1em; font-weight: 800; margin-bottom: 7px;
        }}
        .csv-metric-value {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 30px; font-weight: 800; color: {TEXT}; line-height: 1.1;
        }}
        .csv-metric-value.gold {{ color: {GOLD_SOFT}; }}
        .csv-metric-value.green {{ color: {GREEN}; }}
        .csv-metric-value.red {{ color: {RED}; }}
        .csv-metric-value.blue {{ color: {BLUE}; }}
        .csv-metric-sub {{ color: {TEXT_DIM}; font-size: 12.5px; margin-top: 6px; font-weight: 600; }}
        .csv-progress {{ margin-top: 10px; height: 6px; border-radius: 999px; background: rgba(148,163,184,0.15); overflow: hidden; }}
        .csv-progress > div {{ height: 100%; border-radius: 999px; transition: width 0.7s ease; }}

        /* ============== Badge pills ============== */
        .csv-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 12px; border-radius: 999px;
            font-size: 12px; font-weight: 700;
            border: 1px solid {BORDER_STRONG}; background: rgba(148,163,184,0.08); color: {TEXT_DIM};
        }}
        .csv-pill.gold {{ color: {GOLD_SOFT}; border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.10); }}
        .csv-pill.green {{ color: {GREEN}; border-color: rgba(52,211,153,0.35); background: rgba(52,211,153,0.10); }}
        .csv-pill.red {{ color: {RED}; border-color: rgba(251,113,133,0.35); background: rgba(251,113,133,0.10); }}
        .csv-pill.blue {{ color: {BLUE}; border-color: rgba(96,165,250,0.35); background: rgba(96,165,250,0.10); }}

        /* ============== Team hero ============== */
        .csv-team-hero {{
            background:
                radial-gradient(420px 140px at 100% 0%, var(--team-color, {GOLD})22 0%, transparent 65%),
                rgba(22,27,38,0.85);
            backdrop-filter: blur(10px);
            border: 1px solid {BORDER};
            border-radius: 18px;
            padding: 20px 26px;
            display: flex; align-items: center; gap: 20px;
            box-shadow: {SHADOW};
            margin-bottom: 16px;
        }}
        .csv-team-name {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 26px; font-weight: 800; color: {TEXT}; line-height: 1.1;
        }}
        .csv-team-meta {{ color: {TEXT_DIM}; font-size: 13.5px; margin-top: 3px; font-weight: 600; }}

        /* ============== Segmented radio pills ============== */
        .main div[role="radiogroup"] {{ gap: 10px; }}
        .main div[role="radiogroup"] > label {{
            border: 1px solid {BORDER_STRONG};
            border-radius: 999px;
            padding: 9px 20px;
            background: {BG_CARD};
            transition: all 0.15s ease;
            cursor: pointer;
        }}
        .main div[role="radiogroup"] > label:hover {{ border-color: {PRIMARY}; transform: translateY(-1px); }}
        .main div[role="radiogroup"] > label > div:first-child {{ display: none; }}
        .main div[role="radiogroup"] > label p {{ font-weight: 700; font-size: 14px; color: {TEXT_DIM}; }}
        .main div[role="radiogroup"] > label:has(input:checked) {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
            border-color: transparent;
            box-shadow: 0 4px 16px rgba(59,130,246,0.35);
        }}
        .main div[role="radiogroup"] > label:has(input:checked) p {{ color: #ffffff !important; }}

        /* ============== Buttons ============== */
        .stButton > button {{
            border-radius: 12px; font-weight: 700; font-size: 14px;
            border: 1px solid {BORDER_STRONG};
            background: {BG_CARD}; color: {TEXT};
            padding: 0.5rem 1rem;
            transition: all 0.15s ease;
        }}
        .stButton > button:hover {{ border-color: {PRIMARY}; color: {BLUE}; transform: translateY(-1px); }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
            border: none; color: #ffffff !important;
            box-shadow: 0 4px 16px rgba(59,130,246,0.35);
        }}
        .stButton > button[kind="primary"]:hover {{ box-shadow: 0 6px 22px rgba(59,130,246,0.5); }}
        .stButton > button[kind="primary"] p {{ color: #ffffff !important; }}

        /* ============== Chat ============== */
        div[data-testid="stChatMessage"] {{
            background: rgba(22,27,38,0.85);
            backdrop-filter: blur(10px);
            border: 1px solid {BORDER};
            border-radius: 14px;
            box-shadow: {SHADOW_SM};
            padding: 12px 14px;
        }}
        div[data-testid="stChatMessage"] p, div[data-testid="stChatMessage"] li {{ color: {TEXT}; }}
        div[data-testid="stChatMessage"] a {{ color: {BLUE}; font-weight: 600; word-break: break-all; }}
        div[data-testid="stChatInput"] {{
            max-width: 860px; margin: 0 auto;
            background: rgba(22,27,38,0.92) !important;
            backdrop-filter: blur(14px);
            border: 1px solid {BORDER_STRONG};
            border-radius: 16px;
            box-shadow: 0 12px 40px rgba(0,0,0,0.45);
        }}
        div[data-testid="stChatInput"]:focus-within {{ border-color: {PRIMARY}; }}
        div[data-testid="stChatInput"] textarea {{ font-size: 15px !important; color: {TEXT} !important; }}
        div[data-testid="stBottom"] {{ background: transparent !important; }}
        div[data-testid="stBottom"] > div {{ background: transparent !important; }}

        /* ============== Ticker ============== */
        .csv-ticker {{
            overflow: hidden; white-space: nowrap;
            background: rgba(22,27,38,0.7);
            backdrop-filter: blur(8px);
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 9px 0; margin-bottom: 16px;
        }}
        .csv-ticker-track {{
            display: inline-flex; align-items: center; gap: 36px; padding-left: 36px;
            animation: csv-ticker-scroll 45s linear infinite;
        }}
        .csv-ticker:hover .csv-ticker-track {{ animation-play-state: paused; }}
        .csv-ticker-item {{
            display: inline-flex; align-items: center; gap: 9px;
            color: {TEXT_DIM}; font-size: 13px; font-weight: 600;
        }}
        .csv-ticker-item b {{ color: {TEXT}; font-weight: 800; }}
        .csv-ticker-item img {{ box-shadow: none !important; border: none !important; padding: 2px !important; }}
        @keyframes csv-ticker-scroll {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-50%); }} }}

        div[data-testid="stDataFrame"] {{
            border-radius: 14px; overflow: hidden;
            border: 1px solid {BORDER}; box-shadow: {SHADOW_SM};
        }}
        .stAlert {{ border-radius: 12px; font-size: 14px; }}
        div[data-testid="stExpander"] {{
            background: rgba(22,27,38,0.7); border: 1px solid {BORDER}; border-radius: 12px;
        }}
        div[data-testid="stExpander"] summary p {{ color: {TEXT}; font-weight: 600; }}
        hr {{ border-color: {BORDER}; margin: 1.4rem 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, sub: str = "", tone: str = "",
                progress: float = None, progress_color: str = PRIMARY) -> str:
    """Glass stat card; progress (0-100) adds the inline bar from the
    approved prototype's executive cards."""
    bar = ""
    if progress is not None:
        pct = max(0.0, min(float(progress), 100.0))
        bar = f'<div class="csv-progress"><div style="width:{pct:.1f}%;background:{progress_color}"></div></div>'
    return f"""
    <div class="csv-card" style="padding:16px 20px">
        <div class="csv-metric-label">{label}</div>
        <div class="csv-metric-value {tone}">{value}</div>
        <div class="csv-metric-sub">{sub}</div>
        {bar}
    </div>
    """


def pill(text: str, tone: str = "") -> str:
    return f'<span class="csv-pill {tone}">{text}</span>'


def team_hero(franchise_name: str, subtitle: str = "") -> str:
    color = FRANCHISE_COLORS.get(franchise_name, GOLD)
    return f"""
    <div class="csv-team-hero" style="--team-color:{color}">
        {team_logo(franchise_name, size=68, radius=14)}
        <div>
            <div class="csv-team-name">{franchise_name}</div>
            <div class="csv-team-meta">{subtitle}</div>
        </div>
    </div>
    """

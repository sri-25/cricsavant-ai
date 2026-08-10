"""CricSavant AI -- visual theme.

v8 -- port of the approved Lovable prototype ("Strategic Auction &
War Room Console"): near-black terminal aesthetic, JetBrains-Mono
uppercase micro-labels, hot-magenta primary CTAs, amber monospace
money figures, top HEADER BAR (no sidebar) with franchise selector +
stat chips, tabbed sections, and the Chief Analyst AI docked as a
right-hand panel. User-locked constraints honored: real team logos
(assets/team_logos), the league ticker, and every existing feature.
"""

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

# ---- Tokens (sampled from the Lovable prototype) -------------------
BG = "#0a0c10"
BG_PANEL = "#0e1117"
BG_CARD = "#11141b"
BG_CARD_ELEV = "#161a23"
BORDER = "rgba(148,163,184,0.12)"
BORDER_STRONG = "rgba(148,163,184,0.26)"

MAGENTA = "#e11d74"          # primary CTA ("EXECUTE WINNING BID")
MAGENTA_SOFT = "#f472b6"
AMBER = "#fbbf24"            # money figures, mono
PRIMARY = MAGENTA
PRIMARY_DARK = "#be185d"
GOLD = AMBER
GOLD_SOFT = "#fcd34d"
BLUE = "#60a5fa"
GREEN = "#34d399"
RED = "#fb7185"
PURPLE = "#a78bfa"
TEAL = "#2dd4bf"

TEXT = "#e5e9f0"
TEXT_DIM = "#94a3b8"
TEXT_FAINT = "#64748b"

MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, monospace"

SHADOW = "0 8px 32px rgba(0,0,0,0.45), 0 0 0 1px rgba(148,163,184,0.05) inset"
SHADOW_SM = "0 2px 12px rgba(0,0,0,0.35)"

ROLE_COLOR = {"batter": AMBER, "bowler": BLUE, "all-rounder": PURPLE, "wicketkeeper": TEAL}

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
    """Real team logo (user-locked requirement)."""
    short = FRANCHISE_SHORT.get(franchise_name, "")
    b64 = _logo_b64(short) if short else None
    if b64:
        return (
            f'<img src="data:image/jpeg;base64,{b64}" alt="{short}" '
            f'style="width:{size}px;height:{size}px;object-fit:contain;border-radius:{radius}px;'
            f'background:#fff;padding:3px;border:1px solid rgba(148,163,184,0.18);'
            f'box-shadow:{SHADOW_SM};flex-shrink:0;"/>'
        )
    color = FRANCHISE_COLORS.get(franchise_name, MAGENTA)
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


def avatar_circle(name: str, color: str = AMBER, size: int = 72) -> str:
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;flex-shrink:0;'
        f'background:linear-gradient(145deg,{color},{color}55);display:flex;align-items:center;'
        f'justify-content:center;color:#fff;font-weight:800;font-size:{int(size*0.34)}px;'
        f'font-family:{MONO};box-shadow:{SHADOW_SM};text-shadow:0 1px 3px rgba(0,0,0,0.5);">{_initials(name)}</div>'
    )


def inject_css(accent: str = MAGENTA):
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700;800&family=Space+Grotesk:wght@600;700;800&display=swap');

        html, body, [class*="css"] {{ font-family: 'Inter', -apple-system, sans-serif; font-size: 15.5px; }}

        .stApp {{
            background:
                radial-gradient(900px 480px at 90% -10%, {accent}17 0%, transparent 60%),
                radial-gradient(700px 420px at 0% 0%, rgba(96,165,250,0.07) 0%, transparent 55%),
                {BG};
            color: {TEXT};
        }}

        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
        .main .block-container {{
            animation: csv-fade-up 0.4s ease;
            padding-top: 1.4rem;
            padding-left: 3rem; padding-right: 3rem;
            max-width: 100%;
        }}
        @keyframes csv-fade-up {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        /* Vertical rhythm: sections breathe instead of stacking flush */
        .main h4 {{ margin-top: 1.8rem !important; margin-bottom: 0.7rem !important; }}
        .main h3 {{ margin-top: 1.4rem !important; }}

        /* ============ Sidebar: glass rail, war-room skin ============ */
        section[data-testid="stSidebar"] {{
            background: rgba(14,17,23,0.96);
            backdrop-filter: blur(14px);
            border-right: 1px solid {BORDER};
            min-width: 300px !important;
        }}
        section[data-testid="stSidebar"] * {{ color: {TEXT}; }}
        section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p {{
            font-family: {MONO} !important;
            color: {TEXT_FAINT} !important;
            font-size: 9.5px !important; font-weight: 700 !important;
            text-transform: uppercase; letter-spacing: 0.16em;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
            background: {BG_CARD} !important;
            border: 1px solid {BORDER_STRONG} !important;
            border-radius: 10px !important;
        }}
        div[data-testid="stSidebarNav"] a {{
            border-radius: 10px;
            padding: 10px 14px !important;
            margin: 3px 10px;
            transition: all 0.15s ease;
        }}
        div[data-testid="stSidebarNav"] a span {{
            font-family: {MONO} !important;
            color: {TEXT_DIM} !important;
            font-size: 11.5px !important; font-weight: 700 !important;
            letter-spacing: 0.12em; text-transform: uppercase;
        }}
        div[data-testid="stSidebarNav"] a:hover {{ background: rgba(148,163,184,0.08); }}
        div[data-testid="stSidebarNav"] a:hover span {{ color: {TEXT} !important; }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: {BG_CARD_ELEV};
            box-shadow: inset 0 0 0 1px {BORDER_STRONG}, 0 0 14px {MAGENTA}22;
        }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: {MAGENTA_SOFT} !important; }}
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

        /* ============ Mono micro-label system ============ */
        .csv-mono, .csv-metric-label, .csv-metric-sub, .stCaption,
        div[data-testid="stCaptionContainer"], div[data-testid="stWidgetLabel"] p {{
            font-family: {MONO} !important;
        }}
        .main div[data-testid="stWidgetLabel"] p {{
            font-size: 10px !important; font-weight: 700 !important;
            color: {TEXT_FAINT} !important;
            text-transform: uppercase; letter-spacing: 0.14em;
        }}
        .stCaption, div[data-testid="stCaptionContainer"] {{
            font-size: 11.5px !important; color: {TEXT_DIM} !important;
            line-height: 1.7; letter-spacing: 0.04em;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Space Grotesk', 'Inter', sans-serif !important;
            letter-spacing: -0.01em; color: {TEXT} !important;
        }}
        h2 {{ font-size: 24px !important; font-weight: 800 !important; }}
        h3 {{ font-size: 18px !important; font-weight: 700 !important; }}
        h4 {{ font-size: 15.5px !important; font-weight: 700 !important; }}

        .main div[data-baseweb="select"] > div, .main .stTextInput input, .main .stNumberInput input {{
            background: {BG_CARD} !important;
            border-color: {BORDER_STRONG} !important;
            color: {TEXT} !important;
            font-size: 14px !important;
            border-radius: 10px !important;
        }}

        /* ============ Header bar ============ */
        .csv-header {{
            display: flex; align-items: center; gap: 16px;
            padding: 14px 20px;
            background: rgba(17,20,27,0.9);
            backdrop-filter: blur(12px);
            border: 1px solid {BORDER};
            border-radius: 14px;
            margin-bottom: 6px;
        }}
        .csv-brand-mark {{
            width: 40px; height: 40px; border-radius: 11px;
            background: linear-gradient(140deg, {MAGENTA}, {PRIMARY_DARK});
            display: flex; align-items: center; justify-content: center;
            font-size: 20px; box-shadow: 0 4px 18px {MAGENTA}55;
        }}
        .csv-brand-title {{ font-family: 'Space Grotesk'; font-weight: 800; font-size: 19px; color: {TEXT}; }}
        .csv-brand-title em {{ font-style: normal; color: {MAGENTA_SOFT}; }}
        .csv-brand-sub {{
            font-family: {MONO}; font-size: 9.5px; letter-spacing: 0.18em;
            text-transform: uppercase; color: {TEXT_FAINT}; margin-top: 2px;
        }}
        .csv-live {{
            display: inline-flex; align-items: center; gap: 7px;
            font-family: {MONO}; font-size: 10px; font-weight: 700;
            letter-spacing: 0.14em; text-transform: uppercase;
            color: {GREEN}; background: rgba(52,211,153,0.08);
            border: 1px solid rgba(52,211,153,0.3);
            padding: 6px 12px; border-radius: 999px;
        }}
        .csv-live::before {{
            content: ""; width: 7px; height: 7px; border-radius: 50%;
            background: {GREEN}; animation: csv-pulse 1.6s ease infinite;
        }}
        @keyframes csv-pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}

        .csv-chip {{
            display: flex; flex-direction: column; gap: 3px;
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 9px 16px;
        }}
        .csv-chip-label {{
            font-family: {MONO}; font-size: 9px; font-weight: 700;
            letter-spacing: 0.16em; text-transform: uppercase; color: {TEXT_FAINT};
        }}
        .csv-chip-value {{ font-family: {MONO}; font-size: 15px; font-weight: 800; color: {AMBER}; }}
        .csv-chip-value.ok {{ color: {GREEN}; }}
        .csv-chip-value.bad {{ color: {RED}; }}

        /* ============ Tabs: war-room console style ============ */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px;
            background: rgba(17,20,27,0.8);
            padding: 6px;
            border-radius: 12px;
            border: 1px solid {BORDER};
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 40px; border-radius: 9px;
            color: {TEXT_DIM};
            padding: 0 18px;
            background: transparent;
        }}
        .stTabs [data-baseweb="tab"] p {{
            font-family: {MONO} !important;
            font-size: 11.5px !important; font-weight: 700 !important;
            letter-spacing: 0.12em; text-transform: uppercase;
        }}
        .stTabs [aria-selected="true"] {{
            background: {BG_CARD_ELEV};
            box-shadow: inset 0 0 0 1px {BORDER_STRONG}, 0 0 14px {MAGENTA}22;
        }}
        .stTabs [aria-selected="true"] p {{ color: {MAGENTA_SOFT} !important; }}
        .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

        /* ============ Cards ============ */
        .csv-card {{
            background: rgba(17,20,27,0.88);
            backdrop-filter: blur(10px);
            border: 1px solid {BORDER};
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 12px;
            box-shadow: {SHADOW};
            transition: transform 0.16s ease, border-color 0.16s ease;
        }}
        .csv-card:hover {{ transform: translateY(-2px); border-color: {BORDER_STRONG}; }}
        .csv-metric-label {{
            color: {TEXT_FAINT}; font-size: 9.5px; text-transform: uppercase;
            letter-spacing: 0.16em; font-weight: 700; margin-bottom: 7px;
        }}
        .csv-metric-value {{
            font-family: {MONO};
            font-size: 24px; font-weight: 800; color: {TEXT}; line-height: 1.15;
        }}
        .csv-metric-value.gold {{ color: {AMBER}; }}
        .csv-metric-value.green {{ color: {GREEN}; }}
        .csv-metric-value.red {{ color: {RED}; }}
        .csv-metric-value.blue {{ color: {BLUE}; }}
        .csv-metric-sub {{ color: {TEXT_DIM}; font-size: 10.5px; margin-top: 6px; font-weight: 600; letter-spacing: 0.05em; }}
        .csv-progress {{ margin-top: 10px; height: 5px; border-radius: 999px; background: rgba(148,163,184,0.14); overflow: hidden; }}
        .csv-progress > div {{
            height: 100%; border-radius: 999px; transition: width 0.7s ease;
            background: linear-gradient(90deg, {MAGENTA}, {AMBER});
        }}

        /* ============ Pills ============ */
        .csv-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 11px; border-radius: 6px;
            font-family: {MONO}; font-size: 10px; font-weight: 700;
            letter-spacing: 0.1em; text-transform: uppercase;
            border: 1px solid {BORDER_STRONG}; background: rgba(148,163,184,0.07); color: {TEXT_DIM};
        }}
        .csv-pill.gold {{ color: {AMBER}; border-color: rgba(251,191,36,0.4); background: rgba(251,191,36,0.08); }}
        .csv-pill.green {{ color: {GREEN}; border-color: rgba(52,211,153,0.4); background: rgba(52,211,153,0.08); }}
        .csv-pill.red {{ color: {RED}; border-color: rgba(251,113,133,0.4); background: rgba(251,113,133,0.08); }}
        .csv-pill.blue {{ color: {BLUE}; border-color: rgba(96,165,250,0.4); background: rgba(96,165,250,0.08); }}

        /* ============ Team hero ============ */
        .csv-team-hero {{
            background:
                radial-gradient(420px 130px at 100% 0%, var(--team-color, {MAGENTA})1c 0%, transparent 65%),
                rgba(17,20,27,0.88);
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 18px 24px;
            display: flex; align-items: center; gap: 18px;
            box-shadow: {SHADOW};
            margin-bottom: 14px;
        }}
        .csv-team-name {{ font-family: 'Space Grotesk'; font-size: 23px; font-weight: 800; color: {TEXT}; line-height: 1.1; }}
        .csv-team-meta {{
            font-family: {MONO}; color: {TEXT_DIM}; font-size: 10.5px;
            margin-top: 4px; letter-spacing: 0.08em; text-transform: uppercase;
        }}

        /* ============ Segmented radio ============ */
        .main div[role="radiogroup"] {{ gap: 8px; }}
        .main div[role="radiogroup"] > label {{
            border: 1px solid {BORDER_STRONG};
            border-radius: 9px;
            padding: 8px 16px;
            background: {BG_CARD};
            transition: all 0.15s ease;
            cursor: pointer;
        }}
        .main div[role="radiogroup"] > label:hover {{ border-color: {MAGENTA}; transform: translateY(-1px); }}
        .main div[role="radiogroup"] > label > div:first-child {{ display: none; }}
        .main div[role="radiogroup"] > label p {{
            font-family: {MONO}; font-weight: 700; font-size: 11px;
            letter-spacing: 0.08em; text-transform: uppercase; color: {TEXT_DIM};
        }}
        .main div[role="radiogroup"] > label:has(input:checked) {{
            background: linear-gradient(135deg, {MAGENTA} 0%, {PRIMARY_DARK} 100%);
            border-color: transparent;
            box-shadow: 0 4px 18px {MAGENTA}55;
        }}
        .main div[role="radiogroup"] > label:has(input:checked) p {{ color: #ffffff !important; }}

        /* ============ Buttons ============ */
        .stButton > button {{
            border-radius: 9px; font-weight: 700; font-size: 12.5px;
            font-family: {MONO}; letter-spacing: 0.06em;
            border: 1px solid {BORDER_STRONG};
            background: {BG_CARD}; color: {TEXT};
            padding: 0.45rem 0.95rem;
            transition: all 0.15s ease;
        }}
        .stButton > button:hover {{ border-color: {MAGENTA}; color: {MAGENTA_SOFT}; transform: translateY(-1px); }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {MAGENTA} 0%, {PRIMARY_DARK} 100%);
            border: none; color: #ffffff !important;
            box-shadow: 0 4px 18px {MAGENTA}55;
        }}
        .stButton > button[kind="primary"]:hover {{ box-shadow: 0 6px 26px {MAGENTA}77; }}
        .stButton > button[kind="primary"] p {{ color: #ffffff !important; }}

        /* ============ Chat / Chief Analyst panel ============ */
        div[data-testid="stChatMessage"] {{
            background: rgba(17,20,27,0.9);
            border: 1px solid {BORDER};
            border-radius: 12px;
            box-shadow: {SHADOW_SM};
            padding: 11px 13px;
        }}
        div[data-testid="stChatMessage"] p, div[data-testid="stChatMessage"] li {{ color: {TEXT}; font-size: 14px; }}
        div[data-testid="stChatMessage"] a {{ color: {BLUE}; font-weight: 600; word-break: break-all; }}
        div[data-testid="stChatInput"] {{
            background: rgba(17,20,27,0.95) !important;
            border: 1px solid {BORDER_STRONG};
            border-radius: 12px;
            box-shadow: 0 10px 34px rgba(0,0,0,0.5);
        }}
        div[data-testid="stChatInput"]:focus-within {{ border-color: {MAGENTA}; }}
        div[data-testid="stChatInput"] textarea {{ font-size: 14px !important; color: {TEXT} !important; }}
        div[data-testid="stBottom"] {{ background: transparent !important; }}
        div[data-testid="stBottom"] > div {{ background: transparent !important; }}

        .csv-reco {{
            border: 1px solid rgba(52,211,153,0.35);
            background: rgba(52,211,153,0.06);
            border-radius: 12px;
            padding: 14px 16px;
            margin-top: 10px;
        }}
        .csv-reco-label {{
            font-family: {MONO}; font-size: 9.5px; font-weight: 800;
            letter-spacing: 0.16em; color: {GREEN}; text-transform: uppercase; margin-bottom: 6px;
        }}

        /* ============ Ticker (user-locked feature) ============ */
        .csv-ticker {{
            overflow: hidden; white-space: nowrap;
            background: rgba(17,20,27,0.75);
            border: 1px solid {BORDER};
            border-radius: 11px;
            padding: 8px 0; margin-bottom: 14px;
        }}
        .csv-ticker-track {{
            display: inline-flex; align-items: center; gap: 34px; padding-left: 34px;
            animation: csv-ticker-scroll 45s linear infinite;
        }}
        .csv-ticker:hover .csv-ticker-track {{ animation-play-state: paused; }}
        .csv-ticker-item {{
            display: inline-flex; align-items: center; gap: 8px;
            font-family: {MONO}; color: {TEXT_DIM}; font-size: 11px;
            font-weight: 600; letter-spacing: 0.05em;
        }}
        .csv-ticker-item b {{ color: {AMBER}; font-weight: 800; }}
        .csv-ticker-item img {{ box-shadow: none !important; border: none !important; padding: 2px !important; }}
        @keyframes csv-ticker-scroll {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-50%); }} }}

        div[data-testid="stDataFrame"] {{
            border-radius: 12px; overflow: hidden;
            border: 1px solid {BORDER}; box-shadow: {SHADOW_SM};
        }}
        .stAlert {{ border-radius: 11px; font-size: 13.5px; }}
        div[data-testid="stExpander"] {{
            background: rgba(17,20,27,0.7); border: 1px solid {BORDER}; border-radius: 11px;
        }}
        div[data-testid="stExpander"] summary p {{
            font-family: {MONO} !important; color: {TEXT_DIM};
            font-weight: 700; font-size: 11px !important;
            letter-spacing: 0.1em; text-transform: uppercase;
        }}
        hr {{ border-color: {BORDER}; margin: 1.2rem 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, sub: str = "", tone: str = "",
                progress: float = None, progress_color: str = None) -> str:
    bar = ""
    if progress is not None:
        pct = max(0.0, min(float(progress), 100.0))
        grad = f"background:{progress_color}" if progress_color else ""
        bar = f'<div class="csv-progress"><div style="width:{pct:.1f}%;{grad}"></div></div>'
    return f"""
    <div class="csv-card" style="padding:14px 18px">
        <div class="csv-metric-label">{label}</div>
        <div class="csv-metric-value {tone}">{value}</div>
        <div class="csv-metric-sub">{sub}</div>
        {bar}
    </div>
    """


def pill(text: str, tone: str = "") -> str:
    return f'<span class="csv-pill {tone}">{text}</span>'


def team_hero(franchise_name: str, subtitle: str = "") -> str:
    color = FRANCHISE_COLORS.get(franchise_name, MAGENTA)
    return f"""
    <div class="csv-team-hero" style="--team-color:{color}">
        {team_logo(franchise_name, size=62, radius=13)}
        <div>
            <div class="csv-team-name">{franchise_name}</div>
            <div class="csv-team-meta">{subtitle}</div>
        </div>
    </div>
    """


def header_bar(brand_sub: str = "Strategic Auction & War Room Console") -> str:
    """Brand block of the Lovable-style top header. The franchise
    selector + stat chips are real Streamlit widgets rendered beside
    this by the app shell."""
    return f"""
    <div class="csv-header">
        <div class="csv-brand-mark">🏏</div>
        <div style="flex:1">
            <div class="csv-brand-title">CricSavant <em>AI</em></div>
            <div class="csv-brand-sub">{brand_sub}</div>
        </div>
        <span class="csv-live">Live Lakehouse Connected</span>
    </div>
    """


def stat_chip(label: str, value: str, tone: str = "") -> str:
    return f"""
    <div class="csv-chip">
        <div class="csv-chip-label">{label}</div>
        <div class="csv-chip-value {tone}">{value}</div>
    </div>
    """

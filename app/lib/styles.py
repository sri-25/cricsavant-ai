"""CricSavant AI -- visual theme.

Presentation only: CSS injection, static lookup tables, logo helpers.

v5 -- contrast-first rebuild after direct feedback that v4's light
theme was "clean but the color and formatting is shit, I literally
cannot see a lot of things." The failures were real: amber text on
white (~3:1), faint gray subtext, translucent pill washes. This
version is built around WCAG-AA-or-better contrast everywhere:
  - near-black ink (#111827) on white cards for all primary text
  - ONE strong primary (deep royal blue) for actions, AA on white
  - amber demoted to a small highlight, darkened to #92600a when used
    as text so it actually reads
  - solid, dark pill text on light tinted chips (no translucent mush)
  - dark navy SIDEBAR against the light main area -- the classic
    admin-dashboard split that makes the team logo pop and gives the
    side panel real presence instead of gray-on-gray nav links.
"""

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

# ---- Palette -------------------------------------------------------
BG = "#f6f7f9"           # main page
BG_PANEL = "#101b33"     # SIDEBAR: deep navy (dark panel, light page)
BG_CARD = "#ffffff"
BG_CARD_ELEV = "#ffffff"
BORDER = "rgba(17,24,39,0.12)"
BORDER_STRONG = "rgba(17,24,39,0.25)"

PRIMARY = "#1d4ed8"      # deep royal blue -- buttons, links, active states
PRIMARY_DARK = "#173db4"
GOLD = "#92600a"         # amber-as-TEXT: darkened to read on white
GOLD_SOFT = "#b45309"    # amber for borders/underlines, never body text
BLUE = "#1d4ed8"
GREEN = "#047857"
RED = "#b91c1c"
PURPLE = "#6d28d9"
TEAL = "#0f766e"

TEXT = "#111827"         # near-black ink
TEXT_DIM = "#3f4a5f"     # secondary -- still dark enough to read
TEXT_FAINT = "#64748b"   # tertiary only (timestamps, hints)

# Sidebar-side (light-on-navy) counterparts
SIDE_TEXT = "#f1f5f9"
SIDE_DIM = "#9fb0cc"

SHADOW = "0 1px 3px rgba(15,23,42,0.08), 0 6px 18px rgba(15,23,42,0.07)"
SHADOW_SM = "0 1px 2px rgba(15,23,42,0.06), 0 2px 8px rgba(15,23,42,0.06)"

ROLE_COLOR = {
    "batter": GOLD_SOFT,
    "bowler": BLUE,
    "all-rounder": PURPLE,
    "wicketkeeper": TEAL,
}

FRANCHISE_COLORS = {
    "Chennai Super Kings": "#d4a900",
    "Mumbai Indians": "#1d5fc4",
    "Royal Challengers Bengaluru": "#c8102e",
    "Kolkata Knight Riders": "#5b2c8d",
    "Delhi Capitals": "#1d4ed8",
    "Punjab Kings": "#d11f2f",
    "Rajasthan Royals": "#d61f8d",
    "Sunrisers Hyderabad": "#dd5400",
    "Gujarat Titans": "#1b2a5b",
    "Lucknow Super Giants": "#0284ad",
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

ROLE_ICON = {
    "batter": "🏏",
    "bowler": "🎯",
    "all-rounder": "⚡",
    "wicketkeeper": "🧤",
}

_LOGO_DIR = Path(__file__).resolve().parent.parent / "assets" / "team_logos"


@lru_cache(maxsize=16)
def _logo_b64(short_code: str):
    path = _LOGO_DIR / f"{short_code}.jpg"
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


def team_logo(franchise_name: str, size: int = 56, radius: int = 12) -> str:
    """<img> tag for the real team logo (user-supplied assets), on a
    white tile so it reads identically on the navy sidebar and the
    light main area. Colored-initials fallback only if a file is
    missing -- never a broken-image icon.
    """
    short = FRANCHISE_SHORT.get(franchise_name, "")
    b64 = _logo_b64(short) if short else None
    if b64:
        return (
            f'<img src="data:image/jpeg;base64,{b64}" alt="{short}" '
            f'style="width:{size}px;height:{size}px;object-fit:contain;border-radius:{radius}px;'
            f'background:#fff;padding:4px;border:1px solid rgba(17,24,39,0.10);box-shadow:{SHADOW_SM};flex-shrink:0;"/>'
        )
    color = FRANCHISE_COLORS.get(franchise_name, PRIMARY)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:{radius}px;background:{color};'
        f'display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;'
        f'font-size:{int(size*0.3)}px;flex-shrink:0;">{short or "?"}</div>'
    )


def _initials(name: str) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_circle(name: str, color: str = GOLD_SOFT, size: int = 72) -> str:
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;flex-shrink:0;'
        f'background:linear-gradient(145deg,{color},{color}d9);display:flex;align-items:center;'
        f'justify-content:center;color:#fff;font-weight:800;font-size:{int(size*0.34)}px;'
        f'font-family:Space Grotesk,Inter,sans-serif;box-shadow:{SHADOW_SM};'
        f'text-shadow:0 1px 2px rgba(0,0,0,0.3);">{_initials(name)}</div>'
    )


def inject_css():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 16px;
        }}
        .stApp {{ background: {BG}; color: {TEXT}; }}
        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; }}

        /* ================= SIDEBAR: dark navy panel ================= */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #13203c 0%, {BG_PANEL} 100%);
            border-right: none;
        }}
        section[data-testid="stSidebar"] * {{ color: {SIDE_TEXT}; }}
        section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p {{
            color: {SIDE_DIM} !important;
            font-size: 12.5px !important; font-weight: 700 !important;
            text-transform: uppercase; letter-spacing: 0.06em;
        }}
        /* Franchise selectbox stays a WHITE control on navy -- max contrast */
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
            background: #ffffff !important;
            border-color: rgba(255,255,255,0.25) !important;
            border-radius: 10px !important;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div * {{ color: {TEXT} !important; }}

        /* st.navigation links -> real nav items, not gray afterthoughts */
        div[data-testid="stSidebarNav"] a {{
            border-radius: 10px;
            padding: 10px 14px !important;
            margin: 2px 8px;
        }}
        div[data-testid="stSidebarNav"] a span {{
            color: {SIDE_DIM} !important;
            font-size: 15.5px !important; font-weight: 600 !important;
        }}
        div[data-testid="stSidebarNav"] a:hover {{ background: rgba(255,255,255,0.08); }}
        div[data-testid="stSidebarNav"] a:hover span {{ color: {SIDE_TEXT} !important; }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: rgba(255,255,255,0.14);
            box-shadow: inset 3px 0 0 #f59e0b;
        }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] span {{
            color: #ffffff !important; font-weight: 700 !important;
        }}

        /* ================= MAIN AREA typography ================= */
        h1, h2, h3, h4 {{
            font-family: 'Space Grotesk', 'Inter', sans-serif !important;
            letter-spacing: -0.015em;
            color: {TEXT} !important;
        }}
        h2 {{ font-size: 28px !important; font-weight: 800 !important; }}
        h3 {{ font-size: 21px !important; font-weight: 700 !important; }}
        h4 {{ font-size: 17.5px !important; font-weight: 700 !important; }}
        .main p, .main li, .main .stMarkdown {{ color: {TEXT}; }}
        .main div[data-testid="stWidgetLabel"] p {{
            font-size: 13px !important; font-weight: 700 !important;
            color: {TEXT_DIM} !important;
            text-transform: uppercase; letter-spacing: 0.05em;
        }}
        .stCaption, div[data-testid="stCaptionContainer"] {{
            font-size: 14px !important;
            color: {TEXT_DIM} !important;   /* dark enough to actually read */
            line-height: 1.55;
        }}
        .main div[data-baseweb="select"] > div, .main .stTextInput input, .main .stNumberInput input {{
            background: {BG_CARD} !important;
            border-color: {BORDER_STRONG} !important;
            color: {TEXT} !important;
            font-size: 15px !important;
            border-radius: 10px !important;
        }}

        /* ================= Motion & modern feel ================= */
        .main .block-container {{ animation: csv-fade-up 0.35s ease; }}
        @keyframes csv-fade-up {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* Sidebar collapse/expand arrows: invisible by default (user
        literally could not find them) -- forced visible, white chip on
        the navy rail, gray chip when the rail is collapsed. */
        div[data-testid="stSidebarCollapseButton"] {{ opacity: 1 !important; visibility: visible !important; }}
        div[data-testid="stSidebarCollapseButton"] button {{
            background: rgba(255,255,255,0.14) !important;
            border-radius: 8px !important;
        }}
        div[data-testid="stSidebarCollapseButton"] button svg {{ fill: #ffffff !important; color: #ffffff !important; }}
        div[data-testid="collapsedControl"] {{ opacity: 1 !important; visibility: visible !important; }}
        div[data-testid="collapsedControl"] button {{
            background: {BG_CARD} !important;
            border: 1.5px solid {BORDER_STRONG} !important;
            border-radius: 8px !important;
            box-shadow: {SHADOW_SM};
        }}

        /* Radio groups -> segmented pill control (shadcn-style), not
        1998 radio circles. Falls back gracefully if Streamlit's DOM
        shifts: worst case you get standard radios again. */
        .main div[role="radiogroup"] {{ gap: 10px; }}
        .main div[role="radiogroup"] > label {{
            border: 1.5px solid {BORDER_STRONG};
            border-radius: 999px;
            padding: 9px 20px;
            background: {BG_CARD};
            box-shadow: {SHADOW_SM};
            transition: all 0.15s ease;
            cursor: pointer;
        }}
        .main div[role="radiogroup"] > label:hover {{ border-color: {PRIMARY}; transform: translateY(-1px); }}
        .main div[role="radiogroup"] > label > div:first-child {{ display: none; }}  /* hide the circle */
        .main div[role="radiogroup"] > label p {{ font-weight: 700; font-size: 14.5px; }}
        .main div[role="radiogroup"] > label:has(input:checked) {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
            border-color: {PRIMARY};
            box-shadow: 0 2px 10px rgba(29,78,216,0.35);
        }}
        .main div[role="radiogroup"] > label:has(input:checked) p {{ color: #ffffff !important; }}

        /* ================= Cards / metrics ================= */
        .csv-card {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 18px 22px;
            margin-bottom: 14px;
            box-shadow: {SHADOW};
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .csv-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(15,23,42,0.08), 0 12px 28px rgba(15,23,42,0.10);
        }}
        .csv-metric-label {{
            color: {TEXT_DIM};
            font-size: 12.5px; text-transform: uppercase;
            letter-spacing: 0.06em; font-weight: 700; margin-bottom: 6px;
        }}
        .csv-metric-value {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 32px; font-weight: 800; color: {TEXT}; line-height: 1.1;
        }}
        .csv-metric-value.gold {{ color: {GOLD}; }}
        .csv-metric-value.green {{ color: {GREEN}; }}
        .csv-metric-value.red {{ color: {RED}; }}
        .csv-metric-value.blue {{ color: {BLUE}; }}
        .csv-metric-sub {{ color: {TEXT_DIM}; font-size: 13px; margin-top: 5px; font-weight: 600; }}

        /* ================= Pills: solid ink on tinted chips ========== */
        .csv-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 5px 13px; border-radius: 999px;
            font-size: 13px; font-weight: 700;
            border: 1.5px solid {BORDER_STRONG}; background: #eef1f5; color: {TEXT_DIM};
        }}
        .csv-pill.gold {{ color: #78350f; border-color: #d97706; background: #fef3c7; }}
        .csv-pill.green {{ color: #064e3b; border-color: #059669; background: #d1fae5; }}
        .csv-pill.red {{ color: #7f1d1d; border-color: #dc2626; background: #fee2e2; }}
        .csv-pill.blue {{ color: #1e3a8a; border-color: #2563eb; background: #dbeafe; }}

        /* ================= Team hero band ================= */
        .csv-team-hero {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 20px 26px;
            display: flex; align-items: center; gap: 20px;
            box-shadow: {SHADOW};
            margin-bottom: 16px;
            border-top: 5px solid var(--team-color, {PRIMARY});
        }}
        .csv-team-name {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 28px; font-weight: 800; color: {TEXT}; line-height: 1.1;
        }}
        .csv-team-meta {{ color: {TEXT_DIM}; font-size: 14.5px; margin-top: 3px; font-weight: 600; }}

        /* ================= Buttons ================= */
        .stButton > button {{
            border-radius: 10px; font-weight: 700; font-size: 14.5px;
            border: 1.5px solid {BORDER_STRONG};
            background: {BG_CARD}; color: {TEXT};
            padding: 0.5rem 1rem;
            transition: all 0.15s ease;
            box-shadow: {SHADOW_SM};
        }}
        .stButton > button:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; background: #eff4ff; }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
            border: none; color: #ffffff !important;
            box-shadow: 0 2px 10px rgba(29,78,216,0.35);
        }}
        .stButton > button[kind="primary"]:hover {{
            box-shadow: 0 4px 16px rgba(29,78,216,0.5); color: #ffffff !important;
        }}
        .stButton > button[kind="primary"] p {{ color: #ffffff !important; }}

        /* ================= Chat ================= */
        div[data-testid="stChatMessage"] {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 12px;
            box-shadow: {SHADOW_SM};
            padding: 12px 14px;
        }}
        div[data-testid="stChatMessage"] p, div[data-testid="stChatMessage"] li {{ color: {TEXT}; }}
        div[data-testid="stChatMessage"] a {{ color: {PRIMARY}; font-weight: 600; word-break: break-all; }}
        div[data-testid="stChatInput"] textarea {{ font-size: 15px !important; color: {TEXT} !important; }}
        div[data-testid="stChatInput"] {{ border-radius: 12px; }}

        /* Chat input: centered + width-limited, Claude/ChatGPT style */
        div[data-testid="stChatInput"] {{
            max-width: 860px;
            margin: 0 auto;
            border: 1.5px solid {BORDER_STRONG};
            border-radius: 14px;
            box-shadow: {SHADOW};
            background: {BG_CARD};
        }}
        div[data-testid="stChatInput"]:focus-within {{ border-color: {PRIMARY}; }}

        /* League pulse ticker -- continuous marquee of real numbers */
        .csv-ticker {{
            overflow: hidden;
            white-space: nowrap;
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 9px 0;
            margin-bottom: 16px;
            box-shadow: {SHADOW_SM};
        }}
        .csv-ticker-track {{
            display: inline-flex;
            align-items: center;
            gap: 34px;
            padding-left: 34px;
            animation: csv-ticker-scroll 45s linear infinite;
        }}
        .csv-ticker:hover .csv-ticker-track {{ animation-play-state: paused; }}
        .csv-ticker-item {{
            display: inline-flex; align-items: center; gap: 9px;
            color: {TEXT_DIM}; font-size: 13.5px; font-weight: 600;
        }}
        .csv-ticker-item b {{ color: {TEXT}; font-weight: 800; }}
        .csv-ticker-item img {{ box-shadow: none !important; border: none !important; padding: 0 !important; }}
        @keyframes csv-ticker-scroll {{
            from {{ transform: translateX(0); }}
            to {{ transform: translateX(-50%); }}
        }}

        div[data-testid="stDataFrame"] {{
            border-radius: 12px; overflow: hidden;
            border: 1px solid {BORDER}; box-shadow: {SHADOW_SM};
            background: {BG_CARD};
        }}
        .stAlert {{ border-radius: 12px; font-size: 14.5px; }}
        div[data-testid="stExpander"] {{
            background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 12px;
        }}
        div[data-testid="stExpander"] summary p {{ color: {TEXT}; font-weight: 600; }}
        hr {{ border-color: {BORDER}; margin: 1.4rem 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, sub: str = "", tone: str = "") -> str:
    return f"""
    <div class="csv-card" style="padding:16px 20px">
        <div class="csv-metric-label">{label}</div>
        <div class="csv-metric-value {tone}">{value}</div>
        <div class="csv-metric-sub">{sub}</div>
    </div>
    """


def pill(text: str, tone: str = "") -> str:
    return f'<span class="csv-pill {tone}">{text}</span>'


def team_hero(franchise_name: str, subtitle: str = "") -> str:
    color = FRANCHISE_COLORS.get(franchise_name, PRIMARY)
    return f"""
    <div class="csv-team-hero" style="--team-color:{color}">
        {team_logo(franchise_name, size=72, radius=14)}
        <div>
            <div class="csv-team-name">{franchise_name}</div>
            <div class="csv-team-meta">{subtitle}</div>
        </div>
    </div>
    """

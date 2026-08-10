"""CricSavant AI -- visual theme.

Presentation only: CSS injection, static lookup tables, and logo/photo
helpers. No data access, no business logic.

v4 -- full light-theme rebuild, per direct user decision ("I don't
like the black background", picked light theme from the options).
White/off-white surfaces in the ESPNcricinfo / official-IPL style,
where the color comes from the REAL team logos (user-supplied JPGs in
assets/team_logos/) and each franchise's real brand color -- not from
neon accents fighting a dark void. Real logos replace the v3 initials
crests everywhere.
"""

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

# ---- Palette (light) ----------------------------------------------
BG = "#f4f5f7"          # page
BG_PANEL = "#eceef2"    # sidebar
BG_CARD = "#ffffff"     # cards
BG_CARD_ELEV = "#ffffff"
BORDER = "rgba(15,23,42,0.10)"
BORDER_STRONG = "rgba(15,23,42,0.20)"

# Accents tuned for white backgrounds (darker than the old dark-theme
# neons so text in these colors stays readable).
GOLD = "#b45309"        # amber-700 -- primary accent
GOLD_SOFT = "#d97706"   # amber-600
BLUE = "#2563eb"
GREEN = "#059669"
RED = "#dc2626"
PURPLE = "#7c3aed"
TEAL = "#0d9488"

TEXT = "#0f172a"
TEXT_DIM = "#526078"
TEXT_FAINT = "#8a94a8"

SHADOW = "0 1px 3px rgba(15,23,42,0.06), 0 4px 14px rgba(15,23,42,0.06)"
SHADOW_SM = "0 1px 2px rgba(15,23,42,0.05), 0 2px 8px rgba(15,23,42,0.05)"

ROLE_COLOR = {
    "batter": GOLD_SOFT,
    "bowler": BLUE,
    "all-rounder": PURPLE,
    "wicketkeeper": TEAL,
}

FRANCHISE_COLORS = {
    "Chennai Super Kings": "#e8b800",
    "Mumbai Indians": "#1d5fc4",
    "Royal Challengers Bengaluru": "#c8102e",
    "Kolkata Knight Riders": "#5b2c8d",
    "Delhi Capitals": "#1d4ed8",
    "Punjab Kings": "#d11f2f",
    "Rajasthan Royals": "#e0399e",
    "Sunrisers Hyderabad": "#e65c00",
    "Gujarat Titans": "#1b2a5b",
    "Lucknow Super Giants": "#0699c7",
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
    """Base64 of the user-supplied team logo JPG, or None if missing.
    Cached -- these are read once per process, not once per rerun.
    """
    path = _LOGO_DIR / f"{short_code}.jpg"
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


def team_logo(franchise_name: str, size: int = 56, radius: int = 12) -> str:
    """<img> tag for the real team logo (user-supplied assets). Falls
    back to a colored initials tile only if the file is missing --
    never renders a broken-image icon.
    """
    short = FRANCHISE_SHORT.get(franchise_name, "")
    b64 = _logo_b64(short) if short else None
    if b64:
        return (
            f'<img src="data:image/jpeg;base64,{b64}" alt="{short}" '
            f'style="width:{size}px;height:{size}px;object-fit:contain;border-radius:{radius}px;'
            f'background:#fff;border:1px solid {BORDER};box-shadow:{SHADOW_SM};flex-shrink:0;"/>'
        )
    color = FRANCHISE_COLORS.get(franchise_name, GOLD)
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
    """Initials avatar for players (no real player photos in the app's
    data, and scraping them isn't on the table). Colored by role.
    """
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;flex-shrink:0;'
        f'background:linear-gradient(145deg,{color},{color}cc);display:flex;align-items:center;'
        f'justify-content:center;color:#fff;font-weight:800;font-size:{int(size*0.34)}px;'
        f'font-family:Space Grotesk,Inter,sans-serif;box-shadow:{SHADOW_SM};'
        f'text-shadow:0 1px 2px rgba(0,0,0,0.25);">{_initials(name)}</div>'
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
        .stApp {{
            background: {BG};
            color: {TEXT};
        }}
        section[data-testid="stSidebar"] {{
            background: {BG_PANEL};
            border-right: 1px solid {BORDER};
        }}
        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; }}

        h1, h2, h3, h4 {{
            font-family: 'Space Grotesk', 'Inter', sans-serif !important;
            letter-spacing: -0.015em;
            color: {TEXT} !important;
        }}
        h2 {{ font-size: 28px !important; font-weight: 800 !important; }}
        h3 {{ font-size: 21px !important; font-weight: 700 !important; }}
        h4 {{ font-size: 17px !important; font-weight: 700 !important; }}

        p, li, .stMarkdown {{ color: {TEXT}; }}
        div[data-testid="stWidgetLabel"] p {{
            font-size: 13px !important;
            font-weight: 700 !important;
            color: {TEXT_DIM} !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .stCaption, div[data-testid="stCaptionContainer"] {{
            font-size: 14px !important;
            color: {TEXT_DIM} !important;
            line-height: 1.55;
        }}
        div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
            background: {BG_CARD} !important;
            border-color: {BORDER_STRONG} !important;
            color: {TEXT} !important;
            font-size: 15px !important;
            border-radius: 10px !important;
        }}

        /* ---- Cards ---- */
        .csv-card {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 16px;
            box-shadow: {SHADOW};
        }}
        .csv-metric-label {{
            color: {TEXT_DIM};
            font-size: 12.5px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 700;
            margin-bottom: 6px;
        }}
        .csv-metric-value {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 34px;
            font-weight: 700;
            color: {TEXT};
            line-height: 1.1;
        }}
        .csv-metric-value.gold {{ color: {GOLD_SOFT}; }}
        .csv-metric-value.green {{ color: {GREEN}; }}
        .csv-metric-value.red {{ color: {RED}; }}
        .csv-metric-value.blue {{ color: {BLUE}; }}
        .csv-metric-sub {{ color: {TEXT_FAINT}; font-size: 13px; margin-top: 5px; font-weight: 500; }}

        /* ---- Pills ---- */
        .csv-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 5px 13px; border-radius: 999px;
            font-size: 13px; font-weight: 700;
            border: 1px solid {BORDER}; background: {BG}; color: {TEXT_DIM};
        }}
        .csv-pill.gold {{ color: {GOLD}; border-color: rgba(180,83,9,0.35); background: rgba(217,119,6,0.08); }}
        .csv-pill.green {{ color: {GREEN}; border-color: rgba(5,150,105,0.35); background: rgba(5,150,105,0.07); }}
        .csv-pill.red {{ color: {RED}; border-color: rgba(220,38,38,0.35); background: rgba(220,38,38,0.06); }}
        .csv-pill.blue {{ color: {BLUE}; border-color: rgba(37,99,235,0.35); background: rgba(37,99,235,0.06); }}

        /* ---- Team hero band (Strategy Center header) ---- */
        .csv-team-hero {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 18px;
            padding: 24px 28px;
            display: flex; align-items: center; gap: 22px;
            box-shadow: {SHADOW};
            margin-bottom: 18px;
            border-top: 4px solid var(--team-color, {GOLD_SOFT});
        }}
        .csv-team-name {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 30px; font-weight: 800; color: {TEXT}; line-height: 1.1;
        }}
        .csv-team-meta {{ color: {TEXT_DIM}; font-size: 14.5px; margin-top: 4px; font-weight: 500; }}

        /* ---- Buttons ---- */
        .stButton > button {{
            border-radius: 10px; font-weight: 700; font-size: 14.5px;
            border: 1px solid {BORDER_STRONG};
            background: {BG_CARD}; color: {TEXT};
            padding: 0.5rem 1rem;
            transition: all 0.15s ease;
            box-shadow: {SHADOW_SM};
        }}
        .stButton > button:hover {{ border-color: {GOLD_SOFT}; color: {GOLD}; }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {GOLD_SOFT} 0%, {GOLD} 100%);
            border: none; color: #fff;
            box-shadow: 0 2px 10px rgba(217,119,6,0.35);
        }}
        .stButton > button[kind="primary"]:hover {{ box-shadow: 0 4px 14px rgba(217,119,6,0.5); color: #fff; }}

        /* ---- Chat (native st.chat_message) ---- */
        div[data-testid="stChatMessage"] {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 14px;
            box-shadow: {SHADOW_SM};
            padding: 14px 16px;
        }}
        div[data-testid="stChatMessage"] a {{ color: {BLUE}; word-break: break-all; }}
        div[data-testid="stChatInput"] textarea {{ font-size: 15px !important; }}

        div[data-testid="stDataFrame"] {{
            border-radius: 12px; overflow: hidden;
            border: 1px solid {BORDER}; box-shadow: {SHADOW_SM};
            background: {BG_CARD};
        }}
        .stAlert {{ border-radius: 12px; font-size: 14.5px; }}
        div[data-testid="stExpander"] {{
            background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 12px;
        }}
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
    color = FRANCHISE_COLORS.get(franchise_name, GOLD_SOFT)
    return f"""
    <div class="csv-team-hero" style="--team-color:{color}">
        {team_logo(franchise_name, size=76, radius=14)}
        <div>
            <div class="csv-team-name">{franchise_name}</div>
            <div class="csv-team-meta">{subtitle}</div>
        </div>
    </div>
    """

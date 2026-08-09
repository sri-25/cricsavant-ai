"""CricSavant AI -- visual theme.

Everything here is presentation only: CSS injection + static lookup
tables (franchise colors/short codes, role icons). No data access, no
business logic -- keeps the "make it look elite" concern fully
separate from the "get real numbers" concern in the rest of lib/.
"""

import streamlit as st

# ---- Brand palette -----------------------------------------------
# Dark "auction war room" theme: near-black navy base, warm auction-
# gavel gold as the single accent color, a cool blue for informational
# states, green/red reserved strictly for success/blocked outcomes so
# they stay meaningful (not decorative) wherever they appear.
BG = "#0a0e1a"
BG_PANEL = "#11172a"
BG_CARD = "#161d34"
BORDER = "#232c47"
GOLD = "#e8b84b"
GOLD_SOFT = "#f5d78a"
BLUE = "#5b8def"
GREEN = "#3ecf8e"
RED = "#f16565"
TEXT = "#e9edf7"
TEXT_DIM = "#8b93ab"

# Real current IPL franchise colors -- used for roster chips, purse
# gauges, and the analytics "spend by franchise" chart so each team is
# instantly recognizable rather than reading off a generic palette.
FRANCHISE_COLORS = {
    "Chennai Super Kings": "#f9cd05",
    "Mumbai Indians": "#045093",
    "Royal Challengers Bengaluru": "#da1818",
    "Kolkata Knight Riders": "#3a225d",
    "Delhi Capitals": "#17479e",
    "Punjab Kings": "#dd1f2d",
    "Rajasthan Royals": "#e6469c",
    "Sunrisers Hyderabad": "#f26522",
    "Gujarat Titans": "#1c1c34",
    "Lucknow Super Giants": "#00a5e0",
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


def inject_css():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 16px;
        }}
        .stMarkdown, .stMarkdown p, .stCaption, div[data-testid="stCaptionContainer"] {{
            font-size: 15px !important;
        }}
        section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] p {{
            font-size: 14.5px !important;
        }}

        .stApp {{
            background:
                radial-gradient(circle at 15% 0%, rgba(232,184,75,0.06) 0%, transparent 45%),
                radial-gradient(circle at 85% 100%, rgba(91,141,239,0.06) 0%, transparent 45%),
                {BG};
            color: {TEXT};
        }}

        section[data-testid="stSidebar"] {{
            background: {BG_PANEL};
            border-right: 1px solid {BORDER};
            min-width: 440px !important;
        }}

        #MainMenu, footer, header[data-testid="stHeader"] {{
            background: transparent;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Space Grotesk', 'Inter', sans-serif !important;
            letter-spacing: -0.01em;
        }}

        /* ---- Brand header ---- */
        .csv-brand {{
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 4px 0 18px 0;
            border-bottom: 1px solid {BORDER};
            margin-bottom: 22px;
        }}
        .csv-brand-mark {{
            font-size: 30px;
            width: 48px; height: 48px;
            display: flex; align-items: center; justify-content: center;
            border-radius: 12px;
            background: linear-gradient(135deg, {GOLD} 0%, #b9852a 100%);
            box-shadow: 0 4px 18px rgba(232,184,75,0.35);
        }}
        .csv-brand-title {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 24px;
            color: {TEXT};
            line-height: 1.1;
        }}
        .csv-brand-sub {{
            color: {TEXT_DIM};
            font-size: 13px;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }}

        /* ---- Tabs, styled as an elite nav bar ---- */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px;
            background: {BG_PANEL};
            padding: 6px;
            border-radius: 14px;
            border: 1px solid {BORDER};
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 50px;
            border-radius: 10px;
            color: {TEXT_DIM};
            font-weight: 600;
            font-size: 16px;
            padding: 0 20px;
        }}
        .stTabs [data-baseweb="tab"] p {{
            font-size: 16px !important;
        }}
        .stTabs [aria-selected="true"] {{
            background: linear-gradient(135deg, rgba(232,184,75,0.18), rgba(232,184,75,0.05));
            color: {GOLD_SOFT} !important;
            box-shadow: inset 0 0 0 1px rgba(232,184,75,0.35);
        }}

        /* ---- Cards ---- */
        .csv-card {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 22px 24px;
            margin-bottom: 16px;
        }}
        .csv-card-tight {{ padding: 16px 20px; }}

        .csv-metric-label {{
            color: {TEXT_DIM};
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .csv-metric-value {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 34px;
            font-weight: 700;
            color: {TEXT};
            line-height: 1.15;
        }}
        .csv-metric-value.gold {{ color: {GOLD_SOFT}; }}
        .csv-metric-value.green {{ color: {GREEN}; }}
        .csv-metric-value.red {{ color: {RED}; }}
        .csv-metric-sub {{
            color: {TEXT_DIM};
            font-size: 13.5px;
            margin-top: 4px;
        }}

        /* ---- Pills / chips ---- */
        .csv-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 13px;
            border-radius: 999px;
            font-size: 13.5px;
            font-weight: 600;
            border: 1px solid {BORDER};
            background: rgba(255,255,255,0.03);
            color: {TEXT_DIM};
        }}
        .csv-pill.gold {{ color: {GOLD_SOFT}; border-color: rgba(232,184,75,0.4); background: rgba(232,184,75,0.08); }}
        .csv-pill.green {{ color: {GREEN}; border-color: rgba(62,207,142,0.4); background: rgba(62,207,142,0.08); }}
        .csv-pill.red {{ color: {RED}; border-color: rgba(241,101,101,0.4); background: rgba(241,101,101,0.08); }}
        .csv-pill.blue {{ color: {BLUE}; border-color: rgba(91,141,239,0.4); background: rgba(91,141,239,0.08); }}

        /* ---- Player hero card (Auction Console) ---- */
        .csv-player-hero {{
            background: linear-gradient(135deg, {BG_CARD} 0%, {BG_PANEL} 100%);
            border: 1px solid {BORDER};
            border-radius: 20px;
            padding: 26px 28px;
            position: relative;
            overflow: hidden;
        }}
        .csv-player-hero::before {{
            content: "";
            position: absolute; top: -40%; right: -10%;
            width: 260px; height: 260px;
            background: radial-gradient(circle, rgba(232,184,75,0.14) 0%, transparent 70%);
        }}
        .csv-player-name {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 38px;
            font-weight: 700;
            color: {TEXT};
        }}
        .csv-player-meta {{
            color: {TEXT_DIM};
            font-size: 15.5px;
            margin-top: 4px;
        }}

        /* ---- Chat drawer ---- */
        .csv-chat-msg {{
            padding: 12px 16px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-size: 14.5px;
            line-height: 1.55;
        }}
        .csv-chat-user {{
            background: rgba(91,141,239,0.12);
            border: 1px solid rgba(91,141,239,0.3);
            color: {TEXT};
        }}
        .csv-chat-assistant {{
            background: rgba(232,184,75,0.08);
            border: 1px solid rgba(232,184,75,0.25);
            color: {TEXT};
        }}
        .csv-chat-tool {{
            background: transparent;
            border: 1px dashed {BORDER};
            color: {TEXT_DIM};
            font-family: 'SF Mono', 'Consolas', monospace;
            font-size: 11px;
        }}

        /* ---- Feed rows (live bid ticker) ---- */
        .csv-feed-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 11px 4px;
            border-bottom: 1px solid {BORDER};
            font-size: 14.5px;
        }}
        .csv-feed-row:last-child {{ border-bottom: none; }}

        /* ---- Streamlit widget overrides ---- */
        .stButton > button {{
            border-radius: 10px;
            font-weight: 600;
            border: 1px solid {BORDER};
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {GOLD} 0%, #b9852a 100%);
            border: none;
            color: #1a1300;
        }}
        div[data-testid="stMetricValue"] {{
            font-family: 'Space Grotesk', sans-serif;
        }}
        hr {{ border-color: {BORDER}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, sub: str = "", tone: str = "") -> str:
    """Returns HTML for one metric card. tone: '', 'gold', 'green', 'red'."""
    return f"""
    <div class="csv-card csv-card-tight">
        <div class="csv-metric-label">{label}</div>
        <div class="csv-metric-value {tone}">{value}</div>
        <div class="csv-metric-sub">{sub}</div>
    </div>
    """


def pill(text: str, tone: str = "") -> str:
    return f'<span class="csv-pill {tone}">{text}</span>'


def brand_header(title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="csv-brand">
            <div class="csv-brand-mark">🏆</div>
            <div>
                <div class="csv-brand-title">{title}</div>
                <div class="csv-brand-sub">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

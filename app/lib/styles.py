"""CricSavant AI -- visual theme.

Presentation only: CSS injection + static lookup tables (franchise
colors/short codes, role icons) + small HTML-generating helpers
(avatar/crest circles). No data access, no business logic.

v3 -- direct response to "I don't like to see black... add pictures,
make it pretty, currently it looks dry and dead." Two real, separate
problems addressed:
  1. The base surface read as literal near-black (#08090d, ~3%
     lightness) with color only in two faint corner gradients --
     everywhere else was void. Swapped to a deep NAVY, not black
     (there's a real hue in it), and widened/brightened the color
     washes so life is visible across the page, not just the corners.
  2. There were no player/team "photos" anywhere -- the auction hero
     card in particular had a large dead empty rectangle where a photo
     would go. Real player photos and official team logos are both off
     the table (no image-fetch pipeline, and real IPL crests are
     trademarked) -- so this adds an original alternative that's
     honest about being a placeholder: gradient initials avatars for
     players (colored by role) and initials crests for franchises
     (colored by real team color), the same pattern GitHub/Slack/Linear
     use instead of a broken-image icon when there's no real photo.
"""

import streamlit as st

# ---- Brand palette -------------------------------------------------
# Layered dark-NAVY surfaces (page < panel < card < elevated), the way
# Linear/Vercel/Stripe-style dashboards do it -- each level a little
# lighter than the one below, so the UI reads as having real depth
# instead of one flat background color with boxes drawn on top. Every
# stop here carries a genuine blue hue (not a desaturated gray-black),
# which is the actual fix for "I don't like to see black."
BG = "#0a0e1a"
BG_PANEL = "#0f1526"
BG_CARD = "#161d33"
BG_CARD_ELEV = "#1e2743"
BORDER = "rgba(255,255,255,0.09)"
BORDER_STRONG = "rgba(255,255,255,0.18)"

GOLD = "#f0b429"
GOLD_SOFT = "#ffd166"
BLUE = "#5b8cff"
GREEN = "#2fd67f"
RED = "#ff5c7a"
PURPLE = "#b18cff"
TEAL = "#2dd4bf"

TEXT = "#f6f7fb"
TEXT_DIM = "#9aa3ba"
TEXT_FAINT = "#6b7488"

SHADOW = "0 4px 16px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.05) inset"
SHADOW_SM = "0 2px 8px rgba(0,0,0,0.35)"

# Role -> accent color, used for avatar gradients and small role
# indicators -- spreads color across four hues instead of everything
# defaulting to gold, which was a real contributor to "flat."
ROLE_COLOR = {
    "batter": GOLD,
    "bowler": BLUE,
    "all-rounder": PURPLE,
    "wicketkeeper": TEAL,
}

# Real current IPL franchise colors -- used for roster chips, purse
# gauges, and the analytics "spend by franchise" chart so each team is
# instantly recognizable rather than reading off a generic palette.
FRANCHISE_COLORS = {
    "Chennai Super Kings": "#f9cd05",
    "Mumbai Indians": "#2e7bde",
    "Royal Challengers Bengaluru": "#ec2b3c",
    "Kolkata Knight Riders": "#8b5cf6",
    "Delhi Capitals": "#4f8fff",
    "Punjab Kings": "#ff4d5e",
    "Rajasthan Royals": "#f472b6",
    "Sunrisers Hyderabad": "#ff8a3d",
    "Gujarat Titans": "#5b8cff",
    "Lucknow Super Giants": "#22c3ee",
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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 17px;
        }}

        .stApp {{
            background:
                radial-gradient(ellipse 1100px 700px at 15% -5%, rgba(240,180,41,0.14) 0%, transparent 62%),
                radial-gradient(ellipse 1200px 800px at 100% 5%, rgba(91,140,255,0.13) 0%, transparent 60%),
                radial-gradient(ellipse 900px 700px at 50% 100%, rgba(177,140,255,0.08) 0%, transparent 65%),
                linear-gradient(180deg, #0d1220 0%, {BG} 40%, #0c1018 100%);
            color: {TEXT};
        }}

        section[data-testid="stSidebar"] {{
            background: {BG_PANEL};
            border-right: 1px solid {BORDER};
            min-width: 460px !important;
        }}
        section[data-testid="stSidebar"] > div {{ padding-top: 1.2rem; }}

        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; }}

        h1, h2, h3, h4 {{
            font-family: 'Space Grotesk', 'Inter', sans-serif !important;
            letter-spacing: -0.015em;
            font-weight: 700 !important;
        }}
        h3 {{ font-size: 22px !important; }}
        h4 {{ font-size: 18px !important; color: {TEXT}; }}

        /* Widget labels (selectbox/text_input/number_input) read as an
        afterthought at default size -- bump + weight them like real
        form labels in a product UI, not fine print. */
        div[data-testid="stWidgetLabel"] p {{
            font-size: 14.5px !important;
            font-weight: 600 !important;
            color: {TEXT_DIM} !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .stCaption, div[data-testid="stCaptionContainer"] {{
            font-size: 15px !important;
            color: {TEXT_DIM} !important;
            line-height: 1.55;
        }}
        div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
            background: {BG_CARD_ELEV} !important;
            border-color: {BORDER} !important;
            font-size: 15.5px !important;
            border-radius: 10px !important;
        }}

        /* ---- Brand header ---- */
        .csv-brand {{
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 6px 0 22px 0;
            border-bottom: 1px solid {BORDER};
            margin-bottom: 26px;
        }}
        .csv-brand-mark {{
            font-size: 32px;
            width: 56px; height: 56px;
            display: flex; align-items: center; justify-content: center;
            border-radius: 14px;
            background: linear-gradient(145deg, {GOLD} 0%, #b9852a 100%);
            box-shadow: 0 6px 22px rgba(240,180,41,0.4), 0 0 0 1px rgba(255,255,255,0.12) inset;
        }}
        .csv-brand-title {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 800;
            font-size: 26px;
            color: {TEXT};
            line-height: 1.1;
        }}
        .csv-brand-sub {{
            color: {TEXT_DIM};
            font-size: 13.5px;
            letter-spacing: 0.07em;
            text-transform: uppercase;
            font-weight: 600;
            margin-top: 2px;
        }}

        /* ---- Tabs, styled as an elite nav bar ---- */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            background: {BG_PANEL};
            padding: 8px;
            border-radius: 16px;
            border: 1px solid {BORDER};
            box-shadow: {SHADOW_SM};
            margin-bottom: 8px;
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 52px;
            border-radius: 11px;
            color: {TEXT_DIM};
            font-weight: 700;
            font-size: 16.5px;
            padding: 0 22px;
        }}
        .stTabs [data-baseweb="tab"] p {{ font-size: 16.5px !important; }}
        .stTabs [aria-selected="true"] {{
            background: linear-gradient(135deg, rgba(240,180,41,0.22), rgba(240,180,41,0.06));
            color: {GOLD_SOFT} !important;
            box-shadow: inset 0 0 0 1px rgba(240,180,41,0.4), {SHADOW_SM};
        }}

        /* ---- Cards ---- */
        .csv-card {{
            background: linear-gradient(165deg, {BG_CARD_ELEV} 0%, {BG_CARD} 100%);
            border: 1px solid {BORDER};
            border-radius: 18px;
            padding: 24px 26px;
            margin-bottom: 18px;
            box-shadow: {SHADOW};
        }}
        .csv-card-tight {{ padding: 18px 22px; }}

        .csv-metric-label {{
            color: {TEXT_DIM};
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .csv-metric-value {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 40px;
            font-weight: 700;
            color: {TEXT};
            line-height: 1.1;
        }}
        .csv-metric-value.gold {{ color: {GOLD_SOFT}; }}
        .csv-metric-value.green {{ color: {GREEN}; }}
        .csv-metric-value.red {{ color: {RED}; }}
        .csv-metric-value.blue {{ color: {BLUE}; }}
        .csv-metric-sub {{
            color: {TEXT_FAINT};
            font-size: 13.5px;
            margin-top: 6px;
            font-weight: 500;
        }}

        /* ---- Pills / chips ---- */
        .csv-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 15px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 700;
            border: 1px solid {BORDER};
            background: rgba(255,255,255,0.04);
            color: {TEXT_DIM};
        }}
        .csv-pill.gold {{ color: {GOLD_SOFT}; border-color: rgba(240,180,41,0.45); background: rgba(240,180,41,0.1); }}
        .csv-pill.green {{ color: {GREEN}; border-color: rgba(47,214,127,0.45); background: rgba(47,214,127,0.1); }}
        .csv-pill.red {{ color: {RED}; border-color: rgba(255,92,122,0.45); background: rgba(255,92,122,0.1); }}
        .csv-pill.blue {{ color: {BLUE}; border-color: rgba(91,140,255,0.45); background: rgba(91,140,255,0.1); }}

        /* ---- Player hero card (Auction Console) ---- */
        .csv-player-hero {{
            background:
                radial-gradient(circle at 100% 0%, rgba(240,180,41,0.16) 0%, transparent 60%),
                linear-gradient(165deg, {BG_CARD_ELEV} 0%, {BG_CARD} 100%);
            border: 1px solid {BORDER};
            border-radius: 22px;
            padding: 32px 34px;
            position: relative;
            overflow: hidden;
            box-shadow: {SHADOW};
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }}
        .csv-player-name {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 44px;
            font-weight: 800;
            color: {TEXT};
            line-height: 1.05;
        }}
        .csv-player-meta {{
            color: {TEXT_DIM};
            font-size: 16px;
            margin-top: 6px;
            font-weight: 500;
        }}

        /* ---- Avatars / crests -- the "photo" substitute -----------
        No real player photos or official team logos (no image pipeline,
        and real crests are trademarked) -- gradient initials circles
        instead, colored by role or real franchise color. Same pattern
        Slack/Linear/GitHub use in place of a broken-image icon. */
        .csv-avatar {{
            flex-shrink: 0;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 800;
            color: #10121c;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4), 0 0 0 3px rgba(255,255,255,0.08) inset;
            text-shadow: 0 1px 0 rgba(255,255,255,0.25);
            letter-spacing: -0.02em;
        }}
        .csv-crest {{
            flex-shrink: 0;
            border-radius: 16px;
            display: flex; align-items: center; justify-content: center;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 800;
            color: #10121c;
            box-shadow: 0 6px 18px rgba(0,0,0,0.4), 0 0 0 2px rgba(255,255,255,0.1) inset;
        }}

        /* ---- Chat drawer ---- */
        .csv-chat-msg {{
            padding: 14px 17px;
            border-radius: 14px;
            margin-bottom: 12px;
            font-size: 15px;
            line-height: 1.6;
            box-shadow: {SHADOW_SM};
        }}
        .csv-chat-msg b {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.8; }}
        .csv-chat-msg a {{ color: {GOLD_SOFT}; text-decoration: none; border-bottom: 1px solid rgba(255,209,102,0.4); word-break: break-all; }}
        .csv-chat-msg a:hover {{ border-bottom-color: {GOLD_SOFT}; }}
        .csv-chat-user {{
            background: rgba(91,140,255,0.12);
            border: 1px solid rgba(91,140,255,0.28);
            color: {TEXT};
        }}
        .csv-chat-assistant {{
            background: rgba(240,180,41,0.08);
            border: 1px solid rgba(240,180,41,0.24);
            color: {TEXT};
        }}

        /* ---- Feed rows (live bid ticker) ---- */
        .csv-feed-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 13px 6px;
            border-bottom: 1px solid {BORDER};
            font-size: 15px;
        }}
        .csv-feed-row:last-child {{ border-bottom: none; }}

        /* ---- Streamlit widget overrides ---- */
        .stButton > button {{
            border-radius: 11px;
            font-weight: 700;
            font-size: 15px;
            border: 1px solid {BORDER};
            background: {BG_CARD_ELEV};
            color: {TEXT};
            padding: 0.55rem 1rem;
            transition: all 0.15s ease;
        }}
        .stButton > button:hover {{
            border-color: {BORDER_STRONG};
            background: #1f2333;
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {GOLD} 0%, #c8901f 100%);
            border: none;
            color: #1a1300;
            box-shadow: 0 4px 16px rgba(240,180,41,0.35);
        }}
        .stButton > button[kind="primary"]:hover {{
            box-shadow: 0 6px 20px rgba(240,180,41,0.5);
        }}
        div[data-testid="stMetricValue"] {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 32px !important;
        }}
        hr {{ border-color: {BORDER}; margin: 1.6rem 0; }}

        /* Dataframe container -- can't restyle individual cells (canvas
        rendered), but can give the container itself real presence. */
        div[data-testid="stDataFrame"] {{
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid {BORDER};
            box-shadow: {SHADOW_SM};
        }}

        .stAlert {{ border-radius: 14px; font-size: 15px; }}

        div[data-testid="stExpander"] {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 14px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, sub: str = "", tone: str = "") -> str:
    """Returns HTML for one metric card. tone: '', 'gold', 'green', 'red', 'blue'."""
    return f"""
    <div class="csv-card csv-card-tight">
        <div class="csv-metric-label">{label}</div>
        <div class="csv-metric-value {tone}">{value}</div>
        <div class="csv-metric-sub">{sub}</div>
    </div>
    """


def pill(text: str, tone: str = "") -> str:
    return f'<span class="csv-pill {tone}">{text}</span>'


def _initials(name: str, n: int = 2) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:n].upper()
    return (parts[0][0] + parts[-1][0]).upper()[:n]


def avatar_circle(name: str, color: str = GOLD, size: int = 84) -> str:
    """Gradient initials circle standing in for a player photo we don't
    have -- colored by role (see ROLE_COLOR) so a franchise's roster
    reads as visibly mixed rather than one repeated gold blob.
    """
    font_size = int(size * 0.36)
    return (
        f'<div class="csv-avatar" style="width:{size}px;height:{size}px;font-size:{font_size}px;'
        f'background:linear-gradient(150deg, {color} 0%, {BG_CARD_ELEV} 145%);">{_initials(name)}</div>'
    )


def franchise_crest(name: str, short: str = "", color: str = GOLD, size: int = 56) -> str:
    """Gradient initials crest standing in for a franchise logo --
    official IPL crests are trademarked, so this uses the team's real
    color with its short code instead of a fabricated or copied logo.
    """
    font_size = int(size * 0.32)
    label = short or _initials(name, 3)
    return (
        f'<div class="csv-crest" style="width:{size}px;height:{size}px;font-size:{font_size}px;'
        f'background:linear-gradient(150deg, {color} 0%, {BG_CARD_ELEV} 150%);">{label}</div>'
    )


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

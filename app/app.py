"""CricSavant AI -- franchise strategy platform.

v2 architecture, after the product pivot (user decision): the practice
Auction Console is gone; the app is now built around giving each
franchise CONTROL over its strategy. Multi-page (st.navigation), not
four tabs crammed into one screen:

  🏟️ Strategy Center  -- the heart: one-click deep AI runs (retention
                          plan, auction plan, playing-XI simulation)
                          for the selected franchise, saveable to a
                          permanent strategy notebook (Lakebase).
  🔍 Players           -- search any of ~2,400 real players, form charts.
  📊 League Analytics  -- cross-franchise business view (purse, squad
                          balance), plus the CDF-sync proof strip.
  💬 AI Analyst        -- free-form chat on NATIVE st.chat components
                          (the old custom-HTML sidebar chat was buggy
                          and uncoordinated -- this replaces it).

The agent is Claude Sonnet on Databricks FMAPI (CHAT_MODEL_ENDPOINT
resource), with 7 tools incl. save_strategy_note as the write action.
"""

import re

import pandas as pd
import streamlit as st

from lib import agent, charts, lakebase, lakehouse
from lib.styles import (
    FRANCHISE_COLORS, FRANCHISE_SHORT, ROLE_COLOR, ROLE_ICON, avatar_circle,
    inject_css, metric_card, pill, team_hero, team_logo,
)
from lib.utils import safe_num

st.set_page_config(page_title="CricSavant AI", page_icon="🏏", layout="wide")
inject_css()

# ---------------------------------------------------------------- #
# Session state
# ---------------------------------------------------------------- #
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = None
if "chat_display" not in st.session_state:
    st.session_state.chat_display = []
if "active_franchise" not in st.session_state:
    st.session_state.active_franchise = None
if "strategy_results" not in st.session_state:
    st.session_state.strategy_results = {}  # {(franchise, kind): (answer, trace)}


# ---------------------------------------------------------------- #
# Shared helpers
# ---------------------------------------------------------------- #
_URL_RE = re.compile(r'(?<!\()(?<!href=")(https?://[^\s<>")\]]+)')


def linkify(text: str) -> str:
    if not text:
        return text
    return _URL_RE.sub(r"[\1](\1)", text)


def fmt_cr(v) -> str:
    try:
        return f"₹{float(v):,.2f} cr"
    except (TypeError, ValueError):
        return "-"


@st.cache_data(ttl=30, show_spinner=False)
def cached_franchises() -> pd.DataFrame:
    return lakebase.list_franchises()


@st.cache_data(ttl=60, show_spinner=False)
def cached_player_pool() -> pd.DataFrame:
    return lakebase.list_player_pool()


@st.cache_data(ttl=60, show_spinner=False)
def cached_league_summary() -> pd.DataFrame:
    return lakebase.league_squad_summary()


def run_agent_turn(user_text: str, record_in_chat: bool = True):
    """One agent turn. Prefixes the active franchise so 'my squad'
    always means the selected team; returns (answer, trace).
    """
    active = st.session_state.active_franchise
    context_note = (
        f'[App context: the user manages "{active}". If their request doesn\'t name a '
        f"franchise, it means this one.]\n" if active else ""
    )
    try:
        answer, updated_messages, trace = agent.run_agent(
            context_note + user_text, st.session_state.agent_messages
        )
    except Exception as e:
        answer, updated_messages, trace = f"Agent call failed: {str(e)[:400]}", st.session_state.agent_messages, []
    st.session_state.agent_messages = updated_messages
    if record_in_chat:
        st.session_state.chat_display.append({"role": "user", "content": user_text})
        st.session_state.chat_display.append({"role": "assistant", "content": answer, "trace": trace})
    return answer, trace


def render_trace(trace: list):
    if trace:
        with st.expander(f"🔧 {len(trace)} tool call(s) -- what the AI actually looked up", expanded=False):
            for t in trace:
                st.markdown(f"**`{t['tool']}`**  `{t['args']}`")
                st.json(t["result"], expanded=False)


def franchise_picker():
    """Sidebar franchise selector with the real team logo."""
    franchises_df = cached_franchises()
    if franchises_df.empty:
        st.sidebar.warning("No franchises found.")
        return None
    names = franchises_df["name"].tolist()
    default_idx = names.index(st.session_state.active_franchise) if st.session_state.active_franchise in names else 0
    with st.sidebar:
        picked = st.selectbox("Your franchise", names, index=default_idx)
        # Team switch resets the agent's memory -- stale tool results
        # from another franchise otherwise bleed into answers.
        if st.session_state.active_franchise is not None and picked != st.session_state.active_franchise:
            st.session_state.agent_messages = None
        st.session_state.active_franchise = picked
        st.markdown(
            f'<div style="display:flex;justify-content:center;margin:10px 0 6px">{team_logo(picked, size=120, radius=18)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="text-align:center;color:{FRANCHISE_COLORS.get(picked, "#b45309")};'
            f'font-weight:800;font-size:15px;margin-bottom:14px">{picked}</div>',
            unsafe_allow_html=True,
        )
    return picked


# ================================================================ #
# PAGE: Strategy Center
# ================================================================ #
def page_strategy():
    chosen = st.session_state.active_franchise
    if not chosen:
        st.info("Pick your franchise in the sidebar to begin.")
        return

    status = lakebase.get_franchise_status(chosen, log=False)
    if not status["found"]:
        st.error("Franchise not found.")
        return

    f = status["franchise"]
    total = float(f["purse_total_cr"])
    remaining = float(f["purse_remaining_cr"])
    roster = pd.DataFrame(status["roster"])

    st.markdown(team_hero(chosen, f.get("owner_label", "")), unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(metric_card("Purse remaining", fmt_cr(remaining), f"of {fmt_cr(total)}", "green"), unsafe_allow_html=True)
    over_cap = status["squad_size"] > f["max_squad_size"]
    m2.markdown(metric_card("Squad size", f"{status['squad_size']} / {f['max_squad_size']}",
                            "over cap -- releases needed" if over_cap else "within cap",
                            "red" if over_cap else ""), unsafe_allow_html=True)
    over_os = status["overseas_count"] > f["max_overseas"]
    m3.markdown(metric_card("Overseas", f"{status['overseas_count']} / {f['max_overseas']}",
                            "over cap" if over_os else "slots used",
                            "red" if over_os else "blue"), unsafe_allow_html=True)
    role_counts = roster["role"].value_counts().to_dict() if not roster.empty else {}
    m4.markdown(metric_card("Balance", " · ".join(f"{role_counts.get(r, 0)}{r[0].upper()}" for r in
                            ["batter", "bowler", "all-rounder", "wicketkeeper"]),
                            "B=bat, B=bowl, A=AR, W=WK"), unsafe_allow_html=True)

    st.markdown("### 🎯 Strategy plays")
    st.caption(
        "Each play runs the AI through your real squad, real form data, real venue splits, and the "
        "real auction pool -- then you can save the plan to your strategy notebook."
    )

    plays = {
        "retention": (
            "📋 Retention & release plan",
            f"Build a retention and release plan for {chosen} ahead of the IPL 2027 auction. "
            "Group the squad into retain / release / borderline with the real numbers beside each name, "
            "state the purse freed by the releases, and name the gaps those releases open.",
        ),
        "auction": (
            "🛒 Auction plan (whom to sign)",
            f"Build {chosen}'s auction plan: first identify the squad's weakest areas from real form, "
            "then find the best available players in the auction pool for those gaps, and recommend "
            "specific signings with base price vs. our remaining purse math.",
        ),
        "xi": (
            "🏏 Best XI + Impact Player",
            f"Simulate {chosen}'s strongest playing XI for a home game: batting order, bowling options, "
            "max 4 overseas on the field, and name the Impact Player substitution. Justify each slot "
            "with the player's actual numbers and flag thin-data picks honestly.",
        ),
    }

    bc1, bc2, bc3 = st.columns(3)
    for col, (kind, (label, prompt)) in zip((bc1, bc2, bc3), plays.items()):
        if col.button(label, key=f"play_{kind}", use_container_width=True, type="primary"):
            with st.spinner("CricSavant is working through the real data -- deep runs take ~30-60s..."):
                answer, trace = run_agent_turn(prompt, record_in_chat=False)
            st.session_state.strategy_results[(chosen, kind)] = (answer, trace)

    note_type_for_kind = {"retention": "retention_plan", "auction": "auction_targets", "xi": "playing_xi"}
    for kind, (label, _) in plays.items():
        result = st.session_state.strategy_results.get((chosen, kind))
        if result:
            answer, trace = result
            st.markdown(f"#### {label}")
            with st.chat_message("assistant", avatar="🏆"):
                st.markdown(linkify(answer))
            render_trace(trace)
            sc1, sc2 = st.columns([1, 4])
            if sc1.button("💾 Save to notebook", key=f"save_{kind}"):
                res = lakebase.save_strategy_note(chosen, note_type_for_kind[kind], answer, created_by="user")
                if res.get("success"):
                    st.toast(f"Saved to {chosen}'s strategy notebook.", icon="✅")
                else:
                    st.error(res.get("reason", "Save failed."))

    # ---- Saved notebook ----
    st.markdown("### 📓 Strategy notebook")
    try:
        notes = lakebase.list_strategy_notes(chosen, limit=10)
    except Exception:
        notes = pd.DataFrame()
    if notes.empty:
        st.caption("No saved plans yet -- run a strategy play above and save it.")
    else:
        for _, n in notes.iterrows():
            ts = pd.to_datetime(n["created_at"]).strftime("%b %d, %H:%M")
            with st.expander(f"{n['note_type'].replace('_', ' ').title()} · {ts} · by {n['created_by']}"):
                st.markdown(n["content"])


# ================================================================ #
# PAGE: Players
# ================================================================ #
def page_players():
    st.markdown("## 🔍 Players")
    batter_df = lakehouse.get_batter_profiles()
    bowler_df = lakehouse.get_bowler_profiles()
    pool_df = cached_player_pool()

    pool_names = set(pool_df["player_name"].str.lower())
    all_names = sorted(set(batter_df["player_name"]) | set(bowler_df["player_name"]) | set(pool_df["player_name"]))

    fc1, fc2 = st.columns([3, 1])
    search = fc1.text_input("Search player", placeholder="e.g. Bumrah, Conway, Rashid...")
    scope = fc2.selectbox("Scope", ["All players", "In auction pool only"])

    names = all_names
    if search:
        s = search.lower()
        names = [n for n in names if s in n.lower()]
    if scope == "In auction pool only":
        names = [n for n in names if n.lower() in pool_names]

    st.caption(f"{len(names):,} of {len(all_names):,} players")
    if not names:
        st.info("No players match. Try a shorter search -- some players are stored by initials (e.g. 'JJ Bumrah').")
        return

    selected = st.selectbox("Player", names)
    if not selected:
        return

    bat_row = lakehouse.match_gold_row(selected, batter_df)
    bowl_row = lakehouse.match_gold_row(selected, bowler_df)
    bat_row = bat_row.to_dict() if bat_row is not None else None
    bowl_row = bowl_row.to_dict() if bowl_row is not None else None

    role = "all-rounder" if (bat_row and bowl_row) else ("bowler" if bowl_row else "batter")
    hc1, hc2 = st.columns([10, 1])
    hc1.markdown(f"### {ROLE_ICON.get(role, '🏏')} {selected}")
    hc2.markdown(avatar_circle(selected, ROLE_COLOR.get(role, "#d97706"), size=56), unsafe_allow_html=True)
    if selected.lower() in pool_names:
        prow = pool_df[pool_df["player_name"].str.lower() == selected.lower()].iloc[0]
        st.markdown(
            pill(f"In current auction pool · base {fmt_cr(float(prow['base_price_lakh']) / 100)}", "gold")
            + "&nbsp;" + pill(str(prow["country"]), ""),
            unsafe_allow_html=True,
        )

    if not bat_row and not bowl_row:
        st.info("No qualifying recent-form data in the KPI tables (thin sample across 2008-2025 competitions).")
        return

    if bat_row:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Recent SR", f"{safe_num(bat_row.get('recent_strike_rate')):.1f}", tone="gold"), unsafe_allow_html=True)
        c2.markdown(metric_card("Recent avg", f"{safe_num(bat_row.get('recent_average')):.1f}"), unsafe_allow_html=True)
        c3.markdown(metric_card("Career runs", f"{int(safe_num(bat_row.get('career_runs'))):,}"), unsafe_allow_html=True)
        c4.markdown(metric_card("Boundary %", f"{safe_num(bat_row.get('recent_boundary_pct')):.1f}%"), unsafe_allow_html=True)
        ch1, ch2 = st.columns(2)
        with ch1:
            st.plotly_chart(charts.batting_phase_radar(bat_row), use_container_width=True, config={"displayModeBar": False})
        with ch2:
            st.plotly_chart(
                charts.recent_vs_career_bar(bat_row, "recent_strike_rate", "career_strike_rate", "Strike rate"),
                use_container_width=True, config={"displayModeBar": False},
            )

    if bowl_row:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Recent economy", f"{safe_num(bowl_row.get('recent_economy')):.2f}", tone="gold"), unsafe_allow_html=True)
        c2.markdown(metric_card("Recent wickets", f"{int(safe_num(bowl_row.get('recent_wickets')))}"), unsafe_allow_html=True)
        c3.markdown(metric_card("Career wickets", f"{int(safe_num(bowl_row.get('career_wickets')))}"), unsafe_allow_html=True)
        btype = bowl_row.get("bowler_type")
        c4.markdown(metric_card("Role read", btype.title() if isinstance(btype, str) and btype else "n/a"), unsafe_allow_html=True)
        ch1, ch2 = st.columns(2)
        with ch1:
            st.plotly_chart(charts.bowling_phase_bars(bowl_row), use_container_width=True, config={"displayModeBar": False})
        with ch2:
            st.plotly_chart(
                charts.bowler_role_scatter(bowler_df, highlight_name=bowl_row.get("player_name")),
                use_container_width=True, config={"displayModeBar": False},
            )

    if st.button("🤖 Ask CricSavant about this player", type="primary"):
        with st.spinner("Checking real form and news..."):
            answer, trace = run_agent_turn(
                f"Assess {selected} as a potential auction pick for my franchise -- recent form, role fit, any news.",
                record_in_chat=False,
            )
        with st.chat_message("assistant", avatar="🏆"):
            st.markdown(linkify(answer))
        render_trace(trace)


# ================================================================ #
# PAGE: League Analytics
# ================================================================ #
def page_analytics():
    st.markdown("## 📊 League Analytics")
    st.caption("Where every franchise stands before the next auction -- purse power, squad balance, and cap pressure.")

    league = cached_league_summary()
    if league.empty:
        st.info("No franchise data yet.")
        return

    total_purse_left = float(league["purse_remaining_cr"].astype(float).sum())
    most_cash = league.loc[league["purse_remaining_cr"].astype(float).idxmax()]
    over_cap = league[league["squad_size"].astype(int) > league["max_squad_size"].astype(int)]

    m1, m2, m3 = st.columns(3)
    m1.markdown(metric_card("League purse in play", f"₹{total_purse_left:,.1f} cr", "combined remaining, all 10 teams", "gold"), unsafe_allow_html=True)
    m2.markdown(metric_card("Most purse power", FRANCHISE_SHORT.get(most_cash["name"], most_cash["name"]),
                            f"{fmt_cr(most_cash['purse_remaining_cr'])} remaining", "green"), unsafe_allow_html=True)
    m3.markdown(metric_card("Teams over squad cap", f"{len(over_cap)}",
                            "must release before auction" if len(over_cap) else "all within cap",
                            "red" if len(over_cap) else "green"), unsafe_allow_html=True)

    st.plotly_chart(charts.spend_by_franchise_bar(cached_franchises()), use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### Squad balance by franchise")
    disp = league.copy()
    disp["Purse left (cr)"] = disp["purse_remaining_cr"].astype(float).round(2)
    disp["Squad"] = disp["squad_size"].astype(str) + " / " + disp["max_squad_size"].astype(str)
    disp["Overseas"] = disp["overseas_count"].astype(str) + " / " + disp["max_overseas"].astype(str)
    st.dataframe(
        disp[["name", "Purse left (cr)", "Squad", "Overseas", "batters", "bowlers", "all_rounders", "wicketkeepers", "home_venue"]]
        .rename(columns={"name": "Franchise", "batters": "Bat", "bowlers": "Bowl",
                          "all_rounders": "AR", "wicketkeepers": "WK", "home_venue": "Home venue"}),
        use_container_width=True, hide_index=True,
    )

    # ---- CDF sync proof (capstone requirement), deliberately small ----
    st.markdown("#### ⚙️ Data pipeline health")
    try:
        live_log = lakebase.all_change_log()
        synced_log = lakehouse.get_change_log_history()
        lag = max(len(live_log) - len(synced_log), 0)
        pc1, pc2 = st.columns([1, 3])
        pc1.markdown(metric_card("Synced to Delta", f"{len(synced_log)} / {len(live_log)}",
                                 "events current" if lag == 0 else f"{lag} pending sync",
                                 "green" if lag == 0 else "gold"), unsafe_allow_html=True)
        pc2.caption(
            "Every AI tool call and saved plan is written to Lakebase `change_log`, then synced to the "
            "`cricsavant.ops.lb_change_log_history` Delta table (001_sync_change_log_to_delta.py) -- the "
            "Lakebase→Delta CDF mechanism, kept visible here as proof without taking over the page."
        )
        with st.expander("Recent activity log"):
            st.dataframe(live_log.sort_values("event_id", ascending=False).head(30), use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"Pipeline strip unavailable: {str(e)[:150]}")


# ================================================================ #
# PAGE: AI Analyst (native chat)
# ================================================================ #
def page_chat():
    chosen = st.session_state.active_franchise
    st.markdown("## 💬 AI Analyst")
    st.caption(
        f"Talking strategy for **{chosen}**. Grounded in real stats, real news, your real roster -- "
        "every answer shows the tool calls behind it." if chosen else "Pick a franchise in the sidebar first."
    )

    quick = st.columns(3)
    quick_prompts = [
        "Where is my squad weakest?",
        "Any injury news on my players?",
        "Show my saved strategy notes",
    ]
    clicked_prompt = None
    for col, qp in zip(quick, quick_prompts):
        if col.button(qp, use_container_width=True):
            clicked_prompt = qp

    for msg in st.session_state.chat_display:
        avatar = "🧑‍💼" if msg["role"] == "user" else "🏆"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(linkify(msg["content"]))
            if msg.get("trace"):
                render_trace(msg["trace"])

    prompt = st.chat_input("Ask about your squad, targets, or tell me to save a plan...")
    text = prompt or clicked_prompt
    if text:
        with st.chat_message("user", avatar="🧑‍💼"):
            st.markdown(text)
        with st.chat_message("assistant", avatar="🏆"):
            with st.spinner("Checking the real data..."):
                answer, trace = run_agent_turn(text)
            st.markdown(linkify(answer))
            render_trace(trace)

    if st.session_state.chat_display and st.button("🗑 Clear conversation"):
        st.session_state.agent_messages = None
        st.session_state.chat_display = []
        st.rerun()


# ================================================================ #
# Shell
# ================================================================ #
with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:12px;padding:4px 0 14px">'
        '<span style="font-size:30px">🏏</span>'
        '<div><div style="font-family:Space Grotesk,sans-serif;font-weight:800;font-size:21px;color:#0f172a">CricSavant AI</div>'
        '<div style="color:#526078;font-size:11.5px;text-transform:uppercase;letter-spacing:0.07em;font-weight:700">Franchise Strategy Platform</div></div></div>',
        unsafe_allow_html=True,
    )
franchise_picker()

nav = st.navigation([
    st.Page(page_strategy, title="Strategy Center", icon="🏟️", default=True),
    st.Page(page_players, title="Players", icon="🔍"),
    st.Page(page_analytics, title="League Analytics", icon="📊"),
    st.Page(page_chat, title="AI Analyst", icon="💬"),
])
nav.run()

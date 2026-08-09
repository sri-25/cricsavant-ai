"""CricSavant AI -- the real app.

4 tabs (Live Auction Console, Player Explorer, My Franchise, Analytics)
over a persistent AI chat drawer in the sidebar. Built on the 3
connection paths proven in the Phase 5 integration spike:
  - Unity Catalog gold tables, via a SQL warehouse       (lib/lakehouse.py)
  - Lakebase (franchises/roster/player_pool/change_log)  (lib/lakebase.py)
  - Foundation Model API (the chat agent)                (lib/agent.py)
plus Vector Search for player news (lib/vector_search.py).

The chat agent and the UI's own bid form call the EXACT SAME
lib/lakebase.py functions -- there's one set of auction rules, not a
UI copy and an agent copy that could drift apart.
"""

import datetime
import json

import pandas as pd
import streamlit as st

from lib import agent, charts, lakebase, lakehouse
from lib.styles import (
    FRANCHISE_COLORS, FRANCHISE_SHORT, ROLE_ICON, brand_header, inject_css, metric_card, pill,
)
from lib.utils import safe_num

st.set_page_config(page_title="CricSavant AI", page_icon="🏆", layout="wide")
inject_css()

# ---------------------------------------------------------------- #
# Session state
# ---------------------------------------------------------------- #
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = None  # full message log incl. system prompt, passed to run_agent
if "chat_display" not in st.session_state:
    st.session_state.chat_display = []  # [{role, content, trace?}] for rendering
if "auction_idx" not in st.session_state:
    st.session_state.auction_idx = 0
if "active_franchise" not in st.session_state:
    st.session_state.active_franchise = None


# ---------------------------------------------------------------- #
# Small helpers
# ---------------------------------------------------------------- #
def run_agent_turn(user_text: str):
    """Runs one agent turn, updates the sidebar chat history, and
    returns (answer, trace) so the CALLER can also render it inline
    right where the user clicked -- don't make them go find it.

    Every turn is prefixed with which franchise is currently selected
    in the sidebar. Without this, a free-typed question like "should I
    retain my current squad?" (no franchise named) has nothing telling
    the model which team "my" means -- it either guesses from whatever
    franchise happened to come up earlier in the conversation, or
    ignores the sidebar selection entirely. The quick-prompt buttons
    already interpolate the franchise name into their button text, so
    this fixes the general case (typed questions) the same way.
    """
    active = st.session_state.active_franchise
    context_note = (
        f"[App context: the user currently has \"{active}\" selected as their active "
        f"franchise in the sidebar. If their question doesn't name a franchise, assume "
        f"they mean this one.]\n" if active else ""
    )
    with st.spinner("CricSavant is checking the data..."):
        try:
            answer, updated_messages, trace = agent.run_agent(context_note + user_text, st.session_state.agent_messages)
        except Exception as e:
            answer, updated_messages, trace = f"Agent call failed: {str(e)[:400]}", st.session_state.agent_messages, []
    st.session_state.agent_messages = updated_messages
    st.session_state.chat_display.append({"role": "user", "content": user_text})
    st.session_state.chat_display.append({"role": "assistant", "content": answer, "trace": trace})
    if any(t.get("tool") == "execute_player_bid" for t in trace):
        invalidate_after_bid()
    return answer, trace


def render_inline_answer(answer: str, trace: list):
    st.markdown(
        f'<div class="csv-chat-msg csv-chat-assistant" style="margin-top:10px">'
        f'<b>🏆 CricSavant</b><br>{answer}</div>',
        unsafe_allow_html=True,
    )
    if trace:
        with st.expander(f"🔧 {len(trace)} tool call(s) used -- what the agent actually looked up", expanded=True):
            for t in trace:
                st.markdown(f"**`{t['tool']}`**  `{t['args']}`")
                st.json(t["result"], expanded=False)


def parse_payload(val) -> dict:
    """change_log.payload is JSONB in Lakebase and lands as a JSON
    string once it's gone through Spark's JDBC read + Delta write
    (001_sync_change_log_to_delta.py) into ops.lb_change_log_history.
    pg8000's own dict-vs-str behavior for jsonb columns has also
    varied across versions, so this accepts either shape rather than
    assuming one.
    """
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            return {}
    return {}


def fmt_cr(v) -> str:
    try:
        return f"₹{float(v):,.2f} cr"
    except (TypeError, ValueError):
        return "-"


@st.cache_data(ttl=20, show_spinner=False)
def cached_franchises() -> pd.DataFrame:
    return lakebase.list_franchises()


@st.cache_data(ttl=20, show_spinner=False)
def cached_unowned() -> pd.DataFrame:
    return lakebase.list_unowned_players()


@st.cache_data(ttl=60, show_spinner=False)
def cached_player_pool() -> pd.DataFrame:
    return lakebase.list_player_pool()


def invalidate_after_bid():
    cached_franchises.clear()
    cached_unowned.clear()


def find_profile_row(player_name: str, batter_df: pd.DataFrame, bowler_df: pd.DataFrame):
    """Thin wrapper over lib.lakehouse.match_gold_row -- kept here so
    every caller in this file can use the short name; the actual
    fuzzy-matching logic lives in lib/lakehouse.py so the agent's
    tools (lib/agent.py) use the exact same rule, not a second copy.
    """
    bat = lakehouse.match_gold_row(player_name, batter_df)
    bowl = lakehouse.match_gold_row(player_name, bowler_df)
    return (bat.to_dict() if bat is not None else None,
            bowl.to_dict() if bowl is not None else None)


def build_player_universe(batter_df: pd.DataFrame, bowler_df: pd.DataFrame, pool_df: pd.DataFrame) -> pd.DataFrame:
    """The full, browsable player list: every player with real KPI
    data in the gold tables (~1,500), unioned with the 369-player
    current auction shortlist. Searching for a real, well-known
    player who isn't in this particular mini-auction (already
    contracted elsewhere, or a historical player) still finds them --
    just tagged as not currently up for bid, instead of returning
    nothing the way a pool-only search did.
    """
    pool_names_lower = {n.lower(): r for n, r in zip(pool_df["player_name"], pool_df.to_dict("records"))}
    pool_surname_index: dict = {}
    for n, r in pool_names_lower.items():
        sn = n.strip().split()[-1] if n.strip() else ""
        pool_surname_index.setdefault(sn, []).append(r)

    bat_names_set = set(batter_df["player_name"])
    bowl_names_set = set(bowler_df["player_name"])
    all_names = sorted(bat_names_set | bowl_names_set | set(pool_df["player_name"]))
    rows = []
    for name in all_names:
        has_bat = name in bat_names_set
        has_bowl = name in bowl_names_set
        pool_row = pool_names_lower.get(name.lower())
        if pool_row is None:
            surname = name.strip().split()[-1].lower() if name.strip() else ""
            first_initial = name.strip()[0].lower() if name.strip() else ""
            cands = pool_surname_index.get(surname, [])
            if len(cands) == 1:
                pool_row = cands[0]
            elif len(cands) > 1:
                narrowed = [c for c in cands if c["player_name"].strip()[0].lower() == first_initial]
                pool_row = narrowed[0] if len(narrowed) == 1 else None

        if pool_row:
            rows.append({
                "player_name": name, "role": pool_row.get("role"), "country": pool_row.get("country"),
                "is_overseas": pool_row.get("is_overseas"), "base_price_lakh": pool_row.get("base_price_lakh"),
                "capped_status": pool_row.get("capped_status"), "in_pool": True,
                "has_batting": has_bat, "has_bowling": has_bowl,
            })
        else:
            role = "all-rounder" if (has_bat and has_bowl) else ("bowler" if has_bowl else "batter")
            rows.append({
                "player_name": name, "role": role, "country": None,
                "is_overseas": None, "base_price_lakh": None,
                "capped_status": None, "in_pool": False,
                "has_batting": has_bat, "has_bowling": has_bowl,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- #
# Sidebar -- franchise switcher + persistent AI chat drawer
# ---------------------------------------------------------------- #
with st.sidebar:
    brand_header("CricSavant AI", "Auction War Room")

    franchises_df = cached_franchises()
    if not franchises_df.empty:
        names = franchises_df["name"].tolist()
        default_idx = names.index(st.session_state.active_franchise) if st.session_state.active_franchise in names else 0
        picked = st.selectbox("Playing as", names, index=default_idx)
        # Switching teams mid-conversation but leaving old tool-call
        # results (another franchise's roster/purse numbers) sitting in
        # agent_messages is how you get an answer that's quietly still
        # about the old team. Reset the agent's own message history on
        # a switch -- the visible chat_display stays so nothing looks
        # like it vanished, but the model starts the new team clean.
        if st.session_state.active_franchise is not None and picked != st.session_state.active_franchise:
            st.session_state.agent_messages = None
        st.session_state.active_franchise = picked

    st.markdown("#### 💬 Ask CricSavant")
    st.caption("Grounded in real stats, live news, and your actual roster -- never a guess.")

    qcols = st.columns(2)
    quick_prompts = [
        "Bumrah's recent bowling form?",
        f"{st.session_state.active_franchise}'s roster & purse?" if st.session_state.active_franchise else "Roster & purse?",
        "Any recent injury news I should know?",
        "Who are the top death-overs finishers?",
    ]
    for i, qp in enumerate(quick_prompts):
        if qcols[i % 2].button(qp, key=f"qp_{i}", use_container_width=True):
            run_agent_turn(qp)

    chat_box = st.container(height=440)
    with chat_box:
        if not st.session_state.chat_display:
            st.markdown(
                '<div class="csv-chat-msg csv-chat-assistant">Hi, I\'m CricSavant AI. Ask me about '
                "player form, news, franchise budgets, or tell me to place a bid. Every answer below "
                "shows exactly which tools it called to get there.</div>",
                unsafe_allow_html=True,
            )
        else:
            # st.container(height=...) does NOT auto-scroll to the
            # bottom when new content is appended -- a quick-prompt
            # click or typed question renders its answer at the END of
            # this fixed-height box, invisibly below the fold, unless
            # you scroll the small sidebar box yourself. That's exactly
            # what "how do I even test the AI" looked like: click, see
            # nothing happen. Grouping into (question, answer) turns and
            # showing newest-first means what you just asked is always
            # the first thing visible, no scrolling required.
            messages = st.session_state.chat_display
            turns, i = [], 0
            while i < len(messages):
                if messages[i]["role"] == "user":
                    nxt = messages[i + 1] if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant" else None
                    turns.append((messages[i], nxt))
                    i += 2 if nxt else 1
                else:
                    turns.append((None, messages[i]))
                    i += 1

            for user_msg, asst_msg in reversed(turns):
                if user_msg:
                    st.markdown(f'<div class="csv-chat-msg csv-chat-user"><b>You</b><br>{user_msg["content"]}</div>', unsafe_allow_html=True)
                if asst_msg:
                    st.markdown(f'<div class="csv-chat-msg csv-chat-assistant"><b>🏆 CricSavant</b><br>{asst_msg["content"]}</div>', unsafe_allow_html=True)
                    if asst_msg.get("trace"):
                        with st.expander(f"🔧 {len(asst_msg['trace'])} tool call(s) used", expanded=False):
                            for t in asst_msg["trace"]:
                                st.markdown(f"**`{t['tool']}`**  `{t['args']}`")
                                st.json(t["result"], expanded=False)

    prompt = st.chat_input("Ask about a player, franchise, or place a bid...")
    if prompt:
        run_agent_turn(prompt)
        st.rerun()  # needed here: the chat history container above already rendered this pass

    if st.session_state.chat_display and st.button("🗑 Clear conversation", use_container_width=True):
        st.session_state.agent_messages = None
        st.session_state.chat_display = []
        st.rerun()

# ---------------------------------------------------------------- #
# Main content
# ---------------------------------------------------------------- #
brand_header("CricSavant AI", "Bring your own franchise -- powered by real cross-format form data")

batter_df = lakehouse.get_batter_profiles()
bowler_df = lakehouse.get_bowler_profiles()

tab_auction, tab_explorer, tab_franchise, tab_analytics = st.tabs(
    ["🔨 Live Auction Console", "🔍 Player Explorer", "🏛️ My Franchise", "📊 Analytics"]
)

# ================================================================ #
# TAB 1 -- Live Auction Console
# ================================================================ #
with tab_auction:
    pool = cached_unowned()
    if pool.empty:
        st.info("Every player in the pool has been acquired -- the auction is complete.")
    else:
        st.session_state.auction_idx %= len(pool)
        current = pool.iloc[st.session_state.auction_idx].to_dict()

        nav_l, nav_mid, nav_r = st.columns([1, 6, 1])
        if nav_l.button("⬅ Prev", use_container_width=True):
            st.session_state.auction_idx = (st.session_state.auction_idx - 1) % len(pool)
            st.rerun()
        nav_mid.markdown(
            f"<div style='text-align:center;color:#8b93ab;padding-top:10px;font-size:15px'>"
            f"Lot {st.session_state.auction_idx + 1} of {len(pool)} still available &nbsp;·&nbsp; set {current.get('set_code','-')}</div>",
            unsafe_allow_html=True,
        )
        if nav_r.button("Next ➡", use_container_width=True):
            st.session_state.auction_idx = (st.session_state.auction_idx + 1) % len(pool)
            st.rerun()

        left, right = st.columns([1.4, 1])

        with left:
            role = current.get("role", "batter")
            base_cr = float(current["base_price_lakh"]) / 100.0
            overseas_tag = pill("Overseas", "blue") if current.get("is_overseas") else pill("Domestic", "")
            capped_tag = pill(current.get("capped_status", "").title(), "gold") if current.get("capped_status") == "capped" else pill("Uncapped", "")
            st.markdown(
                f"""
                <div class="csv-player-hero">
                    <div class="csv-player-name">{ROLE_ICON.get(role,'🏏')} {current['player_name']}</div>
                    <div class="csv-player-meta">{current.get('country','')} &nbsp;·&nbsp; Age {current.get('age','-')} &nbsp;·&nbsp; {role.title()}
                    {" · " + current.get('bowling_style','').title() if current.get('bowling_style') not in (None, 'na') else ""}</div>
                    <div style="margin-top:14px">{overseas_tag} &nbsp; {capped_tag}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            m1, m2, m3 = st.columns(3)
            m1.markdown(metric_card("Base price", fmt_cr(base_cr)), unsafe_allow_html=True)

            bat_row, bowl_row = find_profile_row(current["player_name"], batter_df, bowler_df)
            if bat_row:
                m2.markdown(metric_card("Recent strike rate", f"{safe_num(bat_row.get('recent_strike_rate')):.1f}", f"{int(safe_num(bat_row.get('recent_innings')))} recent innings", "gold"), unsafe_allow_html=True)
            elif bowl_row:
                m2.markdown(metric_card("Recent economy", f"{safe_num(bowl_row.get('recent_economy')):.2f}", f"{int(safe_num(bowl_row.get('recent_innings')))} recent innings", "gold"), unsafe_allow_html=True)
            else:
                m2.markdown(metric_card("Form data", "N/A", "No qualifying recent innings in our KPI tables"), unsafe_allow_html=True)

            if bowl_row and bowl_row.get("bowler_type"):
                m3.markdown(metric_card("Role read", bowl_row["bowler_type"].title(), "from percentile ranks", "blue"), unsafe_allow_html=True)
            elif bat_row and bat_row.get("usual_batting_position"):
                m3.markdown(metric_card("Usual batting slot", f"#{int(bat_row['usual_batting_position'])}", "derived from crease-arrival order"), unsafe_allow_html=True)
            else:
                m3.markdown(metric_card("Source", "BCCI shortlist", "Dec 2025 auction pool"), unsafe_allow_html=True)

            if bat_row:
                st.plotly_chart(charts.batting_phase_radar(bat_row), use_container_width=True, config={"displayModeBar": False})
            elif bowl_row:
                st.plotly_chart(charts.bowling_phase_bars(bowl_row), use_container_width=True, config={"displayModeBar": False})

            if st.button("🤖 Ask CricSavant to assess this player", key="ask_auction", use_container_width=True):
                answer, trace = run_agent_turn(f"Give me a quick scouting take on {current['player_name']} -- recent form and any notable news.")
                render_inline_answer(answer, trace)

        with right:
            st.markdown("#### Place a bid")
            franchise_names = cached_franchises()["name"].tolist() if not cached_franchises().empty else []
            default_fidx = franchise_names.index(st.session_state.active_franchise) if st.session_state.active_franchise in franchise_names else 0
            bid_franchise = st.selectbox("Franchise", franchise_names, index=default_fidx, key="bid_franchise")
            bid_price = st.number_input("Bid amount (crore)", min_value=0.0, value=round(base_cr, 2), step=0.25, key="bid_price")

            if st.button("🔨 Place bid", type="primary", use_container_width=True):
                result = lakebase.execute_player_bid(bid_franchise, current["player_name"], float(bid_price))
                invalidate_after_bid()
                if result["success"]:
                    st.toast(f"SOLD! {current['player_name']} to {bid_franchise} for {fmt_cr(bid_price)}.", icon="✅")
                    st.session_state.auction_idx = st.session_state.auction_idx % max(len(cached_unowned()), 1)
                    st.rerun()
                else:
                    st.error(result["reason"])

            st.markdown("#### 📡 Live bid feed")
            feed = lakebase.recent_activity(limit=8)
            feed = feed[feed["tool_name"] == "execute_player_bid"] if not feed.empty else feed
            if feed.empty:
                st.caption("No bids placed yet this session.")
            else:
                for _, r in feed.iterrows():
                    ok = r["result_status"] == "success"
                    icon = "✅" if ok else "🚫"
                    payload = parse_payload(r["payload"])
                    p_name = payload.get("player_name", "?")
                    p_price = payload.get("price_cr", "?")
                    ts = pd.to_datetime(r["created_at"]).strftime("%H:%M:%S") if pd.notna(r["created_at"]) else ""
                    st.markdown(
                        f'<div class="csv-feed-row"><span>{icon} <b>{r.get("franchise_name") or "-"}</b> → {p_name}'
                        f' @ {fmt_cr(p_price) if isinstance(p_price,(int,float)) else p_price}</span>'
                        f'<span style="color:#8b93ab">{ts}</span></div>',
                        unsafe_allow_html=True,
                    )

# ================================================================ #
# TAB 2 -- Player Explorer
# ================================================================ #
with tab_explorer:
    if "player_universe" not in st.session_state:
        st.session_state.player_universe = build_player_universe(batter_df, bowler_df, cached_player_pool())
    universe_df = st.session_state.player_universe

    st.caption(
        f"{len(universe_df):,} players total -- every player with real form data in the Lakehouse, "
        f"plus the {len(cached_player_pool()):,}-player current auction shortlist. Search works across all of them."
    )

    fcol1, fcol2, fcol3, fcol4 = st.columns([2, 1, 1, 1])
    search = fcol1.text_input("Search player", placeholder="e.g. Rashid, Bumrah, Conway...")
    role_filter = fcol2.selectbox("Role", ["All", "batter", "bowler", "all-rounder", "wicketkeeper"])
    pool_filter = fcol3.selectbox("Scope", ["All players", "In current auction only"])
    overseas_filter = fcol4.selectbox("Origin", ["All", "Overseas", "Domestic"])

    filtered = universe_df.copy()
    if search:
        filtered = filtered[filtered["player_name"].str.contains(search, case=False, na=False)]
    if role_filter != "All":
        filtered = filtered[filtered["role"] == role_filter]
    if pool_filter == "In current auction only":
        filtered = filtered[filtered["in_pool"]]
    if overseas_filter != "All":
        filtered = filtered[filtered["is_overseas"] == (overseas_filter == "Overseas")]

    list_col, detail_col = st.columns([1, 1.6])
    with list_col:
        st.caption(f"{len(filtered)} matching players")
        display_df = filtered.copy()
        display_df["In auction"] = display_df["in_pool"].map({True: "🔨 Yes", False: "—"})
        display_df["Base price"] = display_df["base_price_lakh"].apply(
            lambda v: f"₹{v/100:.2f}cr" if pd.notna(v) else "—"
        )
        st.dataframe(
            display_df[["player_name", "role", "In auction", "Base price"]]
            .rename(columns={"player_name": "Player", "role": "Role"}),
            use_container_width=True, height=420, hide_index=True,
        )
        selected_name = st.selectbox(
            "Inspect player", filtered["player_name"].tolist() if not filtered.empty else [],
        )

    with detail_col:
        if selected_name:
            bat_row, bowl_row = find_profile_row(selected_name, batter_df, bowler_df)
            pool_info = filtered[filtered["player_name"] == selected_name].iloc[0].to_dict()

            st.markdown(f"### {ROLE_ICON.get(pool_info.get('role'),'🏏')} {selected_name}")
            if pool_info.get("in_pool"):
                badges = pill(f"🔨 In current auction · base {fmt_cr(pool_info['base_price_lakh']/100)}", "gold")
                if pool_info.get("country"):
                    badges += "&nbsp;" + pill(pool_info["country"], "")
                st.markdown(badges, unsafe_allow_html=True)
            else:
                st.markdown(pill("Not in this auction's shortlist -- already contracted or a historical player", "blue"), unsafe_allow_html=True)

            if not bat_row and not bowl_row:
                st.info("No qualifying recent-form data for this player in the KPI tables yet (thin sample across the 9 ingested competitions, 2008-2025).")

            if bat_row:
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(metric_card("Recent SR", f"{safe_num(bat_row.get('recent_strike_rate')):.1f}", tone="gold"), unsafe_allow_html=True)
                c2.markdown(metric_card("Recent avg", f"{safe_num(bat_row.get('recent_average')):.1f}"), unsafe_allow_html=True)
                c3.markdown(metric_card("Career runs", f"{int(safe_num(bat_row.get('career_runs'))):,}"), unsafe_allow_html=True)
                c4.markdown(metric_card("Boundary %", f"{safe_num(bat_row.get('recent_boundary_pct')):.1f}%"), unsafe_allow_html=True)
                st.plotly_chart(charts.batting_phase_radar(bat_row), use_container_width=True, config={"displayModeBar": False})
                st.plotly_chart(
                    charts.recent_vs_career_bar(bat_row, "recent_strike_rate", "career_strike_rate", "Strike rate"),
                    use_container_width=True, config={"displayModeBar": False},
                )

            if bowl_row:
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(metric_card("Recent economy", f"{safe_num(bowl_row.get('recent_economy')):.2f}", tone="gold"), unsafe_allow_html=True)
                c2.markdown(metric_card("Recent wickets", f"{int(safe_num(bowl_row.get('recent_wickets')))}"), unsafe_allow_html=True)
                c3.markdown(metric_card("Career wickets", f"{int(safe_num(bowl_row.get('career_wickets')))}"), unsafe_allow_html=True)
                bowler_type_val = bowl_row.get('bowler_type')
                bowler_type_val = bowler_type_val if isinstance(bowler_type_val, str) and bowler_type_val else 'n/a'
                c4.markdown(metric_card("Role read", bowler_type_val.title()), unsafe_allow_html=True)
                st.plotly_chart(charts.bowling_phase_bars(bowl_row), use_container_width=True, config={"displayModeBar": False})
                st.plotly_chart(
                    charts.bowler_role_scatter(bowler_df, highlight_name=selected_name),
                    use_container_width=True, config={"displayModeBar": False},
                )

            bc1, bc2 = st.columns(2)
            ask_clicked = bc1.button("🤖 Ask CricSavant about this player", key="ask_explorer", use_container_width=True)
            news_clicked = bc2.button("📰 Latest news", key="news_explorer", use_container_width=True)
            if ask_clicked:
                answer, trace = run_agent_turn(f"Tell me about {selected_name}'s current form -- is this a good auction pick and why?")
                render_inline_answer(answer, trace)
            if news_clicked:
                answer, trace = run_agent_turn(f"Any recent news on {selected_name}?")
                render_inline_answer(answer, trace)

# ================================================================ #
# TAB 3 -- My Franchise
# ================================================================ #
with tab_franchise:
    franchises_df = cached_franchises()
    if franchises_df.empty:
        st.warning("No franchises found.")
    else:
        names = franchises_df["name"].tolist()
        default_idx = names.index(st.session_state.active_franchise) if st.session_state.active_franchise in names else 0
        chosen = st.selectbox("Franchise", names, index=default_idx, key="franchise_tab_select")
        st.session_state.active_franchise = chosen

        status = lakebase.get_franchise_status(chosen, log=False)
        if not status["found"]:
            st.error("Franchise not found.")
        else:
            f = status["franchise"]
            total = float(f["purse_total_cr"])
            remaining = float(f["purse_remaining_cr"])
            spent = total - remaining
            roster = pd.DataFrame(status["roster"])

            color = FRANCHISE_COLORS.get(chosen, "#e8b84b")
            st.markdown(
                f"""<div class="csv-player-hero" style="border-left:4px solid {color}">
                <div class="csv-player-name">{FRANCHISE_SHORT.get(chosen, chosen)} <span style="font-size:20px;color:#8b93ab;font-weight:500">-- {chosen}</span></div>
                <div class="csv-player-meta">{f.get('owner_label','')}</div>
                </div>""",
                unsafe_allow_html=True,
            )

            m1, m2, m3 = st.columns(3)
            m1.markdown(metric_card("Purse remaining", fmt_cr(remaining), f"of {fmt_cr(total)}", "green"), unsafe_allow_html=True)
            squad_over_cap = status['squad_size'] > f['max_squad_size']
            m2.markdown(metric_card(
                "Squad size", f"{status['squad_size']} / {f['max_squad_size']}",
                "over the 2027 auction cap -- release decisions needed" if squad_over_cap else "",
                tone="red" if squad_over_cap else "",
            ), unsafe_allow_html=True)
            m3.markdown(metric_card("Overseas", f"{status['overseas_count']} / {f['max_overseas']}", tone="blue" if status['overseas_count'] < f['max_overseas'] else "red"), unsafe_allow_html=True)

            chart_l, chart_r = st.columns(2)
            with chart_l:
                st.plotly_chart(charts.purse_gauge(spent, total), use_container_width=True, config={"displayModeBar": False})
            with chart_r:
                st.plotly_chart(charts.squad_role_pie(roster), use_container_width=True, config={"displayModeBar": False})

            st.markdown("#### Roster")
            if roster.empty:
                st.markdown(
                    '<div class="csv-card" style="text-align:center;color:#8b93ab">'
                    "No players acquired yet for this franchise.<br>"
                    "Run <code>notebooks/014_seed_real_squads.py</code> to load the real current squad, "
                    "or head to the <b>🔨 Live Auction Console</b> tab to build one from scratch."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.dataframe(
                    roster[["player_name", "role", "is_overseas", "acquisition_type", "price_cr", "acquired_at"]]
                    .rename(columns={"player_name": "Player", "role": "Role", "is_overseas": "Overseas",
                                      "acquisition_type": "Type", "price_cr": "Price (cr)", "acquired_at": "Acquired"})
                    .sort_values("Acquired", ascending=False),
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    "**imported** rows are this team's real IPL 2026 squad (retained + Dec 2025 auction, "
                    "cited in notebooks/014_seed_real_squads.py) -- price not individually tracked for "
                    "these, see that file's header. **auction** rows are bids placed through this app's "
                    "own practice Auction Console."
                )

            # ---- Squad & Venue Fit: the retain/release intelligence ----
            st.markdown("#### 🎯 Squad & Venue Fit")
            home_venue = lakebase.get_home_venue(chosen)
            if home_venue:
                st.caption(
                    f"Real home venue: **{home_venue}**. Each player's overall recent form vs. their "
                    "record specifically at this ground (min. 60 balls faced/bowled there to qualify -- "
                    "'no qualifying sample' is a real, meaningful data point, not a gap to ignore)."
                )
            else:
                st.caption("Home venue not set for this franchise -- run sql/007_add_home_venue.sql.")

            if roster.empty:
                st.caption("No roster to analyze yet.")
            else:
                fit_rows = []
                for _, prow in roster.iterrows():
                    pname = prow["player_name"]
                    role = (prow.get("role") or "").lower()
                    bat_row, bowl_row = find_profile_row(pname, batter_df, bowler_df)
                    venue_bat, venue_bowl = lakehouse.venue_form_for_player(pname, chosen)

                    # A specialist bowler's headline number has to be their
                    # economy, not a stray batting strike rate from a
                    # handful of tail-end deliveries -- "if bat_row" alone
                    # was picking batting SR for pure bowlers (Rahul Chahar,
                    # Akeal Hosein, Matt Henry all showed "Bat SR" here),
                    # which is a wrong read for a retain/release decision.
                    bowler_first = role == "bowler" and bowl_row

                    if bowler_first:
                        recent_label = f"Bowl econ {safe_num(bowl_row.get('recent_economy')):.1f}"
                    elif bat_row:
                        recent_label = f"Bat SR {safe_num(bat_row.get('recent_strike_rate')):.0f}"
                    elif bowl_row:
                        recent_label = f"Bowl econ {safe_num(bowl_row.get('recent_economy')):.1f}"
                    else:
                        recent_label = "no Cricsheet sample"

                    if bowler_first and venue_bowl:
                        venue_label = f"Bowl econ {safe_num(venue_bowl.get('economy')):.1f} ({int(safe_num(venue_bowl.get('innings')))} inns here)"
                    elif venue_bat:
                        venue_label = f"Bat SR {safe_num(venue_bat.get('strike_rate')):.0f} ({int(safe_num(venue_bat.get('innings')))} inns here)"
                    elif venue_bowl:
                        venue_label = f"Bowl econ {safe_num(venue_bowl.get('economy')):.1f} ({int(safe_num(venue_bowl.get('innings')))} inns here)"
                    else:
                        venue_label = "no qualifying sample here"

                    fit_rows.append({
                        "Player": pname, "Role": prow["role"],
                        "Recent form (all venues)": recent_label,
                        "Form at home venue": venue_label,
                    })
                st.dataframe(pd.DataFrame(fit_rows), use_container_width=True, hide_index=True, height=360)

                if st.button("🤖 Get AI retention recommendations for this squad", key="ask_retention", use_container_width=True):
                    answer, trace = run_agent_turn(
                        f"Based on real recent form and home-venue fit, which players on {chosen}'s "
                        "current roster look like strong retains ahead of the next auction, and which "
                        "look like release candidates? Be specific, cite the actual numbers, and call "
                        "out anyone you don't have enough data to judge rather than guessing."
                    )
                    render_inline_answer(answer, trace)

# ================================================================ #
# TAB 4 -- Analytics  (Lakebase change_log -> Delta CDF sync, made visible)
# ================================================================ #
with tab_analytics:
    live_log = lakebase.all_change_log()
    synced_log = lakehouse.get_change_log_history()

    sync_l, sync_r = st.columns([3, 1])
    with sync_l:
        st.markdown("#### Lakebase → Delta CDF sync")
        st.caption(
            "`change_log` (Lakebase, live) is periodically synced into `cricsavant.ops.lb_change_log_history` "
            "(Unity Catalog Delta table) by `001_sync_change_log_to_delta.py` -- our Free-Edition stand-in for "
            "native Lakebase CDF. Everything below is live from Lakebase so this tab is always current; this "
            "strip is the proof the sync mechanism itself works."
        )
    with sync_r:
        lag = max(len(live_log) - len(synced_log), 0)
        st.markdown(metric_card("Synced to Delta", f"{len(synced_log)} / {len(live_log)}", "events" if lag == 0 else f"{lag} pending sync", "green" if lag == 0 else "gold"), unsafe_allow_html=True)

    st.divider()

    if live_log.empty:
        st.info("No agent or bid activity recorded yet -- place a bid or ask the chat agent a question to populate this tab.")
    else:
        total_events = len(live_log)
        bids = live_log[live_log["tool_name"] == "execute_player_bid"]
        success_bids = (bids["result_status"] == "success").sum() if not bids.empty else 0
        blocked_bids = bids["result_status"].astype(str).str.startswith("blocked").sum() if not bids.empty else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(metric_card("Total events", f"{total_events:,}", "live from Lakebase"), unsafe_allow_html=True)
        m2.markdown(metric_card("Bids placed", f"{len(bids)}"), unsafe_allow_html=True)
        m3.markdown(metric_card("Bids successful", f"{success_bids}", tone="green"), unsafe_allow_html=True)
        m4.markdown(metric_card("Blocked by guardrails", f"{blocked_bids}", "proof the validator fires", "red"), unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(charts.bid_outcome_donut(live_log), use_container_width=True, config={"displayModeBar": False})
        with c2:
            st.plotly_chart(charts.tool_usage_bar(live_log), use_container_width=True, config={"displayModeBar": False})

        st.plotly_chart(charts.activity_over_time(live_log), use_container_width=True, config={"displayModeBar": False})

        if not cached_franchises().empty:
            st.plotly_chart(charts.spend_by_franchise_bar(cached_franchises()), use_container_width=True, config={"displayModeBar": False})

        with st.expander("Raw event log (live from Lakebase)"):
            st.dataframe(live_log.sort_values("event_id", ascending=False), use_container_width=True, hide_index=True)

        if not synced_log.empty:
            with st.expander("Raw event log (as synced into ops.lb_change_log_history)"):
                st.dataframe(synced_log.sort_values("event_id", ascending=False), use_container_width=True, hide_index=True)

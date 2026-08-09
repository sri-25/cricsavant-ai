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


def run_agent_turn(user_text: str):
    with st.spinner("CricSavant is checking the data..."):
        try:
            answer, updated_messages, trace = agent.run_agent(user_text, st.session_state.agent_messages)
        except Exception as e:
            answer, updated_messages, trace = f"Agent call failed: {str(e)[:300]}", st.session_state.agent_messages, []
    st.session_state.agent_messages = updated_messages
    st.session_state.chat_display.append({"role": "user", "content": user_text})
    st.session_state.chat_display.append({"role": "assistant", "content": answer, "trace": trace})


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
    bat = batter_df[batter_df["player_name"].str.lower() == player_name.lower()]
    bowl = bowler_df[bowler_df["player_name"].str.lower() == player_name.lower()]
    bat_row = bat.iloc[0].to_dict() if not bat.empty else None
    bowl_row = bowl.iloc[0].to_dict() if not bowl.empty else None
    return bat_row, bowl_row


# ---------------------------------------------------------------- #
# Sidebar -- franchise switcher + persistent AI chat drawer
# ---------------------------------------------------------------- #
with st.sidebar:
    brand_header("CricSavant AI", "Auction War Room")

    franchises_df = cached_franchises()
    if not franchises_df.empty:
        names = franchises_df["name"].tolist()
        default_idx = names.index(st.session_state.active_franchise) if st.session_state.active_franchise in names else 0
        st.session_state.active_franchise = st.selectbox("Playing as", names, index=default_idx)

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

    chat_box = st.container(height=420)
    with chat_box:
        if not st.session_state.chat_display:
            st.markdown(
                '<div class="csv-chat-msg csv-chat-assistant">Hi, I\'m CricSavant AI. Ask me about '
                "player form, news, franchise budgets, or tell me to place a bid.</div>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.chat_display:
            css_class = "csv-chat-user" if msg["role"] == "user" else "csv-chat-assistant"
            who = "You" if msg["role"] == "user" else "CricSavant"
            st.markdown(
                f'<div class="csv-chat-msg {css_class}"><b>{who}</b><br>{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
            if msg.get("trace"):
                with st.expander(f"🔧 {len(msg['trace'])} tool call(s) used", expanded=False):
                    for t in msg["trace"]:
                        st.markdown(f"**`{t['tool']}`**({t['args']})")
                        st.json(t["result"], expanded=False)

    prompt = st.chat_input("Ask about a player, franchise, or place a bid...")
    if prompt:
        run_agent_turn(prompt)
        invalidate_after_bid()
        st.rerun()

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
            f"<div style='text-align:center;color:#8b93ab;padding-top:6px'>"
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
                    <div style="margin-top:12px">{overseas_tag} &nbsp; {capped_tag}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            m1, m2, m3 = st.columns(3)
            m1.markdown(metric_card("Base price", fmt_cr(base_cr)), unsafe_allow_html=True)

            bat_row, bowl_row = find_profile_row(current["player_name"], batter_df, bowler_df)
            if bat_row:
                m2.markdown(metric_card("Recent strike rate", f"{bat_row.get('recent_strike_rate') or 0:.1f}", f"{bat_row.get('recent_innings',0)} recent innings", "gold"), unsafe_allow_html=True)
            elif bowl_row:
                m2.markdown(metric_card("Recent economy", f"{bowl_row.get('recent_economy') or 0:.2f}", f"{bowl_row.get('recent_innings',0)} recent innings", "gold"), unsafe_allow_html=True)
            else:
                m2.markdown(metric_card("Form data", "N/A", "No qualifying recent innings"), unsafe_allow_html=True)

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

            if st.button("🤖 Ask CricSavant to assess this player", key="ask_auction"):
                run_agent_turn(f"Give me a quick scouting take on {current['player_name']} -- recent form and any notable news.")
                st.rerun()

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
                    st.success(f"SOLD! {current['player_name']} to {bid_franchise} for {fmt_cr(bid_price)}.")
                    st.session_state.auction_idx = st.session_state.auction_idx % max(len(cached_unowned()), 1)
                    st.balloons()
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
    pool_df = cached_player_pool()
    fcol1, fcol2, fcol3 = st.columns([2, 1, 1])
    search = fcol1.text_input("Search player", placeholder="e.g. Rashid, Bumrah, Conway...")
    role_filter = fcol2.selectbox("Role", ["All"] + sorted(pool_df["role"].dropna().unique().tolist()) if not pool_df.empty else ["All"])
    overseas_filter = fcol3.selectbox("Origin", ["All", "Overseas", "Domestic"])

    filtered = pool_df.copy()
    if search:
        filtered = filtered[filtered["player_name"].str.contains(search, case=False, na=False)]
    if role_filter != "All":
        filtered = filtered[filtered["role"] == role_filter]
    if overseas_filter != "All":
        filtered = filtered[filtered["is_overseas"] == (overseas_filter == "Overseas")]

    list_col, detail_col = st.columns([1, 1.6])
    with list_col:
        st.caption(f"{len(filtered)} players")
        st.dataframe(
            filtered[["player_name", "country", "role", "is_overseas", "base_price_lakh"]]
            .rename(columns={"player_name": "Player", "country": "Country", "role": "Role",
                              "is_overseas": "Overseas", "base_price_lakh": "Base (lakh)"}),
            use_container_width=True, height=420, hide_index=True,
        )
        selected_name = st.selectbox(
            "Inspect player", filtered["player_name"].tolist() if not filtered.empty else [],
        )

    with detail_col:
        if selected_name:
            bat_row, bowl_row = find_profile_row(selected_name, batter_df, bowler_df)
            pool_row = pool_df[pool_df["player_name"] == selected_name].iloc[0].to_dict()

            st.markdown(f"### {ROLE_ICON.get(pool_row.get('role'),'🏏')} {selected_name}")
            st.caption(f"{pool_row.get('country')} · {pool_row.get('role','').title()} · base price {fmt_cr(float(pool_row['base_price_lakh'])/100)}")

            if not bat_row and not bowl_row:
                st.info("No qualifying recent-form data for this player in the KPI tables yet (thin sample across the 9 ingested competitions, 2008-2025).")

            if bat_row:
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(metric_card("Recent SR", f"{bat_row.get('recent_strike_rate') or 0:.1f}", tone="gold"), unsafe_allow_html=True)
                c2.markdown(metric_card("Recent avg", f"{bat_row.get('recent_average') or 0:.1f}"), unsafe_allow_html=True)
                c3.markdown(metric_card("Career runs", f"{int(bat_row.get('career_runs') or 0):,}"), unsafe_allow_html=True)
                c4.markdown(metric_card("Boundary %", f"{(bat_row.get('recent_boundary_pct') or 0):.1f}%"), unsafe_allow_html=True)
                st.plotly_chart(charts.batting_phase_radar(bat_row), use_container_width=True, config={"displayModeBar": False})
                st.plotly_chart(
                    charts.recent_vs_career_bar(bat_row, "recent_strike_rate", "career_strike_rate", "Strike rate"),
                    use_container_width=True, config={"displayModeBar": False},
                )

            if bowl_row:
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(metric_card("Recent economy", f"{bowl_row.get('recent_economy') or 0:.2f}", tone="gold"), unsafe_allow_html=True)
                c2.markdown(metric_card("Recent wickets", f"{int(bowl_row.get('recent_wickets') or 0)}"), unsafe_allow_html=True)
                c3.markdown(metric_card("Career wickets", f"{int(bowl_row.get('career_wickets') or 0)}"), unsafe_allow_html=True)
                c4.markdown(metric_card("Role read", (bowl_row.get('bowler_type') or 'n/a').title()), unsafe_allow_html=True)
                st.plotly_chart(charts.bowling_phase_bars(bowl_row), use_container_width=True, config={"displayModeBar": False})
                st.plotly_chart(
                    charts.bowler_role_scatter(bowler_df, highlight_name=selected_name),
                    use_container_width=True, config={"displayModeBar": False},
                )

            bc1, bc2 = st.columns(2)
            if bc1.button("🤖 Ask CricSavant about this player", key="ask_explorer"):
                run_agent_turn(f"Tell me about {selected_name}'s current form -- is this a good auction pick and why?")
                st.rerun()
            if bc2.button("📰 Latest news", key="news_explorer"):
                run_agent_turn(f"Any recent news on {selected_name}?")
                st.rerun()

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

            hero_l, hero_r = st.columns([1, 1.6])
            with hero_l:
                color = FRANCHISE_COLORS.get(chosen, "#e8b84b")
                st.markdown(
                    f"""<div class="csv-player-hero" style="border-left:4px solid {color}">
                    <div class="csv-player-name">{FRANCHISE_SHORT.get(chosen, chosen)}</div>
                    <div class="csv-player-meta">{f.get('owner_label','')}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                st.plotly_chart(charts.purse_gauge(spent, total), use_container_width=True, config={"displayModeBar": False})

            with hero_r:
                m1, m2, m3 = st.columns(3)
                m1.markdown(metric_card("Purse remaining", fmt_cr(remaining), f"of {fmt_cr(total)}", "green"), unsafe_allow_html=True)
                m2.markdown(metric_card("Squad size", f"{status['squad_size']} / {f['max_squad_size']}"), unsafe_allow_html=True)
                m3.markdown(metric_card("Overseas", f"{status['overseas_count']} / {f['max_overseas']}", tone="blue" if status['overseas_count'] < f['max_overseas'] else "red"), unsafe_allow_html=True)
                st.plotly_chart(charts.squad_role_pie(roster), use_container_width=True, config={"displayModeBar": False})

            st.markdown("#### Roster")
            if roster.empty:
                st.caption("No players acquired yet -- head to the Auction Console.")
            else:
                st.dataframe(
                    roster[["player_name", "role", "is_overseas", "acquisition_type", "price_cr", "acquired_at"]]
                    .rename(columns={"player_name": "Player", "role": "Role", "is_overseas": "Overseas",
                                      "acquisition_type": "Type", "price_cr": "Price (cr)", "acquired_at": "Acquired"})
                    .sort_values("Acquired", ascending=False),
                    use_container_width=True, hide_index=True,
                )

# ================================================================ #
# TAB 4 -- Analytics  (Lakebase change_log -> Delta CDF sync, made visible)
# ================================================================ #
with tab_analytics:
    st.caption(
        "Sourced from `cricsavant.ops.lb_change_log_history` -- the Delta table synced from "
        "Lakebase's `change_log` (001_sync_change_log_to_delta.py), our Free-Edition stand-in "
        "for native Lakebase CDF."
    )
    ops_log = lakehouse.get_change_log_history()
    used_fallback = False
    if ops_log.empty:
        used_fallback = True
        ops_log = lakebase.all_change_log()
        if not ops_log.empty:
            st.warning(
                "The Delta sync job hasn't run yet (or found nothing new) -- showing live data "
                "read directly from Lakebase instead so this tab isn't empty. Run "
                "`001_sync_change_log_to_delta.py` to populate the Delta table."
            )

    if ops_log.empty:
        st.info("No agent or bid activity recorded yet -- place a bid or ask the chat agent a question first.")
    else:
        total_events = len(ops_log)
        bids = ops_log[ops_log["tool_name"] == "execute_player_bid"]
        success_bids = (bids["result_status"] == "success").sum() if not bids.empty else 0
        blocked_bids = bids["result_status"].astype(str).str.startswith("blocked").sum() if not bids.empty else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(metric_card("Total events logged", f"{total_events:,}", "ops.lb_change_log_history" if not used_fallback else "live from Lakebase"), unsafe_allow_html=True)
        m2.markdown(metric_card("Bids placed", f"{len(bids)}"), unsafe_allow_html=True)
        m3.markdown(metric_card("Bids successful", f"{success_bids}", tone="green"), unsafe_allow_html=True)
        m4.markdown(metric_card("Bids blocked by guardrails", f"{blocked_bids}", "proof the validator fires", "red"), unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(charts.bid_outcome_donut(ops_log), use_container_width=True, config={"displayModeBar": False})
        with c2:
            st.plotly_chart(charts.tool_usage_bar(ops_log), use_container_width=True, config={"displayModeBar": False})

        st.plotly_chart(charts.activity_over_time(ops_log), use_container_width=True, config={"displayModeBar": False})

        if not cached_franchises().empty:
            st.plotly_chart(charts.spend_by_franchise_bar(cached_franchises()), use_container_width=True, config={"displayModeBar": False})

        with st.expander("Raw event log"):
            st.dataframe(ops_log.sort_values("event_id", ascending=False), use_container_width=True, hide_index=True)

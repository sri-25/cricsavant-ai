"""CricSavant AI -- Strategic Auction & War Room Console.

v3 shell, ported from the approved Lovable prototype: TOP HEADER BAR
(brand + live status + franchise selector + purse/slots stat chips)
instead of a sidebar, tabbed sections in war-room console style, and
the Chief Analyst AI docked as a permanent right-hand panel on the
War Room tab. User-locked constraints: real team logos, the league
ticker, and every existing feature (strategy plays + notebook, full
player scouting, league analytics, CDF pipeline proof, grounded chat
with tool traces).
"""

import re

import pandas as pd
import streamlit as st

from lib import agent, charts, lakebase, lakehouse
from lib.styles import (
    FRANCHISE_COLORS, FRANCHISE_SHORT, ROLE_COLOR, ROLE_ICON, avatar_circle,
    header_bar, inject_css, metric_card, pill, stat_chip, team_hero, team_logo,
)
from lib.utils import safe_num

st.set_page_config(page_title="CricSavant AI", page_icon="🏏", layout="wide")

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

inject_css(accent=FRANCHISE_COLORS.get(st.session_state.active_franchise, "#e11d74"))

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
        with st.expander(f"Thought process · {len(trace)} tool calls", expanded=False):
            for t in trace:
                st.markdown(f"**`{t['tool']}`**  `{t['args']}`")
                st.json(t["result"], expanded=False)


def league_ticker():
    """User-locked feature: the moving strip of teams + budgets."""
    try:
        league = cached_league_summary()
    except Exception:
        return
    if league.empty:
        return
    items = []
    for _, r in league.iterrows():
        short = FRANCHISE_SHORT.get(r["name"], r["name"])
        items.append(
            f'<span class="csv-ticker-item">{team_logo(r["name"], size=26, radius=7)}'
            f'{short} <b>₹{float(r["purse_remaining_cr"]):,.2f}cr</b> '
            f'· {int(r["squad_size"])}/{int(r["max_squad_size"])}</span>'
        )
    track = "".join(items)
    st.markdown(
        f'<div class="csv-ticker"><div class="csv-ticker-track">{track}{track}</div></div>',
        unsafe_allow_html=True,
    )


# ================================================================ #
# HEADER BAR (Lovable pattern: brand · selector · stat chips)
# ================================================================ #
st.markdown(header_bar(), unsafe_allow_html=True)

franchises_df = cached_franchises()
hsel, hc1, hc2, hc3 = st.columns([2.2, 1, 1, 1])
chosen = None
status = None
if not franchises_df.empty:
    names = franchises_df["name"].tolist()
    default_idx = names.index(st.session_state.active_franchise) if st.session_state.active_franchise in names else 0
    with hsel:
        picked = st.selectbox("Franchise Desk", names, index=default_idx)
    if st.session_state.active_franchise is not None and picked != st.session_state.active_franchise:
        st.session_state.agent_messages = None  # team switch = fresh agent memory
    st.session_state.active_franchise = picked
    chosen = picked

    status = lakebase.get_franchise_status(chosen, log=False)
    if status["found"]:
        f = status["franchise"]
        os_left = int(f["max_overseas"]) - status["overseas_count"]
        slots_left = int(f["max_squad_size"]) - status["squad_size"]
        hc1.markdown(stat_chip("Remaining Purse", fmt_cr(f["purse_remaining_cr"])), unsafe_allow_html=True)
        hc2.markdown(stat_chip("Overseas Slots Left", f"{os_left} / {f['max_overseas']}",
                               "bad" if os_left < 0 else "ok"), unsafe_allow_html=True)
        hc3.markdown(stat_chip("Squad Slots Left", f"{slots_left} / {f['max_squad_size']}",
                               "bad" if slots_left < 0 else "ok"), unsafe_allow_html=True)

if not chosen or not status or not status.get("found"):
    st.info("No franchise data available.")
    st.stop()

f = status["franchise"]
roster = pd.DataFrame(status["roster"])


# ================================================================ #
# CHIEF ANALYST AI -- docked right panel (War Room tab)
# ================================================================ #
def chief_analyst_panel():
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
        '<div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(140deg,#e11d74,#be185d);'
        'display:flex;align-items:center;justify-content:center;font-size:17px">🧠</div>'
        '<div><div style="font-family:Space Grotesk;font-weight:800;font-size:15px;color:#e5e9f0">Chief Analyst AI</div>'
        '<div class="csv-mono" style="font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:#64748b">'
        'Grounded on Lakehouse + Live Web</div></div></div>',
        unsafe_allow_html=True,
    )

    clicked = None
    sug_cols = st.columns(2)
    suggestions = ["Squad weakness triage", "Injury & availability news",
                   "Venue matchup strategy", "Saved strategy notes"]
    for i, sug in enumerate(suggestions):
        if sug_cols[i % 2].button(sug, key=f"sug_{i}", use_container_width=True):
            clicked = sug

    box = st.container(height=430)
    with box:
        if not st.session_state.chat_display:
            st.caption(
                "ASK ANYTHING -- e.g. 'Can we afford a spin-allrounder and still fund two death "
                "bowlers?' Newest exchange shows first; every answer exposes its tool calls."
            )
        msgs = st.session_state.chat_display
        turns, i = [], 0
        while i < len(msgs):
            if msgs[i]["role"] == "user":
                nxt = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1]["role"] == "assistant" else None
                turns.append((msgs[i], nxt))
                i += 2 if nxt else 1
            else:
                turns.append((None, msgs[i]))
                i += 1
        for user_msg, asst_msg in reversed(turns):
            if user_msg:
                with st.chat_message("user", avatar="🧑‍💼"):
                    st.markdown(user_msg["content"])
            if asst_msg:
                with st.chat_message("assistant", avatar="🧠"):
                    st.markdown(linkify(asst_msg["content"]))
                    if asst_msg.get("trace"):
                        render_trace(asst_msg["trace"])

    prompt = st.chat_input(f"Ask about {FRANCHISE_SHORT.get(chosen, chosen)}...", key="analyst_input")
    text = prompt or clicked
    if text:
        with st.spinner("Analyst is checking the real data..."):
            run_agent_turn(text)
        st.rerun()

    if st.session_state.chat_display and st.button("New conversation", key="clear_chat"):
        st.session_state.agent_messages = None
        st.session_state.chat_display = []
        st.rerun()


# ================================================================ #
# TAB 1: WAR ROOM (strategy + docked analyst)
# ================================================================ #
def tab_war_room():
    left, right = st.columns([1.9, 1], gap="large")

    with right:
        chief_analyst_panel()

    with left:
        league_ticker()
        st.markdown(team_hero(chosen, f.get("owner_label", "")), unsafe_allow_html=True)

        total = float(f["purse_total_cr"])
        remaining = float(f["purse_remaining_cr"])
        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
        m1.markdown(metric_card("Purse Remaining", fmt_cr(remaining), f"of {fmt_cr(total)} total", "gold",
                                progress=(remaining / total * 100) if total else 0), unsafe_allow_html=True)
        over_cap = status["squad_size"] > f["max_squad_size"]
        m2.markdown(metric_card("Squad Size", f"{status['squad_size']} / {f['max_squad_size']}",
                                "over cap -- releases needed" if over_cap else "within cap",
                                "red" if over_cap else "",
                                progress=status["squad_size"] / f["max_squad_size"] * 100,
                                progress_color="#fb7185" if over_cap else None), unsafe_allow_html=True)
        over_os = status["overseas_count"] > f["max_overseas"]
        m3.markdown(metric_card("Overseas", f"{status['overseas_count']} / {f['max_overseas']}",
                                "over cap" if over_os else "slots used",
                                "red" if over_os else "blue",
                                progress=status["overseas_count"] / f["max_overseas"] * 100,
                                progress_color="#fb7185" if over_os else None), unsafe_allow_html=True)
        role_counts = roster["role"].value_counts().to_dict() if not roster.empty else {}
        m4.markdown(metric_card("Balance", " · ".join(f"{role_counts.get(r, 0)}{r[0].upper()}" for r in
                                ["batter", "bowler", "all-rounder", "wicketkeeper"]),
                                "bat · bowl · AR · WK"), unsafe_allow_html=True)

        st.markdown("#### Strategy Plays")
        plays = {
            "Retention & Release": (
                "retention", "retention_plan",
                f"Build a retention and release plan for {chosen} ahead of the IPL 2027 auction. "
                "Group the squad into retain / release / borderline with the real numbers beside each name, "
                "state the purse freed by the releases, and name the gaps those releases open.",
            ),
            "Auction Plan": (
                "auction", "auction_targets",
                f"Build {chosen}'s auction plan: first identify the squad's weakest areas from real form, "
                "then find the best available players in the auction pool for those gaps, and recommend "
                "specific signings with base price vs. our remaining purse math.",
            ),
            "Best XI + Impact": (
                "xi", "playing_xi",
                f"Simulate {chosen}'s strongest playing XI for a home game: batting order, bowling options, "
                "max 4 overseas on the field, and name the Impact Player substitution. Justify each slot "
                "with the player's actual numbers and flag thin-data picks honestly.",
            ),
        }
        selected_label = st.radio("Pick a play", list(plays.keys()), horizontal=True, label_visibility="collapsed")
        kind, note_type, prompt = plays[selected_label]

        run_col, hint_col = st.columns([1, 2.2])
        run_clicked = run_col.button("⚡ Run Strategy Engine", type="primary", use_container_width=True)
        has_result = (chosen, kind) in st.session_state.strategy_results
        hint_col.caption(
            "REAL SQUAD · REAL FORM · LIVE POOL — deep runs take 30-60s."
            + (" Previous run below; re-running refreshes it." if has_result else "")
        )

        if run_clicked:
            with st.spinner("Strategy engine is working through the real data..."):
                answer, trace = run_agent_turn(prompt, record_in_chat=False)
            st.session_state.strategy_results[(chosen, kind)] = (answer, trace)

        result = st.session_state.strategy_results.get((chosen, kind))
        if result:
            answer, trace = result
            st.markdown(
                f'<div class="csv-reco"><div class="csv-reco-label">Recommendation · {selected_label}</div></div>',
                unsafe_allow_html=True,
            )
            with st.chat_message("assistant", avatar="🧠"):
                st.markdown(linkify(answer))
            render_trace(trace)
            if st.button("💾 Save to notebook", key=f"save_{kind}"):
                res = lakebase.save_strategy_note(chosen, note_type, answer, created_by="user")
                if res.get("success"):
                    st.toast(f"Saved to {chosen}'s strategy notebook.", icon="✅")
                else:
                    st.error(res.get("reason", "Save failed."))

        # ---- Squad at a glance ----
        st.markdown("#### Current Squad Roster")
        if roster.empty:
            st.caption("No roster loaded -- run notebooks/014_seed_real_squads.py.")
        else:
            glance_l, glance_r = st.columns([1, 1.5], gap="medium")
            with glance_l:
                st.plotly_chart(charts.squad_role_pie(roster), use_container_width=True, config={"displayModeBar": False})
            with glance_r:
                glance = roster[["player_name", "role", "is_overseas"]].copy()
                glance["Status"] = glance["is_overseas"].map({True: "Overseas", False: "Domestic"})
                st.dataframe(
                    glance[["player_name", "role", "Status"]]
                    .rename(columns={"player_name": "Player", "role": "Role"}),
                    use_container_width=True, hide_index=True, height=330,
                )

        # ---- Notebook ----
        st.markdown("#### Strategy Notebook")
        try:
            notes = lakebase.list_strategy_notes(chosen, limit=10)
        except Exception:
            notes = pd.DataFrame()
        if notes.empty:
            st.caption("No saved plans yet -- run a strategy play and save it.")
        else:
            for _, n in notes.iterrows():
                ts = pd.to_datetime(n["created_at"]).strftime("%b %d, %H:%M")
                with st.expander(f"{n['note_type'].replace('_', ' ').title()} · {ts} · by {n['created_by']}"):
                    st.markdown(n["content"])


# ================================================================ #
# TAB 2: SCOUTING (players)
# ================================================================ #
def tab_players():
    batter_df = lakehouse.get_batter_profiles()
    bowler_df = lakehouse.get_bowler_profiles()
    pool_df = cached_player_pool()

    pool_names = set(pool_df["player_name"].str.lower())
    all_names = sorted(set(batter_df["player_name"]) | set(bowler_df["player_name"]) | set(pool_df["player_name"]))

    fc1, fc2 = st.columns([3, 1])
    search = fc1.text_input("Search Player", placeholder="e.g. Bumrah, Conway, Rashid...")
    scope = fc2.selectbox("Scope", ["All players", "In auction pool only"])

    names = all_names
    if search:
        s = search.lower()
        names = [n for n in names if s in n.lower()]
    if scope == "In auction pool only":
        names = [n for n in names if n.lower() in pool_names]

    st.caption(f"{len(names):,} OF {len(all_names):,} PLAYERS · 9 COMPETITIONS · 2008-2025")
    if not names:
        st.info("No players match. Some players are stored by initials (e.g. 'JJ Bumrah').")
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
    hc2.markdown(avatar_circle(selected, ROLE_COLOR.get(role, "#fbbf24"), size=54), unsafe_allow_html=True)
    if selected.lower() in pool_names:
        prow = pool_df[pool_df["player_name"].str.lower() == selected.lower()].iloc[0]
        st.markdown(
            pill(f"On the block · base {fmt_cr(float(prow['base_price_lakh']) / 100)}", "gold")
            + "&nbsp;" + pill(str(prow["country"]), ""),
            unsafe_allow_html=True,
        )

    if not bat_row and not bowl_row:
        st.info("No qualifying recent-form data in the KPI tables (thin sample across 2008-2025 competitions).")
        return

    if bat_row:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Recent SR", f"{safe_num(bat_row.get('recent_strike_rate')):.1f}", tone="gold"), unsafe_allow_html=True)
        c2.markdown(metric_card("Recent Avg", f"{safe_num(bat_row.get('recent_average')):.1f}"), unsafe_allow_html=True)
        c3.markdown(metric_card("Career Runs", f"{int(safe_num(bat_row.get('career_runs'))):,}"), unsafe_allow_html=True)
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
        c1.markdown(metric_card("Recent Economy", f"{safe_num(bowl_row.get('recent_economy')):.2f}", tone="gold"), unsafe_allow_html=True)
        c2.markdown(metric_card("Recent Wickets", f"{int(safe_num(bowl_row.get('recent_wickets')))}"), unsafe_allow_html=True)
        c3.markdown(metric_card("Career Wickets", f"{int(safe_num(bowl_row.get('career_wickets')))}"), unsafe_allow_html=True)
        btype = bowl_row.get("bowler_type")
        c4.markdown(metric_card("Role Read", btype.title() if isinstance(btype, str) and btype else "n/a"), unsafe_allow_html=True)
        ch1, ch2 = st.columns(2)
        with ch1:
            st.plotly_chart(charts.bowling_phase_bars(bowl_row), use_container_width=True, config={"displayModeBar": False})
        with ch2:
            st.plotly_chart(
                charts.bowler_role_scatter(bowler_df, highlight_name=bowl_row.get("player_name")),
                use_container_width=True, config={"displayModeBar": False},
            )

    if st.button("🧠 Ask Chief Analyst about this player", type="primary"):
        with st.spinner("Checking real form and news..."):
            answer, trace = run_agent_turn(
                f"Assess {selected} as a potential auction pick for my franchise -- recent form, role fit, any news.",
                record_in_chat=False,
            )
        st.markdown('<div class="csv-reco"><div class="csv-reco-label">Scouting Read</div></div>', unsafe_allow_html=True)
        with st.chat_message("assistant", avatar="🧠"):
            st.markdown(linkify(answer))
        render_trace(trace)


# ================================================================ #
# TAB 3: LEAGUE ANALYTICS
# ================================================================ #
def tab_league():
    league = cached_league_summary()
    if league.empty:
        st.info("No franchise data yet.")
        return

    # Franchise card rail -- real logos + purse + readiness
    cards = []
    for _, r in league.iterrows():
        over = int(r["squad_size"]) > int(r["max_squad_size"]) or int(r["overseas_count"]) > int(r["max_overseas"])
        pill_html = ('<span class="csv-mono" style="color:#fb7185;font-weight:800;font-size:9.5px;letter-spacing:0.1em">OVER CAP</span>' if over
                     else '<span class="csv-mono" style="color:#34d399;font-weight:800;font-size:9.5px;letter-spacing:0.1em">READY</span>')
        cards.append(
            f'<div style="flex:0 0 auto;width:112px;text-align:center;background:rgba(17,20,27,0.88);'
            f'border:1px solid rgba(148,163,184,0.12);border-radius:13px;padding:11px 8px">'
            f'<div style="display:flex;justify-content:center">{team_logo(r["name"], size=48, radius=10)}</div>'
            f'<div style="color:#e5e9f0;font-weight:800;font-size:12.5px;margin-top:6px">{FRANCHISE_SHORT.get(r["name"], r["name"])}</div>'
            f'<div class="csv-mono" style="color:#fbbf24;font-size:11px;font-weight:700;margin:2px 0 4px">₹{float(r["purse_remaining_cr"]):,.2f}cr</div>'
            f'{pill_html}</div>'
        )
    st.markdown(
        '<div style="display:flex;gap:10px;overflow-x:auto;padding:2px 2px 12px">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )

    total_purse_left = float(league["purse_remaining_cr"].astype(float).sum())
    most_cash = league.loc[league["purse_remaining_cr"].astype(float).idxmax()]
    over_cap = league[league["squad_size"].astype(int) > league["max_squad_size"].astype(int)]

    m1, m2, m3 = st.columns(3)
    m1.markdown(metric_card("League Purse in Play", f"₹{total_purse_left:,.1f} cr", "combined remaining · all 10 teams", "gold"), unsafe_allow_html=True)
    m2.markdown(metric_card("Max Purse Power", FRANCHISE_SHORT.get(most_cash["name"], most_cash["name"]),
                            f"{fmt_cr(most_cash['purse_remaining_cr'])} remaining", "green"), unsafe_allow_html=True)
    m3.markdown(metric_card("Over-Cap Warnings", f"{len(over_cap)}",
                            "must release before auction" if len(over_cap) else "all within cap",
                            "red" if len(over_cap) else "green"), unsafe_allow_html=True)

    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(charts.spend_by_franchise_bar(cached_franchises()), use_container_width=True, config={"displayModeBar": False})
    with ch2:
        st.plotly_chart(charts.league_role_balance(league), use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### Squad Balance Matrix")
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

    # ---- Lakehouse audit: CDF sync proof (terminal style) ----
    st.markdown("#### Lakehouse Audit (CDF)")
    try:
        live_log = lakebase.all_change_log()
        synced_log = lakehouse.get_change_log_history()
        lag = max(len(live_log) - len(synced_log), 0)
        pc1, pc2 = st.columns([1, 3])
        pc1.markdown(metric_card("Synced to Delta", f"{len(synced_log)} / {len(live_log)}",
                                 "events current" if lag == 0 else f"{lag} pending sync",
                                 "green" if lag == 0 else "gold"), unsafe_allow_html=True)
        pc2.caption(
            "EVERY AI TOOL CALL AND SAVED PLAN IS WRITTEN TO LAKEBASE CHANGE_LOG, THEN SYNCED INTO "
            "CRICSAVANT.OPS.LB_CHANGE_LOG_HISTORY (DELTA) -- THE LAKEBASE→DELTA CDF MECHANISM, "
            "AUDITABLE BELOW."
        )
        with st.expander("Audit log · live from Lakebase"):
            st.dataframe(live_log.sort_values("event_id", ascending=False).head(30), use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"Pipeline strip unavailable: {str(e)[:150]}")


# ================================================================ #
# TABS
# ================================================================ #
tabs = st.tabs(["⚔️ War Room", "🔍 Scouting", "📊 League Analytics"])
with tabs[0]:
    tab_war_room()
with tabs[1]:
    tab_players()
with tabs[2]:
    tab_league()

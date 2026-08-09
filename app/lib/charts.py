"""CricSavant AI -- Plotly chart builders.

Every figure is built defensively against missing/NULL columns and
against sparse/empty data (a fresh franchise, a single logged event) --
an empty-looking chart with a broken axis reads as "this is buggy",
so thin-data cases get an explicit friendly message instead.
"""

import pandas as pd
import plotly.graph_objects as go

from lib.styles import BG_CARD, BLUE, BORDER, FRANCHISE_COLORS, GOLD, GOLD_SOFT, GREEN, RED, TEXT, TEXT_DIM

FONT = dict(family="Inter, sans-serif", color=TEXT, size=13)


def _theme(fig: go.Figure, height=360, title=None) -> go.Figure:
    layout_kwargs = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=FONT,
        height=height,
        margin=dict(l=10, r=10, t=46 if title else 16, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=12, color=TEXT_DIM)),
        hoverlabel=dict(bgcolor=BG_CARD, bordercolor=BORDER, font=dict(color=TEXT, size=13)),
    )
    # Only set a title key at all when one is given -- passing an
    # explicit None title dict has caused a stray "undefined" render
    # in testing, safer to just never touch the key.
    if title:
        layout_kwargs["title"] = dict(text=title, font=dict(size=15, color=TEXT), x=0.02)
    fig.update_layout(**layout_kwargs)
    fig.update_xaxes(gridcolor=BORDER, zerolinecolor=BORDER, color=TEXT_DIM)
    fig.update_yaxes(gridcolor=BORDER, zerolinecolor=BORDER, color=TEXT_DIM)
    return fig


def _empty_state(message: str, height=260, title=None) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False, font=dict(size=13, color=TEXT_DIM),
        xref="paper", yref="paper", x=0.5, y=0.5,
    )
    fig.update_xaxes(visible=False, showgrid=False)
    fig.update_yaxes(visible=False, showgrid=False)
    return _theme(fig, height=height, title=title)


def batting_phase_radar(row: dict, compare_row: dict = None) -> go.Figure:
    """Powerplay / middle / death strike rate, plus situational SRs --
    the shape of a batter's game in one glance.
    """
    axes = ["Powerplay SR", "Middle SR", "Death SR", "Chase SR", "Finisher %"]
    vals = [
        row.get("powerplay_sr") or 0,
        row.get("middle_sr") or 0,
        row.get("death_sr") or 0,
        row.get("chase_sr") or 0,
        (row.get("finisher_pct") or 0) * (100 if (row.get("finisher_pct") or 0) <= 1 else 1),
    ]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]], theta=axes + [axes[0]],
        fill="toself", name=row.get("player_name", "Player"),
        line=dict(color=GOLD, width=2.5), fillcolor="rgba(232,184,75,0.25)",
    ))
    if compare_row is not None:
        cvals = [
            compare_row.get("powerplay_sr") or 0,
            compare_row.get("middle_sr") or 0,
            compare_row.get("death_sr") or 0,
            compare_row.get("chase_sr") or 0,
            (compare_row.get("finisher_pct") or 0) * (100 if (compare_row.get("finisher_pct") or 0) <= 1 else 1),
        ]
        fig.add_trace(go.Scatterpolar(
            r=cvals + [cvals[0]], theta=axes + [axes[0]],
            fill="toself", name=compare_row.get("player_name", "Compare"),
            line=dict(color=BLUE, width=2.5), fillcolor="rgba(91,141,239,0.18)",
        ))
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(showticklabels=True, gridcolor=BORDER, color=TEXT_DIM),
            angularaxis=dict(gridcolor=BORDER, color=TEXT, tickfont=dict(size=13)),
        ),
        showlegend=compare_row is not None,
    )
    return _theme(fig, height=420, title="Batting shape by phase")


def bowling_phase_bars(row: dict) -> go.Figure:
    phases = ["Powerplay", "Middle", "Death"]
    economies = [row.get("powerplay_economy"), row.get("middle_economy"), row.get("death_economy")]
    fig = go.Figure(go.Bar(
        x=phases, y=economies,
        marker_color=[GOLD, BLUE, RED],
        text=[f"{v:.2f}" if v is not None else "-" for v in economies],
        textposition="outside", textfont=dict(size=14),
        width=0.5,
    ))
    return _theme(fig, height=320, title="Economy by phase")


def bowler_role_scatter(df: pd.DataFrame, highlight_name: str = None) -> go.Figure:
    d = df.dropna(subset=["economy_percentile", "strike_rate_percentile"]).copy()
    if d.empty:
        return _empty_state("Not enough qualified bowlers to map yet.", height=420, title="Bowler role map")
    color_map = {"strike bowler": GOLD, "containment bowler": BLUE, "balanced": TEXT_DIM}
    fig = go.Figure()
    for bt, color in color_map.items():
        sub = d[d["bowler_type"] == bt]
        fig.add_trace(go.Scatter(
            x=sub["economy_percentile"], y=sub["strike_rate_percentile"],
            mode="markers", name=bt or "unclassified",
            marker=dict(size=10, color=color, opacity=0.75, line=dict(width=1, color=BORDER)),
            text=sub["player_name"],
            hovertemplate="%{text}<br>economy pct: %{x:.2f}<br>strike-rate pct: %{y:.2f}<extra></extra>",
        ))
    if highlight_name:
        hl = d[d["player_name"] == highlight_name]
        if not hl.empty:
            fig.add_trace(go.Scatter(
                x=hl["economy_percentile"], y=hl["strike_rate_percentile"],
                mode="markers+text", text=hl["player_name"], textposition="top center",
                textfont=dict(size=13, color=GOLD_SOFT),
                marker=dict(size=18, color=GOLD_SOFT, symbol="star", line=dict(width=2, color="white")),
                name="selected", showlegend=False,
            ))
    fig.update_xaxes(title="Economy percentile (lower economy = higher)")
    fig.update_yaxes(title="Strike-rate percentile (fewer balls/wkt = higher)")
    return _theme(fig, height=460, title="Bowler role map -- strike vs containment")


def purse_gauge(spent: float, total: float) -> go.Figure:
    remaining = max(total - spent, 0)
    fig = go.Figure(go.Pie(
        values=[spent, remaining] if total else [0, 1], hole=0.72,
        marker=dict(colors=[GOLD, "rgba(255,255,255,0.06)"]),
        textinfo="none", sort=False, direction="clockwise",
    ))
    pct = (spent / total * 100) if total else 0
    fig.add_annotation(
        text=f"<b style='font-size:26px'>{pct:.0f}%</b><br><span style='font-size:12px;color:{TEXT_DIM}'>of purse spent</span>",
        showarrow=False, font=dict(size=22, color=TEXT),
    )
    fig.update_layout(showlegend=False)
    return _theme(fig, height=260)


def squad_role_pie(roster: pd.DataFrame) -> go.Figure:
    if roster.empty:
        return _empty_state("No players acquired yet.", height=300, title="Squad composition")
    counts = roster["role"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values, hole=0.5,
        marker=dict(colors=[GOLD, BLUE, GREEN, RED]),
        textinfo="label+value", textfont=dict(size=13),
    ))
    fig.update_layout(showlegend=False)
    return _theme(fig, height=300, title="Squad composition")


def spend_by_franchise_bar(franchises: pd.DataFrame) -> go.Figure:
    d = franchises.copy()
    d["spent"] = d["purse_total_cr"].astype(float) - d["purse_remaining_cr"].astype(float)
    d = d.sort_values("spent", ascending=True)
    colors = [FRANCHISE_COLORS.get(n, GOLD) for n in d["name"]]
    fig = go.Figure(go.Bar(
        x=d["spent"], y=d["name"], orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}cr" for v in d["spent"]], textposition="outside", textfont=dict(size=13),
    ))
    fig.update_xaxes(title="Crore spent")
    return _theme(fig, height=420, title="Spend by franchise")


def bid_outcome_donut(change_log: pd.DataFrame) -> go.Figure:
    bids = change_log[change_log["tool_name"] == "execute_player_bid"].copy() if not change_log.empty else change_log
    if bids.empty:
        return _empty_state("No bids placed yet.", height=300, title="Bid outcomes")
    succ = (bids["result_status"] == "success").sum()
    blocked = bids["result_status"].astype(str).str.startswith("blocked").sum()
    fig = go.Figure(go.Pie(
        labels=["Successful bids", "Blocked by guardrails"], values=[succ, blocked],
        hole=0.55, marker=dict(colors=[GREEN, RED]), textinfo="label+value", textfont=dict(size=13),
    ))
    fig.update_layout(showlegend=False)
    return _theme(fig, height=300, title="Bid outcomes")


def tool_usage_bar(change_log: pd.DataFrame) -> go.Figure:
    if change_log.empty:
        return _empty_state("No agent activity yet -- ask the chat a question.", height=300, title="Agent tool-call volume")
    counts = change_log["tool_name"].value_counts()
    fig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation="h",
        marker_color=GOLD,
        text=counts.values, textposition="outside", textfont=dict(size=13),
    ))
    return _theme(fig, height=300, title="Agent tool-call volume")


def activity_over_time(change_log: pd.DataFrame) -> go.Figure:
    if len(change_log) < 2:
        return _empty_state(
            "Not enough activity yet to chart -- place a few bids or ask a few questions.",
            height=260, title="Activity over time",
        )
    d = change_log.copy()
    d["created_at"] = pd.to_datetime(d["created_at"])
    d = d.sort_values("created_at")
    d["cum_events"] = range(1, len(d) + 1)
    fig = go.Figure(go.Scatter(
        x=d["created_at"], y=d["cum_events"], mode="lines+markers",
        line=dict(color=GOLD, width=2.5), marker=dict(size=5),
        fill="tozeroy", fillcolor="rgba(232,184,75,0.12)",
    ))
    span = d["created_at"].max() - d["created_at"].min()
    fig.update_xaxes(tickformat="%H:%M:%S" if span < pd.Timedelta(days=1) else "%b %d")
    return _theme(fig, height=300, title="Cumulative agent/write activity")


def recent_vs_career_bar(row: dict, metric_recent: str, metric_career: str, label: str) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[label], y=[row.get(metric_recent) or 0], name="Recent form",
        marker_color=GOLD, width=0.35, offsetgroup=0,
        text=[f"{row.get(metric_recent) or 0:.1f}"], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=[label], y=[row.get(metric_career) or 0], name="Career",
        marker_color=BLUE, width=0.35, offsetgroup=1,
        text=[f"{row.get(metric_career) or 0:.1f}"], textposition="outside",
    ))
    fig.update_layout(barmode="group", showlegend=True)
    return _theme(fig, height=280)

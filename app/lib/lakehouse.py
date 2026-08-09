"""CricSavant AI -- Lakehouse (Unity Catalog) access via SQL warehouse.

The app runs as its own containerized service with no Spark session
(unlike the notebooks), so every gold-table read goes through a SQL
warehouse connection using WAREHOUSE_ID (a declared App resource, see
app.yaml) and the app's own service-principal identity via
`Config().authenticate` -- the same "unified auth" pattern proven
working in the Phase 5 integration spike (app.py's Test 1).

DELIBERATELY NO PARAMETERIZED QUERIES: an earlier version of this file
sent LIKE '%...%' searches through databricks-sql-connector's bind
parameters, and that broke in production (player lookups failing) --
the connector's parameter-substitution behavior around literal '%'
characters in a LIKE pattern isn't something to bet a demo on without
being able to test it live. Instead, both gold tables are pulled in
full (only ~1500/1420 rows, cached) and every search is a plain
pandas filter -- zero risk from query parameter binding, and faster
besides since repeated searches never re-hit the warehouse.
"""

import os

import pandas as pd
import streamlit as st
from databricks import sql as dbsql
from databricks.sdk.core import Config


@st.cache_resource(show_spinner=False)
def _connection():
    cfg = Config()
    warehouse_id = os.environ["WAREHOUSE_ID"]
    return dbsql.connect(
        server_hostname=cfg.host.replace("https://", "").replace("http://", ""),
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: cfg.authenticate,
    )


def run_query(query: str) -> pd.DataFrame:
    """Runs a plain, non-parameterized SELECT and returns a pandas
    DataFrame. Retries once on a fresh connection if the cached one
    has gone stale (warehouse scaled to zero, or an idle connection
    Databricks closed server-side) -- a real failure mode for a
    long-lived Streamlit process, not a hypothetical one.
    """
    try:
        conn = _connection()
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall_arrow().to_pandas()
    except Exception:
        _connection.clear()
        conn = _connection()
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall_arrow().to_pandas()


@st.cache_data(ttl=180, show_spinner=False)
def get_batter_profiles() -> pd.DataFrame:
    return run_query("SELECT * FROM cricsavant.gold.batter_profile")


@st.cache_data(ttl=180, show_spinner=False)
def get_bowler_profiles() -> pd.DataFrame:
    return run_query("SELECT * FROM cricsavant.gold.bowler_profile")


@st.cache_data(ttl=45, show_spinner=False)
def get_change_log_history() -> pd.DataFrame:
    """The Delta table synced from Lakebase's change_log (see
    001_sync_change_log_to_delta.py) -- proof the CDF-to-analytics
    mechanism works, surfaced as its own small status card in the
    Analytics tab rather than gating the whole tab on it.
    """
    try:
        return run_query(
            "SELECT event_id, event_type, table_name, tool_name, franchise_id, "
            "payload, result_status, created_at FROM cricsavant.ops.lb_change_log_history "
            "ORDER BY event_id"
        )
    except Exception:
        return pd.DataFrame(
            columns=["event_id", "event_type", "table_name", "tool_name",
                     "franchise_id", "payload", "result_status", "created_at"]
        )


def search_players(name_search: str, max_matches: int = 8):
    """Pandas-side fuzzy search over the cached, full gold tables.
    Returns (batter_matches_df, bowler_matches_df).

    A plain substring search alone is a real bug for exactly the kind
    of query this tool exists for: the model reasonably calls this
    with a player's actual full name ("Jasprit Bumrah"), but Cricsheet
    -- and therefore these gold tables -- store him as "JJ Bumrah".
    "jasprit bumrah" is not a substring of "jj bumrah", so the old
    version returned found=False for a player who has full, real data
    (confirmed live: Player Explorer finds "JJ Bumrah" instantly
    searching "bumrah"). Falls back to the same surname + first-initial
    rule lib.lakehouse.match_gold_row already uses everywhere else in
    this app, so this tool stops disagreeing with the rest of the UI
    about whether a well-known player "exists."
    """
    term = (name_search or "").strip().lower()
    bat_df = get_batter_profiles()
    bowl_df = get_bowler_profiles()
    if not term:
        return bat_df.iloc[0:0], bowl_df.iloc[0:0]

    def _search(df: pd.DataFrame) -> pd.DataFrame:
        hit = df[df["player_name"].str.lower().str.contains(term, na=False, regex=False)]
        if not hit.empty:
            return hit.head(max_matches)
        words = term.split()
        if not words:
            return df.iloc[0:0]
        surname, first_initial = words[-1], words[0][0]
        cand = df[df["player_name"].str.lower().str.split().str[-1] == surname]
        if cand.empty:
            return cand
        narrowed = cand[cand["player_name"].str.lower().str.strip().str[0] == first_initial]
        return (narrowed if not narrowed.empty else cand).head(max_matches)

    return _search(bat_df), _search(bowl_df)


def match_gold_row(name: str, gold_df: pd.DataFrame):
    """Matches a name against a gold profile table, tolerant of
    Cricsheet's inconsistent player naming (full name vs initials --
    confirmed straight from live data: "Sikandar Raza" but "SD Hope").
    Exact match first; falls back to surname + first-initial, and only
    commits to that fallback when it narrows to exactly one candidate.
    Shared by the app's Player Explorer/Auction Console AND by the
    agent's tools (lib/agent.py) -- one matching rule, not two that
    could silently disagree.
    """
    if gold_df.empty or not name or not name.strip():
        return None
    exact = gold_df[gold_df["player_name"].str.lower() == name.strip().lower()]
    if not exact.empty:
        return exact.iloc[0]

    parts = name.strip().split()
    if not parts:
        return None
    surname = parts[-1].lower()
    first_initial = parts[0][0].lower()

    cand = gold_df[gold_df["player_name"].str.lower().str.split().str[-1] == surname]
    if cand.empty:
        return None
    if len(cand) == 1:
        return cand.iloc[0]
    narrowed = cand[cand["player_name"].str.lower().str.strip().str[0] == first_initial]
    if len(narrowed) == 1:
        return narrowed.iloc[0]
    return None


# Real IPL home venues, matched fuzzily against Cricsheet's own venue
# strings (which vary across the 2008-2025 window this data covers --
# e.g. Delhi's ground has been "Feroz Shah Kotla" AND "Arun Jaitley
# Stadium" depending on season). See sql/007_add_home_venue.sql.
VENUE_KEYWORDS = {
    "Chennai Super Kings": ["Chidambaram", "Chepauk"],
    "Mumbai Indians": ["Wankhede"],
    "Royal Challengers Bengaluru": ["Chinnaswamy"],
    "Kolkata Knight Riders": ["Eden Gardens"],
    "Delhi Capitals": ["Arun Jaitley", "Feroz Shah Kotla", "Ferozeshah Kotla"],
    "Punjab Kings": ["Mullanpur", "Mohali", "Bindra", "Dharamshala", "Dharamsala"],
    "Rajasthan Royals": ["Sawai Mansingh", "Jaipur", "Guwahati"],
    "Sunrisers Hyderabad": ["Rajiv Gandhi", "Uppal"],
    "Gujarat Titans": ["Narendra Modi", "Motera", "Sardar Patel"],
    "Lucknow Super Giants": ["Ekana"],
}


@st.cache_data(ttl=300, show_spinner=False)
def get_batting_form_by_venue() -> pd.DataFrame:
    return run_query("SELECT * FROM cricsavant.gold.batting_form_by_venue")


@st.cache_data(ttl=300, show_spinner=False)
def get_bowling_form_by_venue() -> pd.DataFrame:
    return run_query("SELECT * FROM cricsavant.gold.bowling_form_by_venue")


def venue_form_for_player(player_name: str, franchise_name: str):
    """This player's real batting/bowling record specifically at
    `franchise_name`'s home venue (min 60 balls faced/bowled there,
    same qualification floor as every other gold form table). Returns
    (bat_row_or_None, bowl_row_or_None).
    """
    keywords = VENUE_KEYWORDS.get(franchise_name, [])
    if not keywords or not player_name:
        return None, None
    pattern = "|".join(keywords)

    bat_df = get_batting_form_by_venue()
    bat_at_venue = bat_df[bat_df["venue"].str.contains(pattern, case=False, na=False, regex=True)]
    bat_row = match_gold_row(player_name, bat_at_venue)

    bowl_df = get_bowling_form_by_venue()
    bowl_at_venue = bowl_df[bowl_df["venue"].str.contains(pattern, case=False, na=False, regex=True)]
    bowl_row = match_gold_row(player_name, bowl_at_venue)

    return (bat_row.to_dict() if bat_row is not None else None,
            bowl_row.to_dict() if bowl_row is not None else None)

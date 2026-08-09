"""CricSavant AI -- Lakehouse (Unity Catalog) access via SQL warehouse.

The app runs as its own containerized service with no Spark session
(unlike the notebooks), so every gold-table / ops-table read goes
through a SQL warehouse connection using WAREHOUSE_ID (a declared App
resource, see app.yaml) and the app's own service-principal identity
via `Config().authenticate` -- the same "unified auth" pattern proven
working in the Phase 5 integration spike (app.py's Test 1).
"""

import os
from typing import Tuple

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


def run_query(query: str, params: tuple = None) -> pd.DataFrame:
    """Runs a SELECT against the Lakehouse and returns a pandas DataFrame.

    Retries once on a fresh connection if the cached one has gone
    stale (warehouses that scaled to zero, or an idle connection
    Databricks closed server-side) -- a real failure mode for a
    long-lived Streamlit process, not a hypothetical one.
    """
    try:
        conn = _connection()
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            return cur.fetchall_arrow().to_pandas()
    except Exception:
        _connection.clear()
        conn = _connection()
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            return cur.fetchall_arrow().to_pandas()


@st.cache_data(ttl=120, show_spinner=False)
def get_batter_profiles() -> pd.DataFrame:
    return run_query("SELECT * FROM cricsavant.gold.batter_profile")


@st.cache_data(ttl=120, show_spinner=False)
def get_bowler_profiles() -> pd.DataFrame:
    return run_query("SELECT * FROM cricsavant.gold.bowler_profile")


@st.cache_data(ttl=60, show_spinner=False)
def get_change_log_history() -> pd.DataFrame:
    """The Delta table synced from Lakebase's change_log (see
    001_sync_change_log_to_delta.py) -- this is the CDF-to-analytics
    requirement made visible in the app: every bid and every agent
    tool call, queryable as a normal Delta table.
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


def search_player_profile(name_search: str, max_matches: int = 8) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fuzzy player search across both profile tables, merged on
    player_name -- used by the Player Explorer tab's search box.
    """
    like = f"%{name_search.strip().lower()}%"
    bat = run_query(
        "SELECT * FROM cricsavant.gold.batter_profile WHERE lower(player_name) LIKE %s LIMIT %s",
        (like, max_matches),
    )
    bowl = run_query(
        "SELECT * FROM cricsavant.gold.bowler_profile WHERE lower(player_name) LIKE %s LIMIT %s",
        (like, max_matches),
    )
    return bat, bowl

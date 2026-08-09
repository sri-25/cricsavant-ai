"""CricSavant AI -- Lakebase (Postgres OLTP) access.

Connects as the least-privilege `cricsavant_app` role (sql/006) using
the password injected via the LAKEBASE_APP_PASSWORD resource (see
app.yaml) -- the exact pattern proven in the Phase 5 spike (app.py
Test 2) and in notebooks/012_agent_tools.py / 013_agent_loop.py.

Connections are opened and closed per call rather than pooled/cached:
this app's write volume (a handful of bids per session) doesn't
justify pool machinery, and it sidesteps a long-lived Streamlit
process holding a Postgres connection open across an idle browser tab.
"""

import datetime
import decimal
import json
import os

import pandas as pd
import pg8000

LAKEBASE_HOST = "ep-curly-dream-d85sia2d.database.us-east-2.cloud.databricks.com"
LAKEBASE_DB = "databricks_postgres"


def _jsonable(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def get_conn():
    return pg8000.connect(
        host=LAKEBASE_HOST,
        port=5432,
        database=LAKEBASE_DB,
        user="cricsavant_app",
        password=os.environ["LAKEBASE_APP_PASSWORD"],
        ssl_context=True,
    )


def query_df(sql: str, params: tuple = None) -> pd.DataFrame:
    """Run a SELECT and return a pandas DataFrame -- used for the
    table/chart-feeding reads (franchises, player_pool, change_log).
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols)
    finally:
        conn.close()


def _log_tool_call(tool_name, table_name, franchise_id, payload, result_status):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO change_log (event_type, table_name, tool_name, franchise_id, payload, result_status) "
            "VALUES ('tool_call', %s, %s, %s, %s, %s)",
            (table_name, tool_name, franchise_id, json.dumps(_jsonable(payload)), result_status),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


# ---- Reference data (read-only from the app's own UI, not just the
# agent) ------------------------------------------------------------

def list_franchises() -> pd.DataFrame:
    return query_df(
        "SELECT franchise_id, name, owner_label, purse_total_cr, purse_remaining_cr, "
        "max_squad_size, max_overseas FROM franchises WHERE is_active ORDER BY name"
    )


def list_player_pool() -> pd.DataFrame:
    return query_df(
        "SELECT pool_id, sr_no, set_code, player_name, country, age, role, bowling_style, "
        "capped_status, is_overseas, base_price_lakh, source_url FROM player_pool "
        "WHERE is_current_reference ORDER BY sr_no"
    )


def list_unowned_players() -> pd.DataFrame:
    """player_pool minus anyone already on an active roster anywhere --
    what a live auction console would actually show as "still available".
    """
    return query_df(
        "SELECT p.pool_id, p.sr_no, p.set_code, p.player_name, p.country, p.age, p.role, "
        "p.bowling_style, p.capped_status, p.is_overseas, p.base_price_lakh, p.source_url "
        "FROM player_pool p "
        "WHERE p.is_current_reference "
        "AND NOT EXISTS (SELECT 1 FROM franchise_roster r WHERE lower(r.player_name) = lower(p.player_name) AND r.status = 'active') "
        "ORDER BY p.sr_no"
    )


def current_auction_rules() -> pd.DataFrame:
    return query_df(
        "SELECT effective_from, max_purse_cr, max_squad_size, min_squad_size, "
        "max_overseas_players, max_overseas_playing_xi, rtm_cards_per_team, notes, source_url "
        "FROM auction_rules WHERE is_current = TRUE LIMIT 1"
    )


def recent_activity(limit: int = 25) -> pd.DataFrame:
    return query_df(
        "SELECT cl.event_id, cl.event_type, cl.tool_name, cl.result_status, cl.payload, "
        "cl.created_at, f.name AS franchise_name "
        "FROM change_log cl LEFT JOIN franchises f ON f.franchise_id = cl.franchise_id "
        "ORDER BY cl.event_id DESC LIMIT %s",
        (limit,),
    )


def all_change_log() -> pd.DataFrame:
    return query_df(
        "SELECT cl.event_id, cl.event_type, cl.tool_name, cl.table_name, cl.result_status, "
        "cl.payload, cl.created_at, f.name AS franchise_name "
        "FROM change_log cl LEFT JOIN franchises f ON f.franchise_id = cl.franchise_id "
        "ORDER BY cl.event_id"
    )


# ---- The 4 agent tools, same validated logic as
# notebooks/013_agent_loop.py, callable directly by the UI (bid form)
# as well as by the chat agent -- one source of truth for the rules. --

def get_franchise_status(franchise_name: str, log: bool = True) -> dict:
    """log=True is the agent-tool behavior (013_agent_loop.py) --
    every call is a real tool invocation worth recording. The My
    Franchise tab calls this with log=False since Streamlit reruns
    this on every widget interaction; logging those would drown the
    Analytics tab's "agent tool-call volume" chart in page-view noise
    that has nothing to do with what the agent actually did.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT franchise_id, name, owner_label, purse_total_cr, purse_remaining_cr, "
            "max_squad_size, max_overseas FROM franchises WHERE lower(name) = lower(%s)",
            (franchise_name,),
        )
        row = cur.fetchone()
        if not row:
            if log:
                _log_tool_call("get_franchise_status", "franchises", None, {"query": franchise_name}, "not_found")
            return {"found": False, "query": franchise_name}
        cols = [d[0] for d in cur.description]
        franchise = _jsonable(dict(zip(cols, row)))
        fid = franchise["franchise_id"]

        cur.execute(
            "SELECT player_name, role, bowling_style, is_overseas, acquisition_type, "
            "price_cr, status, acquired_at FROM franchise_roster "
            "WHERE franchise_id = %s AND status = 'active' ORDER BY acquired_at",
            (fid,),
        )
        rcols = [d[0] for d in cur.description]
        roster = [_jsonable(dict(zip(rcols, r))) for r in cur.fetchall()]

        overseas_count = sum(1 for p in roster if p["is_overseas"])
        if log:
            _log_tool_call("get_franchise_status", "franchises", fid,
                            {"query": franchise_name, "squad_size": len(roster)}, "found")
        return {
            "found": True,
            "franchise": franchise,
            "squad_size": len(roster),
            "overseas_count": overseas_count,
            "roster": roster,
        }
    finally:
        cur.close()
        conn.close()


def execute_player_bid(franchise_name: str, player_name: str, price_cr: float) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT franchise_id, purse_remaining_cr, max_squad_size, max_overseas "
            "FROM franchises WHERE lower(name) = lower(%s)",
            (franchise_name,),
        )
        frow = cur.fetchone()
        if not frow:
            return {"success": False, "reason": f"No franchise found matching '{franchise_name}'."}
        fid, purse_remaining, max_squad, max_overseas = frow

        cur.execute(
            "SELECT role, bowling_style, is_overseas, base_price_lakh FROM player_pool "
            "WHERE lower(player_name) = lower(%s) ORDER BY pool_id LIMIT 1",
            (player_name,),
        )
        prow = cur.fetchone()
        if not prow:
            return {"success": False, "reason": f"No player found in player_pool matching '{player_name}'."}
        role, bowling_style, is_overseas, base_price_lakh = prow
        base_price_cr = float(base_price_lakh) / 100.0 if base_price_lakh is not None else 0.0

        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE is_overseas) FROM franchise_roster "
            "WHERE franchise_id = %s AND status = 'active'",
            (fid,),
        )
        squad_size, overseas_count = cur.fetchone()

        cur.execute(
            "SELECT 1 FROM franchise_roster WHERE lower(player_name) = lower(%s) AND status = 'active' LIMIT 1",
            (player_name,),
        )
        already_owned = cur.fetchone() is not None

        reasons = []
        if already_owned:
            reasons.append(f"{player_name} is already on an active roster.")
        if price_cr > float(purse_remaining):
            reasons.append(f"Bid {price_cr}cr exceeds {franchise_name}'s remaining purse of {float(purse_remaining)}cr.")
        if squad_size >= max_squad:
            reasons.append(f"{franchise_name}'s squad is already at the max size ({max_squad}).")
        if is_overseas and overseas_count >= max_overseas:
            reasons.append(f"{franchise_name} already has the max {max_overseas} overseas players.")
        if price_cr < base_price_cr:
            reasons.append(f"Bid {price_cr}cr is below {player_name}'s base price of {base_price_cr}cr.")

        payload = {
            "franchise_name": franchise_name, "player_name": player_name, "price_cr": price_cr,
            "role": role, "is_overseas": is_overseas, "base_price_cr": base_price_cr,
        }

        if reasons:
            result_status = "blocked: " + "; ".join(reasons)
            cur.execute(
                "INSERT INTO change_log (event_type, table_name, tool_name, franchise_id, payload, result_status) "
                "VALUES ('tool_call', 'franchise_roster', 'execute_player_bid', %s, %s, %s)",
                (fid, json.dumps(payload), result_status),
            )
            conn.commit()
            return {"success": False, "reason": "; ".join(reasons)}

        cur.execute(
            "INSERT INTO franchise_roster (franchise_id, player_name, role, bowling_style, is_overseas, "
            "acquisition_type, price_cr, status) VALUES (%s, %s, %s, %s, %s, 'auction', %s, 'active')",
            (fid, player_name, role, bowling_style, is_overseas, price_cr),
        )
        cur.execute(
            "UPDATE franchises SET purse_remaining_cr = purse_remaining_cr - %s WHERE franchise_id = %s",
            (price_cr, fid),
        )
        cur.execute(
            "INSERT INTO change_log (event_type, table_name, tool_name, franchise_id, payload, result_status) "
            "VALUES ('data_change', 'franchise_roster', 'execute_player_bid', %s, %s, 'success')",
            (fid, json.dumps(payload)),
        )
        conn.commit()
        return {"success": True, "franchise": franchise_name, "player": player_name, "price_cr": price_cr}
    except Exception as e:
        conn.rollback()
        return {"success": False, "reason": f"Unexpected error: {str(e)[:300]}"}
    finally:
        cur.close()
        conn.close()

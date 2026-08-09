# Databricks notebook source
# CricSavant AI -- the agent's 4 tools.
#
# Two retrieval, one more retrieval, one write -- deliberately plain
# Python functions here, not Unity Catalog SQL/Python Functions. Given
# how many Free Edition surprises we've hit on less-common features
# already (Vector Search package, psycopg2's native crash), this keeps
# the tool implementation in code we can fully see and debug, called
# directly by the agent's tool-calling loop (013) rather than betting
# on a UC Function registration path that hasn't been verified here.
# Still a real agent with real retrieval + write tools -- just a more
# predictable mechanism for getting there.
#
#   get_player_form_profile -- reads cricsavant.gold.batter_profile /
#                               bowler_profile (Lakehouse, via Spark --
#                               no extra credential needed, same
#                               session this notebook runs in)
#   search_player_news       -- reads the Vector Search index built in
#                               009 over Tavily-sourced news articles
#   get_franchise_status     -- reads Lakebase (franchises +
#                               franchise_roster) as the cricsavant_app
#                               role set up in 011
#   execute_player_bid       -- the one write tool. Validates against
#                               real auction constraints (purse, squad
#                               size, overseas cap, base price, already-
#                               owned) before writing, and logs BOTH
#                               successful and blocked attempts to
#                               change_log -- so a blocked bid is
#                               evidence the guardrails work, not a
#                               silent no-op.
#
# NOTE ON SCHEMA: franchise_roster has no foreign key to player_pool --
# it stores player_name/role/bowling_style/is_overseas directly on the
# roster row (see sql/001_lakebase_schema.sql). So execute_player_bid
# validates against player_pool at bid time, then copies those fields
# onto the new roster row; get_franchise_status reads straight off
# franchise_roster with no join.

# COMMAND ----------

%pip install pg8000 databricks-vectorsearch -q
dbutils.library.restartPython()

# COMMAND ----------

import json
import decimal
import datetime
import pg8000
from pyspark.sql import functions as F
from databricks.vector_search.client import VectorSearchClient

LAKEBASE_HOST = "ep-curly-dream-d85sia2d.database.us-east-2.cloud.databricks.com"
LAKEBASE_DB = "databricks_postgres"

VS_ENDPOINT_NAME = "cricsavant_endpoint"
VS_INDEX_NAME = "cricsavant.raw.player_news_articles_index"

_vsc = VectorSearchClient()


def _jsonable(value):
    # pg8000/Spark hand back Decimal/date types that json.dumps chokes
    # on -- normalize to plain float/str so every tool's return value
    # is safely passable to an LLM as a tool result.
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _get_lakebase_conn():
    return pg8000.connect(
        host=LAKEBASE_HOST,
        port=5432,
        database=LAKEBASE_DB,
        user="cricsavant_app",
        password=dbutils.secrets.get(scope="cricsavant", key="lakebase_app_password"),
        ssl_context=True,
    )


def _log_tool_call(tool_name, table_name, franchise_id, payload, result_status):
    # Observability-only -- change_log's own design (sql/001) documents
    # capturing tool_call events for reads, not just data_change writes,
    # so the eventual CDF sync shows the agent's full reasoning trail,
    # not just the bids. Fails open: a logging hiccup must never break
    # the actual tool response the agent is waiting on.
    try:
        conn = _get_lakebase_conn()
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


# COMMAND ----------

# TOOL 1 (retrieval): get_player_form_profile
#
# Fuzzy name match (not exact) since callers -- human or the LLM
# itself -- won't always type a player's name exactly as Cricsheet
# spells it. Returns ALL matches, not just the first: this is the
# same identity-collision risk the player_key work in 006/007 solved
# for (two different real "Rashid Khan"s) -- silently picking one
# would be exactly the kind of wrong-answer failure mode the whole
# player_id project was built to prevent.

def get_player_form_profile(player_name_search: str, max_matches: int = 3) -> dict:
    search = player_name_search.strip().lower()
    if not search:
        return {"found": False, "query": player_name_search, "matches": []}

    bat_rows = (
        spark.table("cricsavant.gold.batter_profile")
        .filter(F.lower(F.col("player_name")).contains(search))
        .limit(max_matches)
        .collect()
    )
    bowl_rows = (
        spark.table("cricsavant.gold.bowler_profile")
        .filter(F.lower(F.col("player_name")).contains(search))
        .limit(max_matches)
        .collect()
    )

    matches = []
    key_to_entry = {}
    for r in bat_rows:
        d = r.asDict()
        key = d.get("batter_key")
        entry = {"player_key": key, "player_name": d.get("player_name"), "batting": _jsonable(d)}
        matches.append(entry)
        key_to_entry[key] = entry
    for r in bowl_rows:
        d = r.asDict()
        key = d.get("bowler_key")
        if key in key_to_entry:
            key_to_entry[key]["bowling"] = _jsonable(d)
        else:
            entry = {"player_key": key, "player_name": d.get("player_name"), "bowling": _jsonable(d)}
            matches.append(entry)
            key_to_entry[key] = entry

    if not matches:
        _log_tool_call("get_player_form_profile", "gold.batter_profile/bowler_profile", None,
                        {"query": player_name_search}, "not_found")
        return {"found": False, "query": player_name_search, "matches": []}

    _log_tool_call("get_player_form_profile", "gold.batter_profile/bowler_profile", None,
                    {"query": player_name_search, "match_count": len(matches)}, "found")
    return {
        "found": True,
        "query": player_name_search,
        "match_count": len(matches),
        "note": "More than one match means a genuine name collision or an ambiguous partial match -- disambiguate before treating stats as a single player's." if len(matches) > 1 else None,
        "matches": matches,
    }


# COMMAND ----------

# Quick test -- Bumrah's real career/recent numbers were already
# manually verified back in 007 (254 career innings, 308 career
# wickets, career_economy 7.09). Confirming the tool surfaces the same
# numbers, not re-deriving them.
import pprint
pprint.pprint(get_player_form_profile("Bumrah"))

# COMMAND ----------

# TOOL 2 (retrieval): search_player_news
#
# Thin wrapper around the Delta Sync Index built in 009. Prepending
# the player name to the query text (when given) steers the semantic
# search toward that player specifically, since the index embeds
# whole-article content, not per-player-tagged chunks.

def search_player_news(query: str, player_name: str = None, num_results: int = 5) -> dict:
    search_text = f"{player_name}: {query}" if player_name else query
    index = _vsc.get_index(VS_ENDPOINT_NAME, VS_INDEX_NAME)
    results = index.similarity_search(
        query_text=search_text,
        columns=["player_name", "title", "url"],
        num_results=num_results,
    )
    rows = results.get("result", {}).get("data_array", [])
    articles = [{"player_name": r[0], "title": r[1], "url": r[2]} for r in rows]
    _log_tool_call("search_player_news", "raw.player_news_articles_index", None,
                    {"query": search_text, "article_count": len(articles)},
                    "found" if articles else "no_results")
    return {"query": search_text, "article_count": len(articles), "articles": articles}


# COMMAND ----------

pprint.pprint(search_player_news("explosive death overs finisher in great recent form"))

# COMMAND ----------

# TOOL 3 (retrieval): get_franchise_status
#
# Reads franchise_roster directly -- no join to player_pool, see the
# schema note at the top of this file.

def get_franchise_status(franchise_name: str) -> dict:
    conn = _get_lakebase_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT franchise_id, name, owner_label, purse_total_cr, purse_remaining_cr, "
            "max_squad_size, max_overseas FROM franchises WHERE lower(name) = lower(%s)",
            (franchise_name,),
        )
        row = cur.fetchone()
        if not row:
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


# COMMAND ----------

pprint.pprint(get_franchise_status("Chennai Super Kings"))

# COMMAND ----------

# TOOL 4 (write): execute_player_bid
#
# Real auction constraints, checked in order, ALL violations reported
# together (not just the first) so a blocked bid tells the agent
# everything wrong with it in one round trip:
#   - player not already active on any franchise's roster
#   - bid doesn't exceed the franchise's remaining purse
#   - franchise isn't already at max squad size
#   - overseas cap isn't exceeded (only checked if the player is overseas)
#   - bid isn't below the player's real BCCI-listed base price
#
# Every attempt is logged to change_log -- success AND blocked -- per
# the table's documented design (sql/001) of doubling as proof the
# guardrails actually fire, not just a transaction ledger.

def execute_player_bid(franchise_name: str, player_name: str, price_cr: float) -> dict:
    conn = _get_lakebase_conn()
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


# COMMAND ----------

# Test: pull a real player from player_pool (not a guessed name) so
# this test is guaranteed to match something real, then bid on them.
conn = _get_lakebase_conn()
cur = conn.cursor()
cur.execute("SELECT player_name, base_price_lakh, is_overseas FROM player_pool ORDER BY pool_id LIMIT 1")
test_player_name, test_base_price_lakh, test_is_overseas = cur.fetchone()
cur.close()
conn.close()
print(f"Testing with: {test_player_name} (base price {float(test_base_price_lakh)/100:.2f}cr, overseas={test_is_overseas})")

# COMMAND ----------

# Bid exactly at base price -- should succeed
pprint.pprint(execute_player_bid("Chennai Super Kings", test_player_name, float(test_base_price_lakh) / 100.0))

# COMMAND ----------

# Same player again -- should be blocked as already-owned
pprint.pprint(execute_player_bid("Mumbai Indians", test_player_name, float(test_base_price_lakh) / 100.0))

# COMMAND ----------

# Confirm the roster and purse actually updated
pprint.pprint(get_franchise_status("Chennai Super Kings"))

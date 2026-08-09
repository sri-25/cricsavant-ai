# Databricks notebook source
# CricSavant AI -- the agent loop: an LLM wired up to the 4 tools
# built and validated standalone in 012_agent_tools.py, via the
# Databricks Foundation Model API's OpenAI-compatible tool-calling
# interface.
#
# Why this file duplicates 012's tool code instead of %run-ing it:
# 012 has its own %pip install + restartPython() cell. Chaining a
# %run into a notebook that restarts the Python kernel mid-execution
# is exactly the kind of fragile, order-dependent setup that's
# repeatedly caused problems in this project (009's install/restart
# issues, the widget-then-run-again dance). Keeping this notebook
# self-contained -- one install+restart, one copy of the tool code --
# trades a little duplication for not reintroducing that risk. 012
# stays as the standalone validation harness for the tools; this file
# is what Phase 5's app will actually run.
#
# GROUNDING GUARDRAILS -- the actual point of this file, not just
# plumbing:
#   1. The system prompt instructs the model to NEVER state a stat,
#      price, or franchise status from memory -- always call the tool.
#   2. get_player_form_profile returning >1 match (a genuine name
#      collision, like the two real "Rashid Khan"s found in 007) is
#      surfaced to the model as an ambiguity to ask the user about,
#      not something to silently resolve by picking one.
#   3. execute_player_bid is framed as a real, consequential write --
#      the model is told not to call it speculatively.
#   4. Every tool result -- including failures -- is fed back to the
#      model verbatim, so a blocked bid or a "not found" produces an
#      answer grounded in what actually happened, not a guess.

# COMMAND ----------

%pip install pg8000 databricks-vectorsearch openai -q
dbutils.library.restartPython()

# COMMAND ----------

import json
import decimal
import datetime
import pprint
import pg8000
from pyspark.sql import functions as F
from databricks.vector_search.client import VectorSearchClient
from openai import OpenAI

LAKEBASE_HOST = "ep-curly-dream-d85sia2d.database.us-east-2.cloud.databricks.com"
LAKEBASE_DB = "databricks_postgres"

VS_ENDPOINT_NAME = "cricsavant_endpoint"
VS_INDEX_NAME = "cricsavant.raw.player_news_articles_index"

# Tool-calling-capable model on the Foundation Model API. If this
# model errors out or doesn't invoke tools reliably, databricks-gpt-oss-120b
# is the fallback to try -- swap the string below and rerun.
AGENT_MODEL = "databricks-meta-llama-3-3-70b-instruct"

_vsc = VectorSearchClient()

ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
_client = OpenAI(
    api_key=ctx.apiToken().get(),
    base_url=f"{ctx.apiUrl().get()}/serving-endpoints",
)


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
    # so the CDF sync in 001_sync_change_log_to_delta.py shows the
    # agent's full reasoning trail, not just the bids. Fails open: a
    # logging hiccup must never break the actual tool response.
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

# The 4 tools -- identical logic to 012_agent_tools.py (already
# validated there). See that file for the design rationale on each.

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
        "note": "More than one match means a genuine name collision or an ambiguous partial match -- ask the user to clarify which player before treating stats as a single player's." if len(matches) > 1 else None,
        "matches": matches,
    }


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


_TOOL_FUNCTIONS = {
    "get_player_form_profile": get_player_form_profile,
    "search_player_news": search_player_news,
    "get_franchise_status": get_franchise_status,
    "execute_player_bid": execute_player_bid,
}

# COMMAND ----------

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_player_form_profile",
            "description": (
                "Look up a cricketer's real batting/bowling statistics (recent form, career "
                "numbers, role signals like usual batting position or bowler type) from the "
                "Cricsheet-derived stats database. ALWAYS call this before stating any specific "
                "number about a player's performance -- never guess or recall stats from memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "player_name_search": {"type": "string", "description": "Full or partial player name to search for."}
                },
                "required": ["player_name_search"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_player_news",
            "description": (
                "Search recent news articles about a player. Use for questions about current "
                "form, injuries, or recent events not captured in structured stats. ALWAYS cite "
                "the article URL when using information from this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for."},
                    "player_name": {"type": "string", "description": "Player name to focus the search on, if applicable."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_franchise_status",
            "description": (
                "Get a franchise's current purse remaining, squad size, overseas player count, "
                "and full roster. ALWAYS call this before answering any question about a "
                "franchise's budget or roster -- never assume or estimate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "franchise_name": {"type": "string", "description": "Name of the IPL franchise, e.g. 'Chennai Super Kings'."}
                },
                "required": ["franchise_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_player_bid",
            "description": (
                "Attempt to acquire a player for a franchise at a given price. This is a REAL, "
                "WRITE action with real consequences for the franchise's purse -- only call it "
                "when the user has explicitly asked to place this specific bid (franchise + "
                "player + price all given), never speculatively. Returns success or a specific "
                "reason for rejection (already owned, insufficient purse, squad full, overseas "
                "cap exceeded, below base price)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "franchise_name": {"type": "string"},
                    "player_name": {"type": "string"},
                    "price_cr": {"type": "number", "description": "Bid amount in crore rupees."},
                },
                "required": ["franchise_name", "player_name", "price_cr"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are CricSavant AI, an auction-companion assistant for an IPL fantasy-franchise auction app.

GROUNDING RULES (never violate these):
1. Never state a specific statistic, price, or franchise status from memory or estimation -- always call the relevant tool first.
2. If get_player_form_profile returns more than one match, that means a genuine name collision or ambiguity (there can be two real players with similar names). Ask the user to clarify which player they mean rather than picking one yourself.
3. When you use information from search_player_news, always include the source URL.
4. execute_player_bid is a real write action with real consequences for a franchise's purse. Only call it when the user has clearly specified a franchise, a player, and a price and asked you to place that bid -- do not call it speculatively or "to see what happens".
5. If a tool call fails, returns found=False, or a bid is blocked, say so plainly and explain why using the tool's own reason -- never fill the gap with a guess.
6. Keep answers concise and grounded strictly in what the tools returned.
"""

# COMMAND ----------

def run_agent(user_message: str, messages: list = None, max_turns: int = 6):
    """Runs one user turn through the tool-calling loop. Pass back the
    returned `messages` list to continue a multi-turn conversation."""
    if messages is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": user_message})

    for _ in range(max_turns):
        response = _client.chat.completions.create(
            model=AGENT_MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )
        choice = response.choices[0]
        messages.append(choice.message.model_dump(exclude_none=True))

        if not choice.message.tool_calls:
            return choice.message.content, messages

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            fn = _TOOL_FUNCTIONS.get(fn_name)
            try:
                fn_args = json.loads(tool_call.function.arguments)
                result = fn(**fn_args) if fn else {"error": f"Unknown tool '{fn_name}'"}
            except Exception as e:
                result = {"error": str(e)[:300]}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(_jsonable(result)),
            })

    return "Reached the tool-call turn limit without a final answer -- something's looping.", messages


# COMMAND ----------

# Test 1: plain stats question -- should call get_player_form_profile
# and answer grounded in Bumrah's real numbers.
answer, _ = run_agent("What are Bumrah's recent bowling numbers, and is he a good pick for the death overs?")
print(answer)

# COMMAND ----------

# Test 2: news question -- should call search_player_news and cite a URL.
answer, _ = run_agent("Any recent news on how Jofra Archer has been playing?")
print(answer)

# COMMAND ----------

# Test 3: franchise status -- should call get_franchise_status and
# reflect the Devon Conway bid from 012's test run.
answer, _ = run_agent("What's Chennai Super Kings' roster and remaining purse right now?")
print(answer)

# COMMAND ----------

# Test 4: the grounding guardrail that matters most -- a bid on a
# player who's already owned (Devon Conway, per 012's test) should
# come back blocked, with the agent explaining the real reason, not
# claiming success.
answer, _ = run_agent("Bid 5 crore for Devon Conway for Mumbai Indians.")
print(answer)

# COMMAND ----------

# Test 5: the identity-collision guardrail -- 007 found two distinct
# real "Rashid Khan"s. The agent should notice the ambiguity and ask,
# not silently merge or pick one.
answer, _ = run_agent("What are Rashid Khan's career stats?")
print(answer)

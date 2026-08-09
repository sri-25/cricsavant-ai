"""CricSavant AI -- the agent: same 4 tools and grounding guardrails
validated in notebooks/013_agent_loop.py, ported to run inside the
Databricks App process (no spark/dbutils available here).

get_player_form_profile: Spark filter -> SQL warehouse query (see
lib/lakehouse.py) against the same cricsavant.gold.batter_profile /
bowler_profile tables.
search_player_news: identical Vector Search call, via lib/vector_search.py.
get_franchise_status / execute_player_bid: identical Lakebase logic,
via lib/lakebase.py (single source of truth shared with the Auction
Console's bid form -- the chat agent and the UI enforce the exact same
rules because they call the exact same functions).

Model access: the OpenAI-compatible client against the Foundation
Model API, authenticated via the same cfg.authenticate() bearer-token
pattern proven in the Phase 5 spike (app.py Test 3) -- not
WorkspaceClient().serving_endpoints.get_open_ai_client(), which
doesn't exist.
"""

import json
import os

from databricks.sdk.core import Config
from openai import OpenAI

from lib import lakebase, lakehouse
from lib.vector_search import search_player_news as _vs_search_player_news

AGENT_MODEL_DEFAULT = "databricks-meta-llama-3-3-70b-instruct"

_client = None
_cfg = None


def _get_client():
    global _client, _cfg
    if _client is None:
        _cfg = Config()
        auth_headers = _cfg.authenticate()
        bearer_token = auth_headers["Authorization"].split(" ", 1)[1]
        _client = OpenAI(api_key=bearer_token, base_url=f"{_cfg.host}/serving-endpoints")
    return _client


# ---- Tool 1: same fuzzy-match / name-collision-surfacing behavior as
# the notebook, now backed by a SQL warehouse query instead of
# spark.table(...).filter(...). -------------------------------------

def get_player_form_profile(player_name_search: str, max_matches: int = 3) -> dict:
    search = player_name_search.strip().lower()
    if not search:
        return {"found": False, "query": player_name_search, "matches": []}

    like = f"%{search}%"
    bat_df = lakehouse.run_query(
        "SELECT * FROM cricsavant.gold.batter_profile WHERE lower(player_name) LIKE %s LIMIT %s",
        (like, max_matches),
    )
    bowl_df = lakehouse.run_query(
        "SELECT * FROM cricsavant.gold.bowler_profile WHERE lower(player_name) LIKE %s LIMIT %s",
        (like, max_matches),
    )

    matches, key_to_entry = [], {}
    for _, row in bat_df.iterrows():
        d = row.to_dict()
        key = d.get("batter_key")
        entry = {"player_key": key, "player_name": d.get("player_name"), "batting": d}
        matches.append(entry)
        key_to_entry[key] = entry
    for _, row in bowl_df.iterrows():
        d = row.to_dict()
        key = d.get("bowler_key")
        if key in key_to_entry:
            key_to_entry[key]["bowling"] = d
        else:
            entry = {"player_key": key, "player_name": d.get("player_name"), "bowling": d}
            matches.append(entry)
            key_to_entry[key] = entry

    if not matches:
        return {"found": False, "query": player_name_search, "matches": []}

    return {
        "found": True,
        "query": player_name_search,
        "match_count": len(matches),
        "note": (
            "More than one match means a genuine name collision or an ambiguous partial "
            "match -- ask the user to clarify which player before treating stats as a "
            "single player's."
        ) if len(matches) > 1 else None,
        "matches": matches,
    }


def search_player_news(query: str, player_name: str = None, num_results: int = 5) -> dict:
    return _vs_search_player_news(query, player_name, num_results)


def get_franchise_status(franchise_name: str) -> dict:
    return lakebase.get_franchise_status(franchise_name, log=True)


def execute_player_bid(franchise_name: str, player_name: str, price_cr: float) -> dict:
    return lakebase.execute_player_bid(franchise_name, player_name, price_cr)


_TOOL_FUNCTIONS = {
    "get_player_form_profile": get_player_form_profile,
    "search_player_news": search_player_news,
    "get_franchise_status": get_franchise_status,
    "execute_player_bid": execute_player_bid,
}

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
6. Keep answers concise (2-5 sentences unless the user asks for detail) and grounded strictly in what the tools returned.
"""


def run_agent(user_message: str, messages: list = None, max_turns: int = 6):
    """Runs one user turn through the tool-calling loop.

    Returns (answer, updated_messages, trace) -- trace is a list of
    {tool, args, result} dicts for every tool call made this turn, so
    the UI can render a transparency panel showing exactly what the
    agent looked up before answering.
    """
    client = _get_client()
    model = os.environ.get("CHAT_MODEL_ENDPOINT", AGENT_MODEL_DEFAULT)

    if messages is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": user_message})
    trace = []

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )
        choice = response.choices[0]
        messages.append(choice.message.model_dump(exclude_none=True))

        if not choice.message.tool_calls:
            return choice.message.content, messages, trace

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            fn = _TOOL_FUNCTIONS.get(fn_name)
            try:
                fn_args = json.loads(tool_call.function.arguments)
                result = fn(**fn_args) if fn else {"error": f"Unknown tool '{fn_name}'"}
            except Exception as e:
                result = {"error": str(e)[:300]}
            trace.append({"tool": fn_name, "args": fn_args if fn else {}, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })

    return "Reached the tool-call turn limit without a final answer -- something's looping.", messages, trace

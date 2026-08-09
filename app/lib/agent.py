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

    bat_df, bowl_df = lakehouse.search_players(search, max_matches=max_matches)

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


# ---- Tool 5 (retrieval): venue-aware retain/release signal. ----
#
# Real current roster (seeded from the actual, played-out 2026 IPL
# season -- notebooks/014_seed_real_squads.py) joined with each
# player's recent cross-format form AND their record specifically at
# THIS franchise's real home venue. Deliberately returns only
# structured real numbers -- no canned "retain" / "release" verdict
# computed here. The judgment call is left to the model, same as
# every other tool: it reasons from what's actually returned, cites
# the real figures, and the grounding rules below apply to this tool
# exactly like the other four.

def get_squad_retention_analysis(franchise_name: str) -> dict:
    status = lakebase.get_franchise_status(franchise_name, log=False)
    if not status["found"]:
        return {"found": False, "query": franchise_name}

    home_venue = lakebase.get_home_venue(franchise_name)
    batter_df = lakehouse.get_batter_profiles()
    bowler_df = lakehouse.get_bowler_profiles()

    players = []
    for p in status["roster"]:
        name = p["player_name"]
        bat_row = lakehouse.match_gold_row(name, batter_df)
        bowl_row = lakehouse.match_gold_row(name, bowler_df)
        venue_bat, venue_bowl = lakehouse.venue_form_for_player(name, franchise_name)

        entry = {
            "player_name": name, "role": p.get("role"), "is_overseas": p.get("is_overseas"),
            "recent_form": None, "home_venue_form": None,
        }
        # Report BOTH disciplines when both exist, not just whichever the
        # code checked first. A previous version picked bat_row over
        # bowl_row unconditionally, which meant a specialist bowler with
        # a handful of tail-end deliveries faced got labeled purely by a
        # meaningless batting strike rate -- their actual bowling economy
        # (the number that matters for a retain/release call) never
        # reached the model at all.
        recent_form = {}
        if bat_row is not None:
            b = bat_row.to_dict()
            recent_form["batting"] = {
                "recent_innings": b.get("recent_innings"),
                "recent_strike_rate": b.get("recent_strike_rate"), "recent_average": b.get("recent_average"),
            }
        if bowl_row is not None:
            b = bowl_row.to_dict()
            recent_form["bowling"] = {
                "recent_innings": b.get("recent_innings"),
                "recent_economy": b.get("recent_economy"), "recent_wickets": b.get("recent_wickets"),
            }
        entry["recent_form"] = recent_form or None

        home_venue_form = {}
        if venue_bat:
            home_venue_form["batting"] = {
                "innings": venue_bat.get("innings"),
                "strike_rate": venue_bat.get("strike_rate"), "average": venue_bat.get("average"),
            }
        if venue_bowl:
            home_venue_form["bowling"] = {
                "innings": venue_bowl.get("innings"),
                "economy": venue_bowl.get("economy"), "wickets": venue_bowl.get("wickets"),
            }
        entry["home_venue_form"] = home_venue_form or None
        players.append(entry)

    result = {
        "found": True,
        "franchise": franchise_name,
        "home_venue": home_venue,
        "squad_size": len(players),
        "purse_remaining_cr": status["franchise"].get("purse_remaining_cr"),
        "note": (
            "recent_form is ~18-month cross-format T20 form (all venues, regressed for sample "
            "size). home_venue_form is specifically this player's record at the franchise's "
            "real home ground (min. 60 balls faced/bowled there to qualify) -- null means "
            "either they haven't played enough there to qualify, or there's no Cricsheet match "
            "history for them at all (common for very new/uncapped signings). A player with "
            "strong overall recent form but weak or absent home-venue form is a genuine signal "
            "worth weighing, not a data error -- and the reverse (thin overall sample, strong "
            "home form) is equally real."
        ),
        "players": players,
    }
    lakebase.log_agent_tool_call(
        "get_squad_retention_analysis", "franchise_roster", status["franchise"].get("franchise_id"),
        {"franchise_name": franchise_name, "squad_size": len(players)}, "found",
    )
    return result


_TOOL_FUNCTIONS = {
    "get_player_form_profile": get_player_form_profile,
    "search_player_news": search_player_news,
    "get_franchise_status": get_franchise_status,
    "execute_player_bid": execute_player_bid,
    "get_squad_retention_analysis": get_squad_retention_analysis,
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
    {
        "type": "function",
        "function": {
            "name": "get_squad_retention_analysis",
            "description": (
                "Get a franchise's REAL current squad (seeded from the actual 2026 IPL season) "
                "with each player's recent cross-format form AND their record specifically at "
                "this franchise's real home venue. Use this when asked about retain/release "
                "decisions, squad gaps, who's out of form, or who fits/doesn't fit the home "
                "conditions -- ahead of the real IPL 2027 auction. Returns raw figures only, "
                "not a verdict -- form your own retain/release read from the numbers and say so "
                "explicitly when data is missing for a player rather than assuming they're weak."
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
]

SYSTEM_PROMPT = """You are CricSavant AI, an auction-companion assistant for an IPL fantasy-franchise auction app.

GROUNDING RULES (never violate these):
1. Never state a specific statistic, price, or franchise status from memory or estimation -- always call the relevant tool first.
2. If get_player_form_profile returns more than one match, that means a genuine name collision or ambiguity (there can be two real players with similar names). Ask the user to clarify which player they mean rather than picking one yourself.
3. When you use information from search_player_news, always include the source URL.
4. execute_player_bid is a real write action with real consequences for a franchise's purse. Only call it when the user has clearly specified a franchise, a player, and a price and asked you to place that bid -- do not call it speculatively or "to see what happens".
5. If a tool call fails, returns found=False, or a bid is blocked, say so plainly and explain why using the tool's own reason -- never fill the gap with a guess.
6. For retain/release or squad-gap questions, use get_squad_retention_analysis. recent_form and home_venue_form can each contain a "batting" block, a "bowling" block, or both (all-rounders) -- weigh the block that matches the player's actual role (a bowler's economy/wickets matter more than a few tail-end deliveries faced) rather than defaulting to whichever appears first. When a block is missing/null, say so explicitly ("no qualifying home-venue sample") rather than treating it as evidence they're weak there. A retain/release read is your judgment call to make and explain, grounded in the real figures -- the tool deliberately doesn't hand you a pre-computed verdict.
7. Keep answers concise (2-5 sentences unless the user asks for detail) and grounded strictly in what the tools returned.
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

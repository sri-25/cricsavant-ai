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

# Switched from Llama 3.3 70B by user decision after its strategy
# answers came back shallow. Claude Sonnet isn't offered on Free
# Edition's FMAPI (confirmed from the workspace's own endpoint list),
# so gpt-oss-120b -- OpenAI's open-weight reasoning model, the
# strongest tool-caller Free Edition serves -- is the pick. Multi-step
# reasoning over 25-player squads + venue splits + purse math is
# exactly where the model gap vs Llama 3.3 shows. The live endpoint
# comes from the CHAT_MODEL_ENDPOINT app resource (App Edit screen);
# this is only the fallback default.
AGENT_MODEL_DEFAULT = "databricks-gpt-oss-120b"

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


# ---- Auction targets: who's actually available + in what form. ----

def get_auction_targets(role: str = None, overseas: bool = None, max_results: int = 12) -> dict:
    """Players in the current auction pool NOT already on any roster,
    joined with their real recent form -- the raw material for "who
    should we sign" recommendations. Filter by role and overseas
    status; returns real numbers only, no pre-computed verdicts.
    """
    pool = lakebase.list_unowned_players()
    if pool.empty:
        return {"found": False, "note": "No unowned players left in the auction pool."}

    if role:
        pool = pool[pool["role"].str.lower() == role.strip().lower()]
    if overseas is not None:
        pool = pool[pool["is_overseas"] == overseas]
    if pool.empty:
        return {"found": False, "note": f"No available players match role={role}, overseas={overseas}."}

    batter_df = lakehouse.get_batter_profiles()
    bowler_df = lakehouse.get_bowler_profiles()

    candidates = []
    for _, p in pool.iterrows():
        entry = {
            "player_name": p["player_name"], "role": p["role"], "country": p["country"],
            "age": p["age"], "is_overseas": bool(p["is_overseas"]),
            "capped_status": p["capped_status"],
            "base_price_cr": float(p["base_price_lakh"]) / 100.0 if p["base_price_lakh"] is not None else None,
            "recent_batting": None, "recent_bowling": None,
        }
        bat = lakehouse.match_gold_row(p["player_name"], batter_df)
        bowl = lakehouse.match_gold_row(p["player_name"], bowler_df)
        if bat is not None:
            b = bat.to_dict()
            entry["recent_batting"] = {
                "innings": b.get("recent_innings"), "strike_rate": b.get("recent_strike_rate"),
                "average": b.get("recent_average"),
            }
        if bowl is not None:
            b = bowl.to_dict()
            entry["recent_bowling"] = {
                "innings": b.get("recent_innings"), "economy": b.get("recent_economy"),
                "wickets": b.get("recent_wickets"), "bowler_type": b.get("bowler_type"),
            }
        candidates.append(entry)

    # Players with real form data first -- an uncapped unknown with no
    # Cricsheet history is still listed, but after measurable options.
    candidates.sort(key=lambda c: (c["recent_batting"] is None and c["recent_bowling"] is None))
    candidates = candidates[: max(1, min(int(max_results), 25))]

    lakebase.log_agent_tool_call(
        "get_auction_targets", "player_pool", None,
        {"role": role, "overseas": overseas, "returned": len(candidates)}, "found",
    )
    return {
        "found": True, "candidate_count": len(candidates),
        "note": (
            "All candidates are in the current auction pool and not on any roster. "
            "recent_batting/recent_bowling are ~18-month cross-format T20 form; null means no "
            "qualifying Cricsheet sample (common for uncapped players), which is a risk signal "
            "to state, not proof of weakness. Base prices are real BCCI shortlist figures."
        ),
        "candidates": candidates,
    }


# ---- Strategy notes: the agent's WRITE tool (replaces bids). ------

def save_strategy_note(franchise_name: str, note_type: str, content: str) -> dict:
    result = lakebase.save_strategy_note(franchise_name, note_type, content, created_by="agent")
    return result


def list_strategy_notes(franchise_name: str = None) -> dict:
    df = lakebase.list_strategy_notes(franchise_name)
    notes = df.to_dict("records") if not df.empty else []
    for n in notes:
        n["created_at"] = str(n.get("created_at"))
    return {"found": bool(notes), "count": len(notes), "notes": notes}


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
    "get_squad_retention_analysis": get_squad_retention_analysis,
    "get_auction_targets": get_auction_targets,
    "save_strategy_note": save_strategy_note,
    "list_strategy_notes": list_strategy_notes,
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
            "name": "get_auction_targets",
            "description": (
                "List players available in the current auction pool (not on any roster) with "
                "their real recent form and base prices. Use when recommending signings, "
                "filling squad gaps, or building an auction shortlist. Filter by role and/or "
                "overseas status to target a specific need."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "Optional: 'batter', 'bowler', 'all-rounder', or 'wicketkeeper'."},
                    "overseas": {"type": "boolean", "description": "Optional: true = overseas players only, false = domestic only."},
                    "max_results": {"type": "integer", "description": "Max candidates to return (default 12)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_strategy_note",
            "description": (
                "Save a strategy artifact (retention plan, auction-target shortlist, simulated "
                "playing XI, scouting note) to the franchise's permanent strategy notebook. "
                "This is a WRITE action -- call it when the user asks to save/keep a plan, or "
                "after producing a substantial recommendation the user confirms they want kept. "
                "note_type must be one of: retention_plan, auction_targets, playing_xi, "
                "scouting, general."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "franchise_name": {"type": "string"},
                    "note_type": {"type": "string", "enum": ["retention_plan", "auction_targets", "playing_xi", "scouting", "general"]},
                    "content": {"type": "string", "description": "The full note text to save."},
                },
                "required": ["franchise_name", "note_type", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_strategy_notes",
            "description": "List previously saved strategy notes, optionally filtered to one franchise. Use when the user asks what plans/notes already exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "franchise_name": {"type": "string", "description": "Optional franchise filter."}
                },
                "required": [],
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

SYSTEM_PROMPT = """You are CricSavant AI, a franchise strategy analyst for IPL team management. Your job is to help each franchise take control of their strategy: whom to retain or release, whom to target at the next auction, what their strongest playing XI looks like, and where their squad is weak -- always grounded in the real data your tools return.

GROUNDING RULES (never violate these):
1. Never state a specific statistic, price, or franchise status from memory or estimation -- always call the relevant tool first.
2. If get_player_form_profile returns more than one match, that means a genuine name collision or ambiguity. Ask the user to clarify which player they mean rather than picking one yourself.
3. When you use information from search_player_news, always include the source URL.
4. If a tool call fails or returns found=False, say so plainly using the tool's own reason -- never fill the gap with a guess.
5. For retain/release or squad-gap questions, use get_squad_retention_analysis. recent_form and home_venue_form can each contain a "batting" block, a "bowling" block, or both (all-rounders) -- weigh the block matching the player's actual role. When a block is null, say "no qualifying sample" rather than treating it as weakness.
6. For signing recommendations, use get_auction_targets and respect the franchise's real constraints from get_franchise_status: purse remaining, squad cap, overseas cap. Never recommend a signing the purse can't afford; state the base price and remaining purse when you recommend.
7. save_strategy_note is a WRITE action -- use it when the user asks to save a plan, choosing the right note_type. Confirm what was saved.

STRATEGY TASKS (how to do the deep work):
- RETENTION PLAN: call get_squad_retention_analysis, group the squad into clear retain / release / borderline lists with the actual numbers beside each name, and tie releases to purse freed and gaps opened.
- AUCTION PLAN: first understand the squad's gaps (retention analysis), then get_auction_targets filtered to those gaps, then recommend specific names with base price vs purse math.
- PLAYING XI SIMULATION: from the real roster (get_squad_retention_analysis), pick an XI: openers, middle order, finishers, wicketkeeper, 4-5 bowling options, max 4 overseas (that's the real match-day rule -- distinct from the squad's overseas cap). Name an Impact Player substitute (typically a specialist batter swapped for a bowler or vice versa depending on innings). Justify each slot with the player's actual numbers, use home_venue_form for conditions-fit, and flag any slot where data is thin instead of bluffing confidence.
- Format strategy answers with short headers and bullet lists with numbers; keep casual questions to 2-4 sentences.
"""


def run_agent(user_message: str, messages: list = None, max_turns: int = 8):
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
            max_tokens=4000,  # explicit for FMAPI; gpt-oss spends some of this on reasoning tokens, XI sims need room
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

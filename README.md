# CricSavant AI — Cricket Franchise Auction War Room

Capstone project. An AI-assisted cricket auction "war room": stand up your own
franchise, scout players using cross-format form data built by a Spark pipeline,
pull injury/news context via Tavily, and bid through an agent that can look things
up and take real, rule-validated write actions — with every write flowing through
a Lakebase change log into Delta for analytics.

**This file is the current source of truth for what's actually built.**
`docs/PROJECT_PLAN.md` is the original planning doc — useful for the reasoning
behind early decisions, but several specifics in it (table names, tool signatures)
were superseded during the build and never updated there. If the two disagree,
this file is correct.

## Status

| Phase | What | Status |
| --- | --- | --- |
| 0 | Environment validation spike | Done |
| 1 | Spark medallion pipeline (bronze/silver/gold, cross-format) | Done |
| 2 | Tavily ingestion + embeddings + Vector Search | Done |
| 3 | Lakebase schema (franchises/rosters/rules) + change-log sync | Done |
| 4 | AI agent — 4 tools + grounding guardrails | Done |
| 5 | Databricks App frontend (4 tabs + chat drawer) | In progress — integration spike built, not yet deployed/verified |
| 6 | End-to-end test, polish, demo prep | Not started |

## Run order — notebooks

Run top to bottom within each file. Files marked **deprecated** should not be run.

| # | File | Purpose | Status |
| --- | --- | --- | --- |
| — | `003_seed_competition_config.py` | Seeds `cricsavant.raw.competition_config` (which competitions to ingest) | **Run once** — 004 depends on this table existing |
| 1 | `004_bronze_ingest_all_competitions.py` | Real bronze ingest, all 9 competitions, writes `cricsavant.raw.bronze_matches` | Run and verified (9,876 matches) |
| 2 | `005_silver_matches_and_deliveries.py` | Bronze → `cricsavant.silver.matches` + `cricsavant.silver.deliveries`, resolves player identity | Run and verified (100% batter_id coverage) |
| 3 | `006_gold_player_kpis.py` | Silver → 15 gold KPI tables (career/recent form, phase splits, situational, all-rounder) | Run and verified |
| 4 | `007_gold_player_profiles.py` | Assembles `gold.batter_profile` / `gold.bowler_profile` — one row per player, everything folded in | Run and verified (1,495 / 1,420 rows) |
| — | `setup_secrets.py` | Git-safe one-time setup: stores the Tavily API key as a Databricks secret | Run once |
| 5 | `008_tavily_player_news_ingest.py` | Pulls news articles for a two-lens player shortlist, writes `cricsavant.raw.player_news_articles` | Run and verified |
| 6 | `009_vector_search_index.py` | Builds the Delta Sync Vector Search index over those articles | Run and verified (index ONLINE) |
| — | `011_setup_lakebase_app_credential.py` | Git-safe setup: creates the `cricsavant_app` Postgres role's password as a secret, verifies the connection | Run once |
| 7 | `012_agent_tools.py` | The agent's 4 tools (standalone, with test cells) | Run and verified — all 4 tools + guardrails working |
| 8 | `013_agent_loop.py` | Same 4 tools + LLM tool-calling loop (what the app will actually run) | Run and verified — all 5 grounding-guardrail tests passing |

`notebooks/deprecated/` holds two superseded early attempts (`002_bronze_ingest_ipl.py`,
the IPL-only walking skeleton; `010_lakebase_schema_setup.py`, an early Lakebase schema
draft replaced by `sql/001-005`) — kept for history, not part of the run sequence.

## Run order — SQL (Lakebase SQL Editor)

| # | File | Purpose | Status |
| --- | --- | --- | --- |
| 1 | `sql/001_lakebase_schema.sql` | Creates `franchises`, `franchise_roster`, `auction_rules`, `change_log` | Run |
| 2 | `sql/002_seed_auction_rules.sql` | Seeds the real, cited Dec 2025 BCCI mini-auction rules | Run |
| 3 | `sql/003_seed_player_pool.sql` | Seeds the real 369-player IPL 2026 auction shortlist | Run |
| 4 | `sql/004_add_format_rules_context.sql` | Adds Playing XI overseas cap / Impact Player / capped-status notes to `auction_rules` | Run |
| 5 | `sql/005_seed_franchises.sql` | Seeds the 10 real IPL franchises at the full purse cap | Run (confirmed: 10 rows) |
| 6 | `sql/006_create_app_role.sql` | Creates the `cricsavant_app` Postgres role (least-privilege, password-based) | Run — requires "Enable Postgres Native Role Login" toggled on first |

## Current real schema (what actually exists right now)

**Lakehouse (Unity Catalog, `cricsavant` catalog):**
- `raw.bronze_matches`, `raw.competition_config`, `raw.player_news_articles`, `raw.player_news_articles_index` (Vector Search)
- `silver.matches`, `silver.deliveries`
- `gold.batting_innings`, `gold.bowling_innings`, `gold.batting_form_career`, `gold.bowling_form_career`, `gold.batting_form_t20_leagues`, `gold.bowling_form_t20_leagues`, `gold.batting_form_recent`, `gold.bowling_form_recent`, `gold.batting_form_by_venue`, `gold.bowling_form_by_venue`, `gold.batting_phase_splits`, `gold.bowling_phase_splits`, `gold.batting_situational_profile`, `gold.bowling_situational_profile`, `gold.allrounder_profile`, `gold.batter_profile`, `gold.bowler_profile`
- `ops.lb_change_log_history` (synced from Lakebase's `change_log` via `001_sync_change_log_to_delta.py`), `ops.sync_watermark`

**Lakebase (Postgres, real table names — NOT what `docs/PROJECT_PLAN.md` Section 2 says):**
- `franchises` (10 rows, real IPL teams), `franchise_roster`, `auction_rules` (1 current row, real BCCI-cited), `player_pool` (369 rows, real BCCI-cited), `change_log`
- Roles: your own admin identity, plus `cricsavant_app` (password-based, least-privilege: SELECT on `franchises`/`auction_rules`/`player_pool`, SELECT+INSERT+UPDATE on `franchise_roster`, SELECT+INSERT on `change_log`, UPDATE on `franchises.purse_remaining_cr` only)

**The agent's 4 tools (in `012_agent_tools.py` / `013_agent_loop.py` — real signatures, differ from `docs/PROJECT_PLAN.md` Section 8):**
- `get_player_form_profile(player_name_search, max_matches=3)` — fuzzy name match, returns ALL matches (surfaces name collisions instead of guessing)
- `search_player_news(query, player_name=None, num_results=5)`
- `get_franchise_status(franchise_name)` — by name, not id
- `execute_player_bid(franchise_name, player_name, price_cr)` — single-call validate-then-commit-or-reject (not the two-phase dry-run/confirm design originally sketched in the plan doc — same safety guarantee: nothing invalid ever gets written, just via one call instead of two)

## Folder layout

- `docs/` — original plan (see caveat above).
- `notebooks/` — Spark pipeline, Tavily/embeddings, Lakebase credential setup, agent tools.
  `notebooks/deprecated/` — superseded early attempts, kept for history, not run.
- `sql/` — Lakebase DDL and seed data, run via the Lakebase SQL Editor.
- `app/` — Databricks App (Streamlit) frontend. Integration spike built, not yet deployed.

## Requirement → component map

| Capstone requirement | Component | Status |
| --- | --- | --- |
| Spark data pipeline | `004`→`007`, bronze/silver/gold on 9 competitions, 2008-2025 | Done |
| Third-party API | Tavily via `008` | Done |
| Unstructured data processing | Tavily articles → embeddings → Vector Search (`009`) | Done |
| Databricks App w/ frontend | `app/`, 4 tabs + chat drawer | In progress |
| AI agent (retrieve + write) | `012`/`013`, 4 tools, grounding guardrails | Done |
| Lakebase CDF → Delta analytics | `change_log` table + `001_sync_change_log_to_delta.py` | Done (mechanism proven, not yet scheduled as a recurring Job) |

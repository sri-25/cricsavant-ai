# CricSavant AI — Setup From Scratch

This is a linear runbook for standing this project up in a fresh Databricks Free
Edition workspace. It exists because several steps here are not obvious from just
reading the code — they involve Databricks UI actions, multi-step widget/restart
sequences, or one-time toggles that were only discovered by hitting the error first.
Every one of those is called out explicitly below, not left for you to rediscover.

See `README.md` for what each file does and the current schema. This file is only
about the order and the gotchas.

## 0. Prerequisites

- A Databricks Free Edition workspace.
- A Tavily API key (free tier, no card required — [tavily.com](https://tavily.com)).
- This repo connected as a Databricks **Git folder** (Workspace → Git folders →
  Add repo → paste this repo's URL). That gives you the `notebooks/`, `sql/`, and
  `app/` folders inside Databricks, matching this repo exactly.

## 1. Spark pipeline (`notebooks/`)

Run in this exact order. Each is a normal "Run All" unless noted otherwise.

1. `003_seed_competition_config.py` — seeds the competition list. Must run before 004.
2. `004_bronze_ingest_all_competitions.py` — downloads and lands ~9,800 matches
   across 9 competitions. Takes a few minutes. **`FORCE_FULL_REBUILD`** near the top
   is currently `True`; that's a one-time migration flag from when the player-identity
   column was added. If you're running this completely fresh, it's harmless either
   way, but leave it as `True` for now.
3. `005_silver_matches_and_deliveries.py` — no gotchas, straight run.
4. `006_gold_player_kpis.py` — no gotchas, straight run. Takes a minute or two
   (full ball-by-ball scan).
5. `007_gold_player_profiles.py` — no gotchas, straight run.

`notebooks/deprecated/` is NOT part of this sequence — superseded early attempts
kept only for reference. Don't run anything in that folder.

## 2. Tavily + Vector Search (`notebooks/`)

1. **`setup_secrets.py`** — this one needs two runs, not one:
   - Run the first cell only. A text widget labeled "Tavily API Key" appears at the
     top of the notebook.
   - Click into that widget and type your real Tavily key.
   - Now run the rest of the notebook (or Run All again). If you Run All *before*
     filling the widget, you'll hit `ValueError: Enter your Tavily API key...` —
     that's expected, not a bug; just fill the widget and run again.
2. `008_tavily_player_news_ingest.py` — straight run. Has its own
   `%pip install` + restart cell near the top; let that finish before continuing
   (Databricks will prompt you to re-run cells below it after the restart if you
   run the whole notebook at once — that's normal for any notebook with a restart
   cell, not specific to this one).
3. `009_vector_search_index.py` — straight run. The last cell polls automatically
   until the index is ready (up to 10 minutes) — just let it run, no need to
   babysit or re-run anything.

## 3. Lakebase schema (`sql/`, via the Lakebase SQL Editor — NOT Databricks notebooks)

Files in `sql/` are not notebooks. Open Lakebase's own SQL Editor (from your
Lakebase project) and paste/run each file's contents directly, in order:

1. `001_lakebase_schema.sql`
2. `002_seed_auction_rules.sql`
3. `003_seed_player_pool.sql`
4. `004_add_format_rules_context.sql`
5. `005_seed_franchises.sql`
6. **`006_create_app_role.sql`** — has a required prerequisite not captured in any
   file: before running this, go to your Lakebase instance's page → **Edit** →
   turn on **Enable Postgres Native Role Login** → **Save**. Password-based Postgres
   roles are off by default; this SQL will error with a permissions issue until
   that's toggled on. Also: replace `REPLACE_ME_STRONG_PASSWORD` in the editor with
   a real generated password before running — don't save that edit back to the file.
7. `007_add_home_venue.sql` — adds `franchises.home_venue` + seeds the 10 real
   current home grounds. Run before step 5's `014_seed_real_squads.py` below.

## 4. Lakebase app credential (`notebooks/`)

`011_setup_lakebase_app_credential.py` — same two-run pattern as `setup_secrets.py`:
run the first cell, fill in the "Lakebase App Password" widget with the *same*
password you used in `sql/006` above, then run the rest. It also needs
`LAKEBASE_HOST` filled in twice in the file (once before, once after the
`%pip install` + restart cell — widget/variable state doesn't survive a restart,
so it has to be re-set). The last cell verifies the connection and deliberately
tries an action it shouldn't be allowed to do (drop a table) — seeing that fail is
the notebook working correctly, not an error to fix.

## 5. Agent tools (`notebooks/`)

1. `012_agent_tools.py` — straight run, includes test cells for each of the 4 tools.
2. `013_agent_loop.py` — straight run, includes 5 test cells exercising the
   grounding guardrails (cited news, blocked bids, name-collision disambiguation).

Both have their own `%pip install databricks-vectorsearch pg8000 ... ` + restart
cell — same note as `008` above, this is normal, just let the restart finish.

3. `014_seed_real_squads.py` — seeds each franchise's REAL current (2026 season)
   roster (retained + Dec 2025 auction, cited from business-standard.com) and each
   team's real post-auction remaining purse, replacing the old "every team starts
   empty at the full cap" placeholder. Idempotent (safe to re-run). Prints a list
   of any players it couldn't match to real role data at the end — that's a
   review list, not a failure. Requires `sql/007_add_home_venue.sql` to have been
   run first. This is what makes the 5th agent tool
   (`get_squad_retention_analysis`) and the My Franchise tab's "Squad & Venue Fit"
   panel meaningful instead of empty.

## 6. Databricks App (`app/`)

Deployed via "Deploy from a Git repository" (see `README.md` status table). When
setting this up: Compute → Apps → Create App → point the source at this repo's
`app/` folder → add the 3 resources (SQL warehouse, the
`cricsavant/lakebase_app_password` secret, the **`databricks-gpt-oss-120b`**
serving endpoint — chosen over Llama 3.3 70B for materially stronger multi-step
tool-calling; Claude endpoints aren't offered on Free Edition) with the exact
resource keys already set in `app/app.yaml` → Deploy. Also run
`sql/008_strategy_notes.sql` (agent write surface) before first use.

The app's service principal (shown on the App's Overview page, e.g. `app-xxxxx
<app-name>`) needs these Unity Catalog / Vector Search grants — all 4 tabs and
the chat agent touch different parts of the Lakehouse now, not just `gold`:

| Grant | Where | Why |
| --- | --- | --- |
| `USE CATALOG`, `USE SCHEMA` | Catalog Explorer → `cricsavant` (catalog level) | Prerequisite for any nested SELECT to take effect |
| `SELECT` | Catalog Explorer → `cricsavant.gold` schema | Player Explorer / Auction Console profile lookups |
| `USE SCHEMA`, `SELECT` | Catalog Explorer → `cricsavant.raw` schema | `search_player_news` queries the `raw.player_news_articles_index` Vector Search index |
| `USE SCHEMA`, `SELECT` | Catalog Explorer → `cricsavant.ops` schema | Analytics tab reads `ops.lb_change_log_history` |
| **Can Query** | Compute → Vector Search → `cricsavant_endpoint` → Permissions | Required separately from the UC grant above — the endpoint itself is a permissioned resource |

Missing any one of these produces the same `INSUFFICIENT_PERMISSIONS` error pattern
hit during the Phase 5 spike, just on a different schema/endpoint.

## Known gotchas, summarized

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ValueError: Enter your ... key/password in the widget` | Ran the whole notebook before filling the widget | Fill the widget, run again — expected, not a bug |
| `ModuleNotFoundError` right after a `%pip install` cell | Python wasn't restarted yet, or cells below weren't re-run after restart | Let `dbutils.library.restartPython()` finish, then run the remaining cells |
| `INVALID_ARRAY_INDEX` / similar Spark indexing errors | Not applicable anymore — already fixed in the current code (`get()` instead of `element_at()` on arrays) | N/A, just documenting why you won't see it |
| `permission denied for table ...` on a Lakebase write | The `cricsavant_app` role's grants (`sql/006`) don't cover that table/column | Check `sql/006` covers what you're trying to do; it's deliberately least-privilege |
| `Compute error — App creation failed unexpectedly` on Free Edition | Known transient regional provisioning issue (seen Nov 2025, self-resolved) | Retry later; not a code problem |
| Postgres role creation fails on `sql/006` | "Enable Postgres Native Role Login" not toggled on yet | Toggle it on in the instance's Edit page first |

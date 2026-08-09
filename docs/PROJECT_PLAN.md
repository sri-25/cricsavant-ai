# CricSavant AI — Project Plan

Last updated: 2026-08-07. Timeline: **2 days.**

> **This document is the original plan, kept for the reasoning behind early
> decisions. Several specifics below were superseded during the actual build
> and were never edited back into this file — most importantly the Lakebase
> table names in Section 2 (`team_portfolios`/`player_investments`/
> `bcci_auction_rules`/`agent_tool_call_log`) and the tool signatures in
> Section 8, including `execute_player_bid`'s two-phase dry-run/confirm
> design. None of those reflect what's actually running. For the current,
> accurate schema and tool signatures, see `README.md` in the project root —
> that file is kept up to date; this one is not.

## 0. Working model

Claude acts as developer, architect, and UI/UX engineer — designing the system,
writing the actual code/notebooks/SQL/app, and explaining the reasoning behind every
piece. Sri runs it: clicking through the Databricks/Lakebase UI, pasting code in,
executing — that's deliberate, it's how the learning and the "built this myself"
feeling actually happen. When something breaks, a screenshot or pasted error is all
that's needed to debug together and keep moving. Piece by piece, Sri approves before
each step. Time pressure is handled by tight, concrete steps and fast turnaround on
errors — not by silently trimming scope: anywhere a real trade-off exists, it gets
surfaced and decided together, not pre-cut on Claude's judgment alone. Where earlier
sections of this doc say "kept lean" for time reasons, treat that as superseded —
depth is back on the table by default; the only real ceiling is genuine platform
limits (Free Edition quotas, what's technically possible in the time available), not
a self-imposed one.

## 1. Decisions locked in this round

- **Theme stays IPL / cricket.** Project name: CricSavant AI.
- **Workspace: Databricks Free Edition (personal).** Confirmed against official docs
  (docs.databricks.com/aws/en/getting-started/free-edition-limitations, updated Jul 20
  2026) — exact limits that shape the build:
  - Lakebase: **1 project**, scale-to-zero compute. Enough for this project (one
    Postgres schema), but no room for a second project if we mess one up.
  - Model serving endpoints: allowed, but capped count, no GPU serving, no
    provisioned throughput.
  - AI Search: **1 endpoint, 1 search unit, Direct Vector Access not supported** —
    our vector index must be a Delta-Sync index (embed to a Delta table, sync from
    that), which is what we planned anyway.
  - Apps: up to 3, but **auto-stop 24h after deploy/update** — restart before any
    demo if there's been a gap.
  - Jobs: 5 concurrent tasks max. Lakeflow pipelines: 1 active pipeline per type.
  - Outbound internet restricted to a trusted-domain allowlist — worth checking
    Tavily's API host is reachable from a Free Edition notebook in Phase 0, not
    assumed.
- **One third-party API: Tavily, not Tavily + CricAPI/Sportmonks.** Tavily is a
  web-search API that crawls and extracts clean text from many underlying news sites
  in a single call — it already satisfies "extract from multiple sources," you don't
  need a second API for that. Free tier: 1,000 credits/month, no card required.
  **Accuracy boundary (hard rule, not a suggestion):** Tavily never backs a number the
  app treats as fact. Historical player/venue stats come from Cricsheet via the Spark
  pipeline; live auction state (budget, bids, rosters) lives in Lakebase under our own
  write-validated control. Tavily only powers `search_player_news` — qualitative
  context, rendered with source link + publish date in the UI so it reads as "reported
  by X," not an asserted fact. IPL 2026 already finished (~May), so in practice this
  tool is pre-auction form/injury context, not live scoring — flag if that's not the
  framing you want. A second, cricket-specific live-scores API (Sportmonks needs a
  paid tier for IPL coverage) is a stretch item only if Phase 0-5 finish early — not
  in the 2-day core path.
- **Spark pipeline: medallion (bronze/silver/gold), kept lean.** Full bronze/silver/gold
  as requested, but the gold layer ships with a small, defensible set of aggregates
  (player x venue impact, phase-wise economy/strike rate) rather than an open-ended
  feature set — depth of engineering matters less than the pipeline being real and the
  agent tool actually depending on its output.
- **Cricsheet data window: 2008-2025, and NOT IPL-only.** The 2026 season only just
  finished (~May); the IPL archive for it may still be incomplete. Historical corpus
  is 2008-2025 across formats — confirmed Cricsheet covers Tests, ODIs, T20Is, and
  ~25 domestic T20/first-class competitions (BBL, PSL, CPL, SA20, ILT20, County
  Championship, Sheffield Shield, etc.), refreshed regularly as matches complete.
  This is what "how a player is doing internationally and in domestic leagues" needs
  to be built from — no second data source required, just a wider bronze ingest.
  Note this is **batch-refreshed, not real-time in-match scoring** — if true live
  ball-by-ball tracking during an active match is actually wanted, that's a different,
  riskier build needing a paid live-scores API; flag if that's the intent.
- **Gold layer = cross-format player form profile, not just IPL venue stats.** Rolling
  recent-form (last 5/10 matches) plus career splits, broken out by format
  (Test/ODI/T20I/T20-league) and by venue, computed across every competition in scope
  above. Injuries and qualitative strengths/weaknesses are not in ball-by-ball data —
  those stay on the Tavily/news side.
- **Bring-your-own-franchise.** Lakebase schema is generalized: a `franchises` table
  (any franchise a user creates, with its own purse — not hardcoded to the 10 real
  IPL teams) and a `franchise_roster` table covering both an imported starting roster
  and auction acquisitions. Franchise creation / roster import is a direct app-form
  write to Lakebase, not routed through the AI agent — keeps the agent's write surface
  to one clear action (`execute_player_bid`) while still writing through Lakebase, so
  it still flows through CDF either way.
- **Agent: 4 tools** (grew from 3 — see Section 8 for why). Two structured retrieval
  flavors (historical stats, live franchise state), one unstructured/semantic
  retrieval, one write. Auction rules are injected as always-on system context rather
  than a callable tool, so the model can't "forget" to check them — see Section 6.
- **Frontend: Streamlit Databricks App, 4 tabs + persistent chat drawer** — see
  Section 9 for the full information architecture. Grew from 3 tabs because the
  "real-time hand app" framing needs a dedicated live-auction console and player
  explorer, not just a bidding form.

## 2. CDF: decided approach

**Native Lakebase CDF (option 1) is not available on this account.** Checked directly
— the workspace username menu has no Previews entry at all on Free Edition (screenshot
confirmed: only Settings, Privacy policy, Send feedback, Log out). This lines up with
Free Edition's documented administrative restrictions (no account console, enterprise
admin features gated). We are not pursuing a paid trial to unlock it — that needs a
credit card, risks billing after 14 days, and would mean rebuilding the catalog/schema
already created, for an unconfirmed payoff. Decision: skip it, build our own.

**Committed approach: application-layer change log + scheduled Spark JDBC sync.**
Better than the raw "logical replication" fallback originally sketched, because it
doesn't need WAL-level replication-slot privileges we haven't confirmed we have on a
managed instance — it only needs ordinary INSERT permission, which we definitely have.

1. One unified `change_log` table in Lakebase: `id, table_name, record_id, change_type,
   payload (jsonb), franchise_id, changed_at`. Every write path in our own app code
   (the `execute_player_bid` tool, franchise/roster onboarding forms) inserts one row
   here in the same transaction as the real write — so it can never drift out of sync,
   because we control every write path (no external actor writes to this database).
   This single table doubles as the "agent tool call" usage log the rubric calls out
   as an analytics example, so it's one mechanism serving two requirements.
2. A scheduled Databricks Job (well within the 5-concurrent-task Free Edition limit)
   runs every few minutes, reads `change_log` via `spark.read.jdbc` against Lakebase's
   standard Postgres connection endpoint (this is a fully supported, documented
   connection path — not a workaround), appends new rows past a watermark to a managed
   Delta table `main.cricsavant.lb_change_log_history`, mirroring the shape the native
   feature would have produced.
3. Analytics tab queries that Delta table exactly as it would have queried a native
   `lb_*_history` table — the downstream experience is identical.

This is still genuinely "Change Data Feed from Lakebase into a Delta table, used to
power analytics about your app" — it just captures changes at the application layer
instead of the WAL layer. Worth stating plainly in the submission write-up: this was a
deliberate engineering call made after confirming the native preview isn't reachable on
Free Edition, not something to gloss over. It also sidesteps a real risk the native
feature would have carried into a demo — depending on an undocumented-SLA preview
feature's internal batching (~15s) versus a mechanism we fully control end to end.

## 3. Two-day sequencing

**Day 1 AM — de-risk everything (Phase 0).**
Provision Unity Catalog schema, create a Lakebase project, attempt to enable CDF
preview, set `REPLICA IDENTITY FULL` on a throwaway test table and confirm a
`lb_test_history` Delta table actually appears. Get a Tavily API key and make one
real call. Deploy a "hello world" Streamlit Databricks App to confirm Apps works on
this account. Confirm a Model Serving embedding endpoint is reachable under quota.
None of this is the real app — it's a walking skeleton proving every requirement is
technically reachable before investing real build time.

**Day 1 PM — Phases 1 & 2 in parallel (pipeline + unstructured data).**
Cricsheet ingest -> bronze -> silver -> gold. Tavily pull -> embeddings -> Vector
Search index. These don't depend on each other, so they run side by side.

**Day 2 AM — Phases 3 & 4 (Lakebase write path + agent).**
Real Lakebase schema (`team_portfolios`, `player_investments`, `bcci_auction_rules`),
CDF turned on for real, then the 3 agent tools registered as Unity Catalog functions
and wired into an agent endpoint.

**Day 2 PM — Phase 5 & 6 (app + integration + submission prep).**
Streamlit app wired to real endpoints, one full smoke test of the whole loop (place a
bid through the agent -> Lakebase row changes -> CDF -> Delta -> dashboard updates),
UI pass, README/demo script for submission.

This sequencing is tight on purpose: every requirement gets touched end-to-end by
Day 1 lunchtime in skeleton form, so nothing critical is discovered broken on the
last afternoon.

## 4. Risk register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| ~~Lakebase CDF preview not self-enable-able on Free Edition~~ — confirmed blocked | Native CDF (option 1) unavailable | **Resolved and proven**: app-layer change_log + Spark JDBC sync (Section 2) tested end-to-end -- a manual test row written to Lakebase's change_log showed up in `cricsavant.ops.lb_change_log_history` after running notebooks/001_sync_change_log_to_delta.py. Mechanism works; scheduling it as a recurring Job is the only remaining step. |
| Scheduled sync job introduces lag (changes visible in Delta only every N minutes) | Analytics tab isn't instantaneous | Acceptable for this use case — set the schedule to a few minutes, mention the lag honestly in the demo rather than implying real-time |
| Tavily results treated as fact under demo/grading pressure | Wrong info presented as accurate in a "high stakes" project | Hard rule: Tavily only backs `search_player_news`, always rendered with source + date; never backs stats or auction numbers |
| Free Edition compute/serving quotas exhausted | Blocks pipeline runs or agent endpoint mid-build | Keep gold layer + embedding batch small; avoid re-running full historical ingest repeatedly |
| Databricks App auto-stops 24h after deploy | App looks "down" walking into a demo | Restart the app explicitly before any demo/review session |
| Cricsheet 2026 data incomplete | Broken ingest step | Cap historical corpus at 2025; treat 2026 as live-only via Tavily |
| Tavily free tier (1,000 credits/mo) exhausted during dev+demo | News tool goes empty mid-demo | Cache pulled articles in Delta immediately; agent tool reads cache first, live-calls only on cache miss |
| 2-day timeline vs. 6 non-trivial requirements | Something ships half-done | Walking-skeleton-first sequencing (Section 3); cut UI polish before cutting any rubric requirement |

## 6. What this app is actually for — framing check

You described this as a real-time hand app carried into an actual IPL auction. Important
scope clarification: BCCI's live auction system isn't something we can integrate with —
there's no public API for it. So "Buy" in this app means "commit to *my own* internal
record that my franchise won this player at this price," recorded and validated by us,
in parallel with the real auction happening in the room — a decision-support and
compliance-tracking companion, not a system that transacts with the real auction. Worth
confirming that's the framing you had in mind, since it changes what "accuracy" is
protecting: not the real auction outcome (we don't control that), but *your* franchise's
internal budget/rules integrity and the quality of the recommendation you get before you
raise your paddle.

## 7. Business questions this app answers

Every tool and screen traces back to one of these, asked by someone sitting at the
auction table with 30 seconds to decide:

- "Player X is up next — is he good for us, and what should we pay?" (form profile +
  news + our own roster gaps, synthesized into a recommended ceiling price)
- "Is this player actually fit / in form right now, or is the base price a trap?"
  (news-grounded check, not just career stats)
- "If I bid ₹Y crore on this player, does it break our purse, overseas cap, or squad
  rules?" (pre-commit validation, before the bid is real)
- "We have ₹12cr and 4 slots left — what should our priority order be?" (strategy
  planning across remaining purse + role gaps)
- "We already have 4 overseas pace bowlers — do we need another, or should we
  diversify?" (role/composition-aware reasoning over our own live roster)
- "What are the current BCCI rules — RTM cards, overseas cap, purse cap — so we don't
  plan around stale assumptions?" (rules grounding)
- "Looking back, did we overpay or get value across our squad?" (post-hoc analytics)

## 8. Tools, in detail

| Tool | Type | Reads/writes | Purpose |
| --- | --- | --- | --- |
| `get_player_form_profile(player, competition=None, venue=None)` | Structured retrieval | Gold Delta table (Spark pipeline) | Cross-format recent form + career splits + venue performance. Ground truth for any stat the agent states. |
| `search_player_news(query)` | Semantic/unstructured retrieval | Vector index over embedded Tavily articles | Injury status, recent form narrative, expert commentary — always returned with source + publish date, filtered to recent articles so stale news doesn't drive a bid. |
| `get_franchise_status(franchise_id)` | Structured retrieval | Lakebase (live OLTP read) | Purse remaining, current roster by role, overseas count, RTM cards used. This is what makes "should we bid on another overseas pacer" answerable — it's *our* state, not the player's. |
| `execute_player_bid(player, franchise, amount_cr, confirm=False)` | Write | Lakebase (OLTP write, rule-validated) | `confirm=False` (default) returns a dry-run compliance preview — resulting purse, overseas count, role balance — with no write. `confirm=True` re-validates server-side against current rules and franchise state (never trusts client-cached numbers) and commits. This is the "don't want teams to bid falsely" guardrail: bad bids get caught at preview time, not after the fact. |

**Auction rules are not a 5th tool.** They're injected into the agent's system context
every turn from a Lakebase `auction_rules` table (purse cap, squad size min/max,
overseas cap, RTM cards, retention slabs), so the model always knows current rules
without depending on remembering to call something. Rules are human-curated when BCCI
changes them, each entry stamped with `source_url` and `verified_at` — deliberately
*not* auto-updated by the agent from a web search, since misreading a rules article and
silently changing what counts as a legal bid is exactly the kind of mistake this project
can't afford. If you want a "check for rule changes" helper, that's a periodic search
run by us as maintainers, not an autonomous agent action.

**Grounding discipline ("very very accurately"), concretely:**
- System prompt requires: any recommendation or player-quality claim must be backed by
  a `get_player_form_profile` and/or `search_player_news` call in that turn — not
  answered from the model's own memory of cricket. Enforced as a required step for
  recommendation-type questions, not left to the model's discretion.
- `search_player_news` filters out anything past a recency window (older injury/form
  news is more likely to be stale/wrong for a live decision) and always surfaces
  source + date in the UI, so a stale or shaky claim is visibly attributable, not
  presented as settled fact.
- The model is instructed to only state numbers that came from a tool call in that
  turn, and to say so explicitly when evidence is thin or conflicting, rather than
  smoothing over uncertainty.
- Every tool call (all 4, not just the write) is logged to a Lakebase
  `agent_tool_call_log` table (tool name, params summary, franchise, result, timestamp)
  — flows through CDF too, and is what powers the tool-usage analytics in Section 9,
  plus doubles as an audit trail if a recommendation is ever questioned after the fact.

## 9. Analytics

| Analytic | Source | Powers |
| --- | --- | --- |
| Player form trend (last 5/10 matches vs. career) | Gold Delta (Spark) | Player profile page |
| Venue + format performance splits | Gold Delta (Spark) | Player profile page |
| Value-for-money (price paid vs. form-adjusted expected value) | Gold Delta + `lb_player_investments_history` (CDF) | Analytics tab, post-bid feedback |
| Bid price trajectory per player | `lb_player_investments_history` (CDF) | Analytics tab |
| Franchise purse burn-down over the session | `lb_franchise_roster_history` (CDF) | My Franchise tab, Analytics tab |
| Squad role/composition balance (bat/bowl/keeper/all-rounder, pace/spin, overseas/domestic) | Live Lakebase read via `get_franchise_status` + gold player master | My Franchise tab |
| Agent tool-call volume, latency, and blocked-bid count | `lb_agent_tool_call_log_history` (CDF) | Analytics tab — this is also your best demo evidence that the guardrail actually works |
| Sold/unsold funnel, league-wide spend | `lb_*_history` (CDF), aggregated across franchises | Analytics tab (stretch if time allows) |

## 10. UI — information architecture

Framed as a live-auction companion: one persistent chat drawer, four screens under it.

**Live Auction Console (home screen).** The screen used in the room. Currently-up
player set manually (no live BCCI feed exists to read this from). Player card with
photo, role, base price; strengths/weaknesses as agent-generated bullets grounded in
tools 1 and 2; a recommended bid ceiling with the reasoning shown, not just the number;
Buy (opens the dry-run preview, then confirm) and Add to Wishlist buttons.

**Player Explorer.** Searchable/filterable board — role (batter/bowler/keeper/
all-rounder), bowling style (pace/spin) as a facet rather than a 5th role, overseas/
domestic, price bracket. Drills into the full **Player Profile**: photo, bio, career
stats table, form sparkline, venue chart, news feed with source links, Buy/Wishlist.

**My Franchise.** Roster grid by role, purse-remaining gauge, overseas/RTM tracker,
role-balance chart, wishlist. Also where a franchise is created and a starting roster
imported — the bring-your-own-franchise entry point.

**Analytics.** The CDF-powered dashboards from Section 9.

**Persistent Agent Chat Drawer**, open from any screen — real-time strategy Q&A
("what should we prioritize with ₹12cr and 4 slots left") and a "Build a strategy"
quick-form (budget, role needs, constraints) that feeds a structured planning prompt
to the same 4 tools. Not a separate tab — deliberately always-available, matching the
"hand app" framing.

**Player photos**: rather than a second API, Tavily supports image results
(`include_images`) — we pull a photo URL alongside the news search and cache it in
Delta, falling back to a simple role-based avatar if no usable image comes back. Real
photos where available, no extra integration.

**MVP-cut if Day 2 runs short (in this order):** league-wide/multi-franchise
analytics first, then value-for-money scatter (keep simpler bar charts), then dedicated
strategy quick-form (chat still works without it, just less guided), then real player
photos (avatar fallback becomes the default). The 4 tools, rule-validated writes, and
the 4 core screens are not cut candidates — those are the rubric.

## 11. What I need from you to actually start building

1. Confirm you're good with the decisions in Section 1 (or flag changes).
2. Databricks workspace URL + a personal access token (or Databricks CLI profile) if
   you want me to provision/run things directly from here, rather than you copy-pasting
   notebooks in by hand — meaningful time savings given 2 days.
3. Say "go" — nothing in `notebooks/`, `sql/`, `agent/`, `app/` gets written until then.

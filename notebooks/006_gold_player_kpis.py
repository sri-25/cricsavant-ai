# Databricks notebook source
# CricSavant AI -- Gold layer: player KPIs for auction decision-making.
#
# DESIGN
# ------
# Two grains, same pattern as silver's matches/deliveries split:
#
#   1. Fact tables (gold.batting_innings, gold.bowling_innings): one row
#      per player per match per innings. Built once here by rolling up
#      silver.deliveries. This is the expensive step (full ball-by-ball
#      scan) -- everything else is a cheap GROUP BY over these.
#
#   2. Summary tables: built by calling ONE reusable aggregation
#      function (summarize_batting / summarize_bowling) with different
#      group-by columns and filters. Adding a new KPI slice later is a
#      new function call, not new SQL -- the thing you said you wanted.
#
# SCOPE DECISION: auction-relevant format.
# IPL auctions are buying T20 ability, not Test/ODI ability. All the
# "form" and "recent form" tables below are scoped to T20_LEAGUES
# (IPL/BBL/PSL/CPL/SA20/ILT20/T20I) by default -- adjustable in one
# place (the T20_LEAGUES list), not re-derived per query.
#
# WHAT THIS DOES NOT CLAIM TO KNOW (real data gaps, not bugs):
#   - Batting/bowling handedness or bowling style (pace/spin/wrist) --
#     not in Cricsheet. Backlog item #12 (post-submission).
#   - Fielding quality beyond raw dismissal counts (no catch/drop data).
#   - Auction price / value-for-money -- needs a Lakebase join, happens
#     at the app layer, not here.
#   - A single "player value score" -- deliberately NOT computed.
#     Blending batting and bowling metrics into one number is a
#     modeling choice with arbitrary weights, which would look like a
#     fact but isn't one. gold.allrounder_profile below joins the raw
#     batting + bowling metrics side by side and stops there; scoring
#     is a decision for the agent/app layer to make transparently, not
#     something to bury in a gold table.
#
#   - regressed_strike_rate / regressed_economy on the T20-leagues
#     tables ARE a modeling choice too, but a different kind: they're a
#     named, standard statistical technique (credibility weighting /
#     regression to the mean), not an invented weighting scheme, and
#     they exist alongside the raw numbers rather than replacing them.
#     Needed because a raw ORDER BY on strike_rate/economy at a 60-ball
#     qualification floor is dominated by small-sample noise -- a
#     proven, large-sample performer can rank below a player who had
#     one hot 2-match stretch. See the PRIOR_BALLS comment further down.
#
# CRICKET-SCORING CONVENTIONS APPLIED (standard, not invented):
#   - "Balls faced" / "balls bowled" exclude wides and no-balls (they
#     aren't legal deliveries).
#   - Byes and leg-byes count as runs for the team but NOT against the
#     bowler's figures; wides and no-balls DO count against the bowler
#     (including any runs scored off them).
#   - A wicket credits the BOWLER unless BOWLER_EXCLUDED_KINDS says
#     otherwise (run out, retired, timed out, obstructing the field --
#     see the sanity-check cell below for the actual kind strings
#     before trusting this list).
#   - "Boundary" 4s/6s exclude deliveries flagged non_boundary (Cricsheet's
#     own flag for e.g. overthrows that reach the boundary rope but
#     aren't a batting boundary).
#
# PLAYER IDENTITY: every player-level grouping below uses batter_key /
# bowler_key, not the raw batter/bowler name string. These are
# coalesce(registry_id, "name:"+name) -- the real Cricsheet registry id
# when the delivery resolved to one (see 005's coverage-check cell),
# falling back to a name-prefixed synthetic key only for the rare
# unresolved case. The fallback matters: grouping directly by a
# possibly-null id would silently bucket EVERY unresolved player
# together under one null key, which is worse than the original
# name-collision risk, not a fix for it. A resolved-name column
# (player_name, picked via first()) rides along on every summary table
# for display -- it's a label, not the grouping key.

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.gold")

from pyspark.sql import functions as F

SILVER_DELIVERIES = "cricsavant.silver.deliveries"
SILVER_MATCHES = "cricsavant.silver.matches"

deliveries_df = spark.table(SILVER_DELIVERIES)
matches_df = spark.table(SILVER_MATCHES)

# T20 franchise/international leagues -- the formats auction decisions
# actually care about. Not Test/ODI. One list, referenced everywhere
# below that needs it.
T20_LEAGUES = ["IPL", "BBL", "PSL", "CPL", "SA20", "ILT20", "T20I"]

# COMMAND ----------

# Sanity check BEFORE we build bowler-credit logic on top of it: confirm
# the actual dismissal "kind" strings in the data match what
# BOWLER_EXCLUDED_KINDS below assumes. If these don't match, fix the
# list in the next cell -- one place, not a re-derivation.
display(
    deliveries_df
    .filter(F.col("is_wicket") == True)  # noqa: E712
    .select(F.explode("wickets").alias("wk"))
    .select(F.col("wk.kind").alias("dismissal_kind"))
    .groupBy("dismissal_kind")
    .count()
    .orderBy(F.desc("count"))
)

# COMMAND ----------

# Dismissal kinds NOT credited to the bowler -- standard scoring
# convention. Adjust this list, not the logic below it, if the sanity
# check above shows different strings.
BOWLER_EXCLUDED_KINDS = [
    "run out", "retired hurt", "retired not out", "retired out",
    "obstructing the field", "timed out",
]
excluded_kinds_sql = "array(" + ",".join(f"'{k}'" for k in BOWLER_EXCLUDED_KINDS) + ")"

# COMMAND ----------

# Match-level context needed for situational tagging. Joined onto every
# delivery so batting/bowling rollups can group by it directly.
match_context = matches_df.select(
    "match_id", "season", "start_date", "venue", "match_type", "team_type",
    "team_1", "team_2", "outcome_result", "outcome_winner",
    "outcome_by_runs", "outcome_by_wickets", "event_stage",
)

# Actual innings length in overs, derived from the data itself (not a
# nominal per-format constant) -- correctly handles rain-shortened /
# DLS-reduced innings, which a fixed "T20 = 20 overs" assumption would
# get wrong.
innings_length = (
    deliveries_df.groupBy("match_id", "innings_seq")
    .agg(F.max("over_number").alias("last_over"))
    .withColumn("innings_overs", F.col("last_over") + F.lit(1))
    .drop("last_over")
)

deliveries_enriched = (
    deliveries_df
    .join(match_context, on="match_id", how="left")
    .join(innings_length, on=["match_id", "innings_seq"], how="left")
    .withColumn("is_chase", F.col("innings_target_runs").isNotNull())
    .withColumn(
        "is_close_match",
        (F.col("outcome_by_runs").isNotNull() & (F.col("outcome_by_runs") <= 10))
        | (F.col("outcome_by_wickets").isNotNull() & (F.col("outcome_by_wickets") <= 2)),
    )
    .withColumn("is_knockout", F.col("event_stage").isNotNull())
    .withColumn(
        # Death overs = last 4 overs of a <=20-over innings, last 10 of
        # a longer limited-overs innings. Tests have no death-overs
        # concept (unlimited overs) -- phase is null for them.
        "death_over_threshold",
        F.when(F.col("match_type") == "Test", F.lit(None).cast("long"))
        .when(F.col("innings_overs") <= 20, F.col("innings_overs") - F.lit(4))
        .otherwise(F.col("innings_overs") - F.lit(10)),
    )
    .withColumn(
        "phase",
        F.when(F.col("match_type") == "Test", F.lit(None).cast("string"))
        .when(F.col("powerplay_type").isNotNull(), F.lit("powerplay"))
        .when(F.col("over_number") >= F.col("death_over_threshold"), F.lit("death"))
        .otherwise(F.lit("middle")),
    )
    .withColumn("batter_key", F.coalesce(F.col("batter_id"), F.concat(F.lit("name:"), F.col("batter"))))
    .withColumn("bowler_key", F.coalesce(F.col("bowler_id"), F.concat(F.lit("name:"), F.col("bowler"))))
)

legal_ball = (F.col("extras_wides") == 0) & (F.col("extras_noballs") == 0)
is_boundary_4 = (F.col("runs_batter") == 4) & (~F.col("non_boundary"))
is_boundary_6 = (F.col("runs_batter") == 6) & (~F.col("non_boundary"))

# COMMAND ----------

# gold.batting_innings -- one row per (match, innings, batter).

dismissals_df = (
    deliveries_df
    .filter(F.col("is_wicket") == True)  # noqa: E712
    .select("match_id", "innings_seq", F.explode("wickets").alias("wk"))
    .select(
        "match_id", "innings_seq",
        F.col("wk.player_out").alias("player_out"),
        F.col("wk.kind").alias("dismissal_kind"),
    )
    .dropDuplicates(["match_id", "innings_seq", "player_out"])
)

batting_base = (
    deliveries_enriched
    .groupBy("match_id", "competition", "innings_seq", "batting_team", "batter_key", "batter_id", "batter")
    .agg(
        F.sum("runs_batter").alias("runs"),
        F.sum(F.when(legal_ball, 1).otherwise(0)).alias("balls_faced"),
        F.sum(F.when(is_boundary_4, 1).otherwise(0)).alias("fours"),
        F.sum(F.when(is_boundary_6, 1).otherwise(0)).alias("sixes"),
        F.sum(F.when(legal_ball & (F.col("runs_batter") == 0), 1).otherwise(0)).alias("dot_balls"),
        F.sum(F.when(F.col("phase") == "powerplay", F.col("runs_batter")).otherwise(0)).alias("pp_runs"),
        F.sum(F.when((F.col("phase") == "powerplay") & legal_ball, 1).otherwise(0)).alias("pp_balls"),
        F.sum(F.when(F.col("phase") == "death", F.col("runs_batter")).otherwise(0)).alias("death_runs"),
        F.sum(F.when((F.col("phase") == "death") & legal_ball, 1).otherwise(0)).alias("death_balls"),
        F.max("is_chase").alias("is_chase"),
        F.max("is_close_match").alias("is_close_match"),
        F.max("is_knockout").alias("is_knockout"),
        F.max("season").alias("season"),
        F.max("start_date").alias("match_date"),
        F.max("venue").alias("venue"),
        F.max("match_type").alias("match_type"),
    )
)

batting_innings = (
    batting_base
    .join(
        dismissals_df.select(
            "match_id", "innings_seq",
            F.col("player_out").alias("batter"),
            "dismissal_kind",
        ),
        on=["match_id", "innings_seq", "batter"],
        how="left",
    )
    .withColumn("is_out", F.col("dismissal_kind").isNotNull())
    .withColumn("strike_rate", F.when(F.col("balls_faced") > 0, F.round(F.col("runs") * 100.0 / F.col("balls_faced"), 2)))
    .withColumn("boundary_pct", F.when(F.col("balls_faced") > 0, F.round((F.col("fours") + F.col("sixes")) * 100.0 / F.col("balls_faced"), 2)))
    .withColumn("dot_pct", F.when(F.col("balls_faced") > 0, F.round(F.col("dot_balls") * 100.0 / F.col("balls_faced"), 2)))
    .withColumn("pp_strike_rate", F.when(F.col("pp_balls") > 0, F.round(F.col("pp_runs") * 100.0 / F.col("pp_balls"), 2)))
    .withColumn("death_strike_rate", F.when(F.col("death_balls") > 0, F.round(F.col("death_runs") * 100.0 / F.col("death_balls"), 2)))
)

(
    batting_innings.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("competition")
    .saveAsTable("cricsavant.gold.batting_innings")
)
print("gold.batting_innings:", batting_innings.count(), "rows")

# COMMAND ----------

# gold.bowling_innings -- one row per (match, innings, bowler).

deliveries_bowling = (
    deliveries_enriched
    .withColumn("bowling_team", F.when(F.col("batting_team") == F.col("team_1"), F.col("team_2")).otherwise(F.col("team_1")))
    .withColumn("is_legal_ball", legal_ball.cast("int"))
    .withColumn("conceded", F.col("runs_batter") + F.col("extras_wides") + F.col("extras_noballs"))
    .withColumn(
        "bowler_credited_wickets",
        F.expr(f"size(filter(coalesce(wickets, array()), w -> NOT array_contains({excluded_kinds_sql}, w.kind)))"),
    )
    .withColumn("is_dot", (F.col("is_legal_ball") == 1) & (F.col("runs_total") == 0))
)

bowling_innings = (
    deliveries_bowling
    .groupBy("match_id", "competition", "innings_seq", "bowling_team", "bowler_key", "bowler_id", "bowler")
    .agg(
        F.sum("conceded").alias("runs_conceded"),
        F.sum("is_legal_ball").alias("balls_bowled"),
        F.sum("bowler_credited_wickets").alias("wickets"),
        F.sum(F.col("is_dot").cast("int")).alias("dot_balls"),
        F.sum(F.when(F.col("extras_wides") > 0, 1).otherwise(0)).alias("wides"),
        F.sum(F.when(F.col("extras_noballs") > 0, 1).otherwise(0)).alias("noballs"),
        F.sum(F.when(F.col("phase") == "powerplay", F.col("conceded")).otherwise(0)).alias("pp_runs_conceded"),
        F.sum(F.when((F.col("phase") == "powerplay") & (F.col("is_legal_ball") == 1), 1).otherwise(0)).alias("pp_balls_bowled"),
        F.sum(F.when(F.col("phase") == "powerplay", F.col("bowler_credited_wickets")).otherwise(0)).alias("pp_wickets"),
        F.sum(F.when(F.col("phase") == "death", F.col("conceded")).otherwise(0)).alias("death_runs_conceded"),
        F.sum(F.when((F.col("phase") == "death") & (F.col("is_legal_ball") == 1), 1).otherwise(0)).alias("death_balls_bowled"),
        F.sum(F.when(F.col("phase") == "death", F.col("bowler_credited_wickets")).otherwise(0)).alias("death_wickets"),
        F.max("is_chase").alias("is_chase"),
        F.max("is_close_match").alias("is_close_match"),
        F.max("is_knockout").alias("is_knockout"),
        F.max("season").alias("season"),
        F.max("start_date").alias("match_date"),
        F.max("venue").alias("venue"),
        F.max("match_type").alias("match_type"),
    )
    .withColumn("economy", F.when(F.col("balls_bowled") > 0, F.round(F.col("runs_conceded") * 6.0 / F.col("balls_bowled"), 2)))
    .withColumn("bowling_average", F.when(F.col("wickets") > 0, F.round(F.col("runs_conceded") * 1.0 / F.col("wickets"), 2)))
    .withColumn("bowling_strike_rate", F.when(F.col("wickets") > 0, F.round(F.col("balls_bowled") * 1.0 / F.col("wickets"), 2)))
    .withColumn("dot_pct", F.when(F.col("balls_bowled") > 0, F.round(F.col("dot_balls") * 100.0 / F.col("balls_bowled"), 2)))
    .withColumn("pp_economy", F.when(F.col("pp_balls_bowled") > 0, F.round(F.col("pp_runs_conceded") * 6.0 / F.col("pp_balls_bowled"), 2)))
    .withColumn("death_economy", F.when(F.col("death_balls_bowled") > 0, F.round(F.col("death_runs_conceded") * 6.0 / F.col("death_balls_bowled"), 2)))
)

(
    bowling_innings.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("competition")
    .saveAsTable("cricsavant.gold.bowling_innings")
)
print("gold.bowling_innings:", bowling_innings.count(), "rows")

# COMMAND ----------

# Reusable aggregation functions -- this is the "add a KPI = one
# function call" mechanism. group_by_cols and filter_condition are the
# knobs; every summary table below is a call to one of these two
# functions, not new SQL.

def summarize_batting(df, group_by_cols, filter_condition=None, min_balls=1):
    """group_by_cols should include batter_key (the resolved identity),
    not the raw batter name -- see the PLAYER IDENTITY note at the top
    of this notebook. A representative display name is added
    automatically via first(), not by requiring "batter" in
    group_by_cols."""
    d = df if filter_condition is None else df.filter(filter_condition)
    return (
        d.groupBy(*group_by_cols)
        .agg(
            F.first("batter").alias("player_name"),
            F.countDistinct("match_id", "innings_seq").alias("innings"),
            F.sum("runs").alias("runs"),
            F.sum("balls_faced").alias("balls_faced"),
            F.sum("fours").alias("fours"),
            F.sum("sixes").alias("sixes"),
            F.sum(F.when(F.col("is_out"), 1).otherwise(0)).alias("dismissals"),
            F.sum("pp_runs").alias("pp_runs"),
            F.sum("pp_balls").alias("pp_balls"),
            F.sum("death_runs").alias("death_runs"),
            F.sum("death_balls").alias("death_balls"),
            F.round(F.stddev_samp("runs"), 2).alias("runs_stddev"),
        )
        .withColumn("strike_rate", F.when(F.col("balls_faced") > 0, F.round(F.col("runs") * 100.0 / F.col("balls_faced"), 2)))
        .withColumn("average", F.when(F.col("dismissals") > 0, F.round(F.col("runs") * 1.0 / F.col("dismissals"), 2)))
        .withColumn("not_out_pct", F.when(F.col("innings") > 0, F.round((F.col("innings") - F.col("dismissals")) * 100.0 / F.col("innings"), 2)))
        .withColumn("boundary_pct", F.when(F.col("balls_faced") > 0, F.round((F.col("fours") + F.col("sixes")) * 100.0 / F.col("balls_faced"), 2)))
        .withColumn("pp_strike_rate", F.when(F.col("pp_balls") > 0, F.round(F.col("pp_runs") * 100.0 / F.col("pp_balls"), 2)))
        .withColumn("death_strike_rate", F.when(F.col("death_balls") > 0, F.round(F.col("death_runs") * 100.0 / F.col("death_balls"), 2)))
        .filter(F.col("balls_faced") >= min_balls)
    )


def summarize_bowling(df, group_by_cols, filter_condition=None, min_balls=1):
    """group_by_cols should include bowler_key (the resolved identity),
    not the raw bowler name -- see the PLAYER IDENTITY note at the top
    of this notebook."""
    d = df if filter_condition is None else df.filter(filter_condition)
    return (
        d.groupBy(*group_by_cols)
        .agg(
            F.first("bowler").alias("player_name"),
            F.countDistinct("match_id", "innings_seq").alias("innings"),
            F.sum("runs_conceded").alias("runs_conceded"),
            F.sum("balls_bowled").alias("balls_bowled"),
            F.sum("wickets").alias("wickets"),
            F.sum("dot_balls").alias("dot_balls"),
            F.sum("pp_runs_conceded").alias("pp_runs_conceded"),
            F.sum("pp_balls_bowled").alias("pp_balls_bowled"),
            F.sum("pp_wickets").alias("pp_wickets"),
            F.sum("death_runs_conceded").alias("death_runs_conceded"),
            F.sum("death_balls_bowled").alias("death_balls_bowled"),
            F.sum("death_wickets").alias("death_wickets"),
        )
        .withColumn("economy", F.when(F.col("balls_bowled") > 0, F.round(F.col("runs_conceded") * 6.0 / F.col("balls_bowled"), 2)))
        .withColumn("bowling_average", F.when(F.col("wickets") > 0, F.round(F.col("runs_conceded") * 1.0 / F.col("wickets"), 2)))
        .withColumn("bowling_strike_rate", F.when(F.col("wickets") > 0, F.round(F.col("balls_bowled") * 1.0 / F.col("wickets"), 2)))
        .withColumn("dot_pct", F.when(F.col("balls_bowled") > 0, F.round(F.col("dot_balls") * 100.0 / F.col("balls_bowled"), 2)))
        .withColumn("pp_economy", F.when(F.col("pp_balls_bowled") > 0, F.round(F.col("pp_runs_conceded") * 6.0 / F.col("pp_balls_bowled"), 2)))
        .withColumn("death_economy", F.when(F.col("death_balls_bowled") > 0, F.round(F.col("death_runs_conceded") * 6.0 / F.col("death_balls_bowled"), 2)))
        .filter(F.col("balls_bowled") >= min_balls)
    )


def write_gold(df, name, partition_cols=None):
    writer = df.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.saveAsTable(f"cricsavant.gold.{name}")
    print(f"cricsavant.gold.{name}: {df.count()} rows")

# COMMAND ----------

batting_innings_tbl = spark.table("cricsavant.gold.batting_innings")
bowling_innings_tbl = spark.table("cricsavant.gold.bowling_innings")

t20_filter = F.col("competition").isin(T20_LEAGUES)

# Career form, every competition -- the broadest cut, mostly a baseline.
write_gold(summarize_batting(batting_innings_tbl, ["batter_key"], min_balls=60), "batting_form_career")
write_gold(summarize_bowling(bowling_innings_tbl, ["bowler_key"], min_balls=60), "bowling_form_career")

# T20-leagues-only form -- the single most auction-relevant table:
# batting/bowling ability in the actual format being auctioned for.
batting_t20_base = summarize_batting(batting_innings_tbl, ["batter_key"], filter_condition=t20_filter, min_balls=60)
bowling_t20_base = summarize_bowling(bowling_innings_tbl, ["bowler_key"], filter_condition=t20_filter, min_balls=60)

# Shrinkage (regression to the mean) on top of the raw rate stats.
# min_balls=60 (10 overs) is enough to be LISTED, but nowhere near
# enough to rank fairly against a player with thousands of deliveries
# -- a bowler with one or two brilliant spells can post an economy no
# one sustains over a real career, which would bury a proven, elite,
# large-sample performer (e.g. a Bumrah-caliber bowler) under small-
# sample noise on a plain ORDER BY. Standard fix, not an invented
# metric: credibility-weight each player's own rate against the
# league-wide average, weighted by how many real balls of evidence
# they have. PRIOR_BALLS is the one tunable knob -- how many balls of
# "league average" the prior is worth. A player with far more real
# balls than that converges to their own true rate; a player with far
# fewer gets pulled toward the average. Both raw and regressed columns
# are kept -- raw for "what actually happened," regressed for "best
# estimate of true skill, adjusted for sample size."
PRIOR_BALLS = 120  # ~20 overs' worth of league-average evidence

league_avg_batting_rpb = batting_t20_base.agg(F.sum("runs") / F.sum("balls_faced")).collect()[0][0]
league_avg_bowling_rpb = bowling_t20_base.agg(F.sum("runs_conceded") / F.sum("balls_bowled")).collect()[0][0]

batting_form_t20_leagues = batting_t20_base.withColumn(
    "regressed_strike_rate",
    F.round(
        (F.col("runs") + F.lit(PRIOR_BALLS) * F.lit(league_avg_batting_rpb))
        / (F.col("balls_faced") + F.lit(PRIOR_BALLS))
        * 100,
        2,
    ),
)
bowling_form_t20_leagues = bowling_t20_base.withColumn(
    "regressed_economy",
    F.round(
        (F.col("runs_conceded") + F.lit(PRIOR_BALLS) * F.lit(league_avg_bowling_rpb))
        / (F.col("balls_bowled") + F.lit(PRIOR_BALLS))
        * 6,
        2,
    ),
)

write_gold(batting_form_t20_leagues, "batting_form_t20_leagues")
write_gold(bowling_form_t20_leagues, "bowling_form_t20_leagues")

# Recent form -- real auctions weight the last ~1.5 seasons of T20
# cricket far more heavily than career totals. Window is relative to
# the most recent match IN THE DATA (not today's date), and is one
# adjustable constant, not logic to rewrite.
#
# THIS is the table auction-facing rankings should actually be sorted
# by, not the career one -- an auction is a bet on current form, not a
# lifetime "true skill" estimate. It needs the same shrinkage treatment
# as the career table, if anything more: an 18-month window gives
# EVERYONE fewer balls, including proven players, so small-sample noise
# is worse here, not better. The prior is computed from this same
# recent-period population (not the career-wide rate), so a declining
# veteran or a breakout player both get judged against current scoring
# conditions, not blended against years-old form.
max_batting_date = batting_innings_tbl.agg(F.max("match_date")).collect()[0][0]
RECENT_WINDOW_DAYS = 545  # ~18 months
recent_filter = t20_filter & (F.col("match_date") >= F.date_sub(F.lit(max_batting_date), RECENT_WINDOW_DAYS))

batting_recent_base = summarize_batting(batting_innings_tbl, ["batter_key"], filter_condition=recent_filter, min_balls=30)
bowling_recent_base = summarize_bowling(bowling_innings_tbl, ["bowler_key"], filter_condition=recent_filter, min_balls=30)

league_avg_batting_recent_rpb = batting_recent_base.agg(F.sum("runs") / F.sum("balls_faced")).collect()[0][0]
league_avg_bowling_recent_rpb = bowling_recent_base.agg(F.sum("runs_conceded") / F.sum("balls_bowled")).collect()[0][0]

batting_form_recent = batting_recent_base.withColumn(
    "regressed_strike_rate",
    F.round(
        (F.col("runs") + F.lit(PRIOR_BALLS) * F.lit(league_avg_batting_recent_rpb))
        / (F.col("balls_faced") + F.lit(PRIOR_BALLS))
        * 100,
        2,
    ),
)
bowling_form_recent = bowling_recent_base.withColumn(
    "regressed_economy",
    F.round(
        (F.col("runs_conceded") + F.lit(PRIOR_BALLS) * F.lit(league_avg_bowling_recent_rpb))
        / (F.col("balls_bowled") + F.lit(PRIOR_BALLS))
        * 6,
        2,
    ),
)

write_gold(batting_form_recent, "batting_form_recent")
write_gold(bowling_form_recent, "bowling_form_recent")

# Venue splits -- home-ground / conditions fit, useful when a franchise
# is scouting for a specific home venue.
write_gold(summarize_batting(batting_innings_tbl, ["batter_key", "venue"], filter_condition=t20_filter, min_balls=60), "batting_form_by_venue")
write_gold(summarize_bowling(bowling_innings_tbl, ["bowler_key", "venue"], filter_condition=t20_filter, min_balls=60), "bowling_form_by_venue")

# COMMAND ----------

# Phase splits -- powerplay / middle / death specialization. Built
# directly off delivery-grain data (phase doesn't survive into the
# innings-grain fact tables except as pp_*/death_* subtotals) so
# "middle overs" is available too, not just powerplay/death.

phase_deliveries = deliveries_enriched.filter(t20_filter & F.col("phase").isNotNull())

batting_phase_splits = (
    phase_deliveries
    .withColumn("legal_ball_flag", legal_ball.cast("int"))
    .withColumn("boundary_flag", (is_boundary_4 | is_boundary_6).cast("int"))
    .groupBy("batter_key", "phase")
    .agg(
        F.first("batter").alias("player_name"),
        F.countDistinct("match_id", "innings_seq").alias("innings"),
        F.sum("runs_batter").alias("runs"),
        F.sum("legal_ball_flag").alias("balls_faced"),
        F.sum("boundary_flag").alias("boundaries"),
    )
    .withColumn("strike_rate", F.when(F.col("balls_faced") > 0, F.round(F.col("runs") * 100.0 / F.col("balls_faced"), 2)))
    .withColumn("boundary_pct", F.when(F.col("balls_faced") > 0, F.round(F.col("boundaries") * 100.0 / F.col("balls_faced"), 2)))
    .filter(F.col("balls_faced") >= 30)
)
write_gold(batting_phase_splits, "batting_phase_splits")

bowling_phase_splits = (
    phase_deliveries
    .withColumn("bowling_team", F.when(F.col("batting_team") == F.col("team_1"), F.col("team_2")).otherwise(F.col("team_1")))
    .withColumn("is_legal_ball", legal_ball.cast("int"))
    .withColumn("conceded", F.col("runs_batter") + F.col("extras_wides") + F.col("extras_noballs"))
    .withColumn(
        "bowler_credited_wickets",
        F.expr(f"size(filter(coalesce(wickets, array()), w -> NOT array_contains({excluded_kinds_sql}, w.kind)))"),
    )
    .groupBy("bowler_key", "phase")
    .agg(
        F.first("bowler").alias("player_name"),
        F.countDistinct("match_id", "innings_seq").alias("innings"),
        F.sum("conceded").alias("runs_conceded"),
        F.sum("is_legal_ball").alias("balls_bowled"),
        F.sum("bowler_credited_wickets").alias("wickets"),
    )
    .withColumn("economy", F.when(F.col("balls_bowled") > 0, F.round(F.col("runs_conceded") * 6.0 / F.col("balls_bowled"), 2)))
    .filter(F.col("balls_bowled") >= 30)
)
write_gold(bowling_phase_splits, "bowling_phase_splits")

# COMMAND ----------

# Situational profiles -- clutch performance. Fixed small set of
# binary contexts (chase/close-match/knockout), so a wide "one row per
# player" table is more directly usable than a long/grouped one.
#
# "Close match" = won/lost by <=10 runs or <=2 wickets -- a standard
# but genuinely arbitrary convention; adjust the two constants in
# deliveries_enriched above if a different threshold is wanted.

batting_situational = (
    batting_innings_tbl
    .filter(t20_filter)
    .groupBy("batter_key")
    .agg(
        F.first("batter").alias("player_name"),
        F.sum(F.when(F.col("is_chase"), F.col("runs")).otherwise(0)).alias("chase_runs"),
        F.sum(F.when(F.col("is_chase"), F.col("balls_faced")).otherwise(0)).alias("chase_balls"),
        F.sum(F.when(~F.col("is_chase"), F.col("runs")).otherwise(0)).alias("defend_runs"),
        F.sum(F.when(~F.col("is_chase"), F.col("balls_faced")).otherwise(0)).alias("defend_balls"),
        F.sum(F.when(F.col("is_close_match"), F.col("runs")).otherwise(0)).alias("close_match_runs"),
        F.sum(F.when(F.col("is_close_match"), F.col("balls_faced")).otherwise(0)).alias("close_match_balls"),
        F.sum(F.when(F.col("is_knockout"), F.col("runs")).otherwise(0)).alias("knockout_runs"),
        F.sum(F.when(F.col("is_knockout"), F.col("balls_faced")).otherwise(0)).alias("knockout_balls"),
        F.sum(F.when(F.col("is_out"), 1).otherwise(0)).alias("dismissals_total"),
        F.countDistinct("match_id", "innings_seq").alias("innings_total"),
    )
    .withColumn("chase_sr", F.when(F.col("chase_balls") > 0, F.round(F.col("chase_runs") * 100.0 / F.col("chase_balls"), 2)))
    .withColumn("defend_sr", F.when(F.col("defend_balls") > 0, F.round(F.col("defend_runs") * 100.0 / F.col("defend_balls"), 2)))
    .withColumn("close_match_sr", F.when(F.col("close_match_balls") > 0, F.round(F.col("close_match_runs") * 100.0 / F.col("close_match_balls"), 2)))
    .withColumn("knockout_sr", F.when(F.col("knockout_balls") > 0, F.round(F.col("knockout_runs") * 100.0 / F.col("knockout_balls"), 2)))
    .withColumn("finisher_pct", F.when(F.col("innings_total") > 0, F.round((F.col("innings_total") - F.col("dismissals_total")) * 100.0 / F.col("innings_total"), 2)))
    .filter(F.col("innings_total") >= 10)
)
write_gold(batting_situational, "batting_situational_profile")

bowling_situational = (
    bowling_innings_tbl
    .filter(t20_filter)
    .groupBy("bowler_key")
    .agg(
        F.first("bowler").alias("player_name"),
        F.sum(F.when(F.col("is_chase"), F.col("runs_conceded")).otherwise(0)).alias("chase_runs_conceded"),
        F.sum(F.when(F.col("is_chase"), F.col("balls_bowled")).otherwise(0)).alias("chase_balls_bowled"),
        F.sum(F.when(F.col("is_close_match"), F.col("runs_conceded")).otherwise(0)).alias("close_match_runs_conceded"),
        F.sum(F.when(F.col("is_close_match"), F.col("balls_bowled")).otherwise(0)).alias("close_match_balls_bowled"),
        F.sum(F.when(F.col("is_close_match"), F.col("wickets")).otherwise(0)).alias("close_match_wickets"),
        F.sum(F.when(F.col("is_knockout"), F.col("runs_conceded")).otherwise(0)).alias("knockout_runs_conceded"),
        F.sum(F.when(F.col("is_knockout"), F.col("balls_bowled")).otherwise(0)).alias("knockout_balls_bowled"),
        F.sum(F.when(F.col("is_knockout"), F.col("wickets")).otherwise(0)).alias("knockout_wickets"),
        F.countDistinct("match_id", "innings_seq").alias("innings_total"),
    )
    .withColumn("chase_economy", F.when(F.col("chase_balls_bowled") > 0, F.round(F.col("chase_runs_conceded") * 6.0 / F.col("chase_balls_bowled"), 2)))
    .withColumn("close_match_economy", F.when(F.col("close_match_balls_bowled") > 0, F.round(F.col("close_match_runs_conceded") * 6.0 / F.col("close_match_balls_bowled"), 2)))
    .withColumn("knockout_economy", F.when(F.col("knockout_balls_bowled") > 0, F.round(F.col("knockout_runs_conceded") * 6.0 / F.col("knockout_balls_bowled"), 2)))
    .filter(F.col("innings_total") >= 10)
)
write_gold(bowling_situational, "bowling_situational_profile")

# COMMAND ----------

# All-rounder profile -- batting + bowling T20-league form joined side
# by side for players with both. Deliberately NOT collapsed into one
# score (see header comment).
batting_t20 = spark.table("cricsavant.gold.batting_form_t20_leagues")
bowling_t20 = spark.table("cricsavant.gold.bowling_form_t20_leagues")

allrounder_profile = (
    batting_t20.select(
        F.col("batter_key").alias("player_key"),
        F.col("player_name"),
        F.col("innings").alias("batting_innings"),
        F.col("runs"), F.col("strike_rate"), F.col("average").alias("batting_average"),
    )
    .join(
        bowling_t20.select(
            F.col("bowler_key").alias("player_key"),
            F.col("innings").alias("bowling_innings"),
            F.col("wickets"), F.col("economy"), F.col("bowling_average"),
        ),
        on="player_key", how="inner",
    )
    # Clearing the 60-ball-bowled floor cumulatively over a long career
    # (occasional part-time overs) is not the same thing as being a
    # regular bowling option. This ratio makes that distinction visible
    # instead of letting prolific long-career batsmen who bowled a
    # handful of overs a year masquerade as all-rounders.
    .withColumn(
        "bowling_involvement_pct",
        F.round(F.col("bowling_innings") * 100.0 / F.col("batting_innings"), 1),
    )
)
write_gold(allrounder_profile, "allrounder_profile")

# COMMAND ----------

# Verification: recognizable names, plausible numbers.
#
# The RECENT tables (not career) are the ones that should actually
# drive auction-facing rankings -- that's the real test of whether this
# is fixed, not the career view.
print("Top 10 RECENT-FORM (~18mo) REGRESSED strike rates -- the auction-relevant ranking:")
display(spark.table("cricsavant.gold.batting_form_recent").orderBy(F.desc("regressed_strike_rate")).limit(10))

print("Top 10 RECENT-FORM (~18mo) REGRESSED economy rates -- the auction-relevant ranking:")
display(spark.table("cricsavant.gold.bowling_form_recent").orderBy("regressed_economy").limit(10))

print("For comparison -- RECENT-FORM RAW economy (min 30 balls, unadjusted, small-sample-prone):")
display(spark.table("cricsavant.gold.bowling_form_recent").orderBy("economy").limit(10))

print("Career-long views, for reference (not what auction rankings should sort by):")
print("Top 10 T20-league career REGRESSED strike rates:")
display(spark.table("cricsavant.gold.batting_form_t20_leagues").orderBy(F.desc("regressed_strike_rate")).limit(10))

print("Top 10 T20-league career REGRESSED economy rates:")
display(spark.table("cricsavant.gold.bowling_form_t20_leagues").orderBy("regressed_economy").limit(10))

print("Death-overs specialists (batting), min 30 balls in that phase:")
display(spark.table("cricsavant.gold.batting_phase_splits").filter("phase = 'death'").orderBy(F.desc("strike_rate")).limit(10))

print("All-rounders by runs, unfiltered -- includes career part-time bowlers:")
display(spark.table("cricsavant.gold.allrounder_profile").orderBy(F.desc("runs")).limit(10))

print("Genuine all-rounders -- bowled in at least 40% of the innings they batted in:")
display(
    spark.table("cricsavant.gold.allrounder_profile")
    .filter("bowling_involvement_pct >= 40")
    .orderBy(F.desc("runs"))
    .limit(10)
)

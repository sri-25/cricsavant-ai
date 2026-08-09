# Databricks notebook source
# CricSavant AI -- Silver layer: matches + deliveries.
#
# Bronze (cricsavant.raw.bronze_matches) is one row per match with a
# big nested `innings` blob -- correct for a raw landing zone, but not
# what analytics or the agent's tools want to query. Silver splits this
# into two tables by grain, which is the actual design decision here:
#
#   cricsavant.silver.matches      -- one row per match (dimension)
#   cricsavant.silver.deliveries   -- one row per ball bowled (fact)
#
# deliveries is deliberately built at the LOWEST meaningful grain (one
# ball, every raw fact about it preserved) rather than pre-aggregated,
# because that's what makes gold-layer KPIs additive later: a new KPI
# is a new GROUP BY / filter over this same table, not a silver
# schema change. See PROJECT_PLAN.md discussion -- this is also why
# innings.powerplays is carried through and resolved into a
# powerplay_type per delivery here (an objective, source-provided
# fact), while something like "is this a death over" is deliberately
# NOT computed here -- that's a business-defined threshold, so it
# belongs at the gold layer, not baked into silver.
#
# Two scope calls made explicitly (not silently): wickets stays as a
# small nested array on the delivery row rather than its own table
# (multi-wicket-per-ball is an extremely rare, documented edge case --
# not worth a separate table for). review/replacements (Impact Player
# substitution data) are carried through unflattened -- not needed for
# core form/stats KPIs yet, revisit only if Impact Player-specific
# analysis becomes an actual question.
#
# Innings-level flags (target, super_over, declared, forfeited) are
# denormalized onto every delivery in that innings rather than living
# in a separate innings-grain table -- standard fact-table practice,
# keeps this to exactly two tables, and makes filtering (e.g. "exclude
# super overs") a plain WHERE clause with no join.
#
# PLAYER IDENTITY: batter_id/bowler_id/non_striker_id resolve each
# delivery's name string against that match's player_registry map
# (bronze, sourced from Cricsheet's own registry.people). Grouping by
# these IDs in gold instead of raw name strings is what prevents two
# real players who share a name from silently merging into one, or one
# real player fragmenting across name-string variants. element_at() on
# a map returns NULL for a missing key rather than throwing (unlike the
# array out-of-bounds case fixed earlier) -- if a name is somehow
# absent from a given match's registry, its id column is just null,
# not a failure.
#
# Both tables are fully recomputed from bronze every run. Unlike bronze,
# this involves no network calls -- it's a pure in-Lakehouse Spark
# transform over data already sitting in Unity Catalog -- so a full
# rebuild each run is cheap and guarantees silver can never drift out
# of sync with bronze.

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.silver")

BRONZE_TABLE = "cricsavant.raw.bronze_matches"
SILVER_MATCHES_TABLE = "cricsavant.silver.matches"
SILVER_DELIVERIES_TABLE = "cricsavant.silver.deliveries"

bronze_df = spark.table(BRONZE_TABLE)

# COMMAND ----------

from pyspark.sql.functions import col, size, get

# get() throughout, not element_at(): same reasoning as powerplay_type
# below -- dates/teams are "required" per the Cricsheet spec, but
# trusting that to hold across 9,876 real-world files from an external
# source is exactly the kind of assumption that broke bronze earlier.
# get() returns NULL on an empty/short array instead of throwing.
silver_matches_df = bronze_df.select(
    col("match_id"),
    col("competition"),
    col("dates"),
    get(col("dates"), 0).alias("start_date"),
    get(col("dates"), size(col("dates")) - 1).alias("end_date"),
    size(col("dates")).alias("num_days"),
    col("season"),
    col("venue"),
    get(col("teams"), 0).alias("team_1"),
    get(col("teams"), 1).alias("team_2"),
    col("toss.decision").alias("toss_decision"),
    col("toss.winner").alias("toss_winner"),
    col("toss.uncontested").alias("toss_uncontested"),
    col("outcome_result"),
    col("outcome_winner"),
    col("outcome_method"),
    col("outcome_eliminator"),
    col("outcome_by_runs"),
    col("outcome_by_wickets"),
    col("outcome_by_innings"),
    col("player_of_match"),
    col("match_type"),
    col("team_type"),
    col("gender"),
    col("event.name").alias("event_name"),
    col("event.match_number").alias("event_match_number"),
    col("event.group").alias("event_group"),
    col("event.stage").alias("event_stage"),
    size(col("innings")).alias("num_innings"),
)

(
    silver_matches_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(SILVER_MATCHES_TABLE)
)

print(f"silver.matches: {silver_matches_df.count()} rows")

# COMMAND ----------

from pyspark.sql.functions import posexplode, explode, expr, coalesce, lit, element_at, size as array_size

# Innings level: keep an ordinal (1st innings, 2nd innings, ... -- up
# to 4 for a Test) and denormalize the per-innings flags we want on
# every delivery in that innings. player_registry (a map, one per
# match) rides along through this whole explode chain so it's
# available for the id lookups in the final select below.
innings_exploded = (
    bronze_df.select(
        col("match_id"),
        col("competition"),
        col("player_registry"),
        posexplode(col("innings")).alias("innings_pos", "inn"),
    )
    .withColumn("innings_seq", col("innings_pos") + 1)
    .select(
        col("match_id"),
        col("competition"),
        col("player_registry"),
        col("innings_seq"),
        col("inn.team").alias("batting_team"),
        col("inn.powerplays").alias("powerplays"),
        col("inn.target.runs").alias("innings_target_runs"),
        col("inn.target.overs").alias("innings_target_overs"),
        coalesce(col("inn.super_over"), lit(False)).alias("is_super_over"),
        coalesce(col("inn.declared"), lit(False)).alias("is_declared"),
        coalesce(col("inn.forfeited"), lit(False)).alias("is_forfeited"),
        explode(col("inn.overs")).alias("ov"),
    )
)

overs_exploded = innings_exploded.select(
    "*",
    col("ov.over").alias("over_number"),
).select(
    col("match_id"), col("competition"), col("player_registry"), col("innings_seq"), col("batting_team"),
    col("powerplays"), col("innings_target_runs"), col("innings_target_overs"),
    col("is_super_over"), col("is_declared"), col("is_forfeited"),
    col("over_number"),
    posexplode(col("ov.deliveries")).alias("delivery_seq", "dl"),
)

deliveries_with_num = overs_exploded.withColumn(
    "delivery_num", col("dl.actual_delivery").cast("double")
)

silver_deliveries_df = deliveries_with_num.select(
    col("match_id"),
    col("competition"),
    col("innings_seq"),
    col("batting_team"),
    col("over_number"),
    col("delivery_seq"),
    col("dl.actual_delivery").alias("actual_delivery"),
    col("dl.batter").alias("batter"),
    element_at(col("player_registry"), col("dl.batter")).alias("batter_id"),
    col("dl.bowler").alias("bowler"),
    element_at(col("player_registry"), col("dl.bowler")).alias("bowler_id"),
    col("dl.non_striker").alias("non_striker"),
    element_at(col("player_registry"), col("dl.non_striker")).alias("non_striker_id"),
    coalesce(col("dl.runs.batter"), lit(0)).alias("runs_batter"),
    coalesce(col("dl.runs.extras"), lit(0)).alias("runs_extras"),
    coalesce(col("dl.runs.total"), lit(0)).alias("runs_total"),
    coalesce(col("dl.runs.non_boundary"), lit(False)).alias("non_boundary"),
    coalesce(col("dl.extras.byes"), lit(0)).alias("extras_byes"),
    coalesce(col("dl.extras.legbyes"), lit(0)).alias("extras_legbyes"),
    coalesce(col("dl.extras.noballs"), lit(0)).alias("extras_noballs"),
    coalesce(col("dl.extras.penalty"), lit(0)).alias("extras_penalty"),
    coalesce(col("dl.extras.wides"), lit(0)).alias("extras_wides"),
    (
        col("dl.wickets").isNotNull() & (array_size(col("dl.wickets")) > 0)
    ).alias("is_wicket"),
    col("dl.wickets").alias("wickets"),
    col("dl.review").alias("review"),
    col("dl.replacements").alias("replacements"),
    col("innings_target_runs"),
    col("innings_target_overs"),
    col("is_super_over"),
    col("is_declared"),
    col("is_forfeited"),
    # Objective, source-provided fact: which of this innings's declared
    # powerplay windows (if any) this delivery falls in. NOT a
    # "death overs" classification -- that's a strategy-defined
    # threshold, deliberately left for gold to decide.
    # get(), not element_at(): when a delivery falls outside every
    # declared powerplay window (the common case -- most deliveries,
    # and entire matches/competitions with no powerplays array at all),
    # filter(...) returns an empty array. element_at(empty_array, 1)
    # throws INVALID_ARRAY_INDEX under Databricks' default strict
    # indexing instead of returning NULL. get() is the tolerant
    # equivalent -- 0-indexed, returns NULL on out-of-bounds instead of
    # erroring, which is exactly the "no powerplay here" case.
    # pp.`from` backticked -- FROM is a reserved SQL keyword and the
    # bare dot-access parses ambiguously in Spark's SQL grammar.
    expr("""
        get(
            filter(powerplays, pp -> delivery_num >= pp.`from` AND delivery_num <= pp.to),
            0
        ).type
    """).alias("powerplay_type"),
)

(
    silver_deliveries_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("competition")
    .saveAsTable(SILVER_DELIVERIES_TABLE)
)

print(f"silver.deliveries: {silver_deliveries_df.count()} rows")

# COMMAND ----------

# Sanity checks: does every delivery trace back to a real match, and
# do the per-competition delivery counts look plausible (T20s should
# average roughly 240 deliveries/match, ODIs ~600, Tests much higher
# and more variable)?
display(
    spark.table(SILVER_DELIVERIES_TABLE)
    .groupBy("competition")
    .agg(
        expr("count(distinct match_id) as matches"),
        expr("count(*) as deliveries"),
        expr("round(count(*) / count(distinct match_id), 1) as avg_deliveries_per_match"),
    )
    .orderBy("competition")
)

# COMMAND ----------

# Coverage check: what fraction of deliveries got a real batter_id back
# from the registry lookup? Should be at or extremely close to 100% --
# a low number here means either the registry map is missing entries
# for some competition, or the name string on the delivery doesn't
# exactly match the name string used as the map key in that match's
# registry (both would be worth knowing about before trusting player_id
# downstream in gold).
display(
    spark.table(SILVER_DELIVERIES_TABLE)
    .groupBy("competition")
    .agg(
        expr("count(*) as deliveries"),
        expr("count(batter_id) as deliveries_with_batter_id"),
        expr("round(count(batter_id) * 100.0 / count(*), 2) as batter_id_coverage_pct"),
    )
    .orderBy("competition")
)

# COMMAND ----------

display(spark.table(SILVER_MATCHES_TABLE).limit(5))

# COMMAND ----------

display(spark.table(SILVER_DELIVERIES_TABLE).limit(10))

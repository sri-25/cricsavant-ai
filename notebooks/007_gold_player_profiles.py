# Databricks notebook source
# CricSavant AI -- Gold layer: comprehensive player profiles.
#
# WHY THIS EXISTS, on top of the tables 006 already built:
# 006 built form/phase/situational as SEPARATE tables, each answering
# one question. That's the right grain to compute at, but it's the
# wrong shape to hand a decision-maker: a real recruiter doesn't read
# "top 10 by economy" and stop -- they read innings played, average AND
# rate together, role fit, and recent form all at once, then judge for
# themselves. This notebook assembles that view: one row per player,
# every signal that matters folded in as columns, built by joining the
# tables 006 already computed (no ball-by-ball rework).
#
# ANCHORED ON RECENT FORM, not career: an auction is a bet on current
# form, so batter_profile/bowler_profile are built starting from
# batting_form_recent / bowling_form_recent (the ~18-month, shrinkage-
# adjusted tables from 006), with career numbers joined in alongside
# as context, not as the primary sort.
#
# WHAT THIS DELIBERATELY DOES NOT CLAIM:
#   - Bowling style (pace/spin/wrist/finger) -- NOT in Cricsheet at
#     all, not inferred, not guessed. Stays on the post-submission
#     backlog (external reference data keyed off registry player_id).
#   - Batting handedness -- same, not in Cricsheet, not inferred here.
#   - usual_batting_position and likely_keeper_signal ARE computed
#     here, but both are DERIVED signals (crease-arrival order;
#     stumping-fielder frequency), not fields Cricsheet states
#     outright. Labeled as such, not presented as source fact.
#   - bowler_type (strike / containment / balanced) is a heuristic
#     label from comparing percentile rank on two metrics, not a
#     invented composite score -- the raw economy and bowling_strike_rate
#     numbers it's based on are still there for anyone to judge
#     differently.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

deliveries_df = spark.table("cricsavant.silver.deliveries")
bronze_df = spark.table("cricsavant.raw.bronze_matches")

T20_LEAGUES = ["IPL", "BBL", "PSL", "CPL", "SA20", "ILT20", "T20I"]

# Same batter_key/bowler_key derivation as 006 (coalesce real registry
# id, falling back to a name-prefixed synthetic key only when a name
# didn't resolve) -- recomputed here since it's a derived concept, not
# a stored silver column. See 006's PLAYER IDENTITY note for why this
# matters.
deliveries_keyed = deliveries_df.withColumn(
    "batter_key", F.coalesce(F.col("batter_id"), F.concat(F.lit("name:"), F.col("batter")))
).withColumn(
    "bowler_key", F.coalesce(F.col("bowler_id"), F.concat(F.lit("name:"), F.col("bowler")))
)

# COMMAND ----------

# Usual batting position: NOT a Cricsheet field -- derived from the
# actual order players first appear at the crease within each innings.
# Median (not mode) across a player's innings, since mode needs no
# ties-handling decision and median is just as honest a summary of
# "where do they usually bat."
first_appearance = (
    deliveries_keyed
    .filter(F.col("competition").isin(T20_LEAGUES))
    .groupBy("match_id", "innings_seq", "batter_key")
    .agg(F.min(F.col("over_number") * 1000 + F.col("delivery_seq")).alias("first_ball_ordinal"))
)

position_window = Window.partitionBy("match_id", "innings_seq").orderBy("first_ball_ordinal")
batting_position_per_innings = first_appearance.withColumn(
    "batting_position", F.row_number().over(position_window)
)

batting_position_summary = (
    batting_position_per_innings
    .groupBy("batter_key")
    .agg(
        F.expr("percentile_approx(batting_position, 0.5)").alias("usual_batting_position"),
        F.count("*").alias("position_sample_innings"),
    )
)

# COMMAND ----------

# Likely-keeper signal: NOT a Cricsheet field -- inferred from who
# most often executes a stumping as the credited fielder (only the
# keeper can stump). Resolved to a real registry id by rejoining
# bronze's player_registry map on match_id (fielder names were never
# threaded through 005 the way batter/bowler/non_striker were, so this
# does that resolution fresh, scoped to just this one signal, without
# needing another 004/005 rerun).
match_registry = bronze_df.select("match_id", "player_registry")

stumping_fielders = (
    deliveries_df
    .filter(F.col("competition").isin(T20_LEAGUES))
    .select("match_id", F.explode("wickets").alias("wk"))
    .filter(F.col("wk.kind") == "stumped")
    .select("match_id", F.explode("wk.fielders").alias("fielder"))
    .select("match_id", F.col("fielder.name").alias("fielder_name"))
    .join(match_registry, on="match_id", how="left")
    .withColumn(
        "fielder_key",
        F.coalesce(
            F.element_at(F.col("player_registry"), F.col("fielder_name")),
            F.concat(F.lit("name:"), F.col("fielder_name")),
        ),
    )
    .groupBy("fielder_key")
    .agg(F.count("*").alias("likely_keeper_signal"))
)

# COMMAND ----------

# Phase splits, long -> wide (one column set per phase instead of one
# row per phase) so they fold into a single profile row per player.
batting_phase_splits = spark.table("cricsavant.gold.batting_phase_splits")
bowling_phase_splits = spark.table("cricsavant.gold.bowling_phase_splits")

batting_phase_wide = (
    batting_phase_splits
    .groupBy("batter_key")
    .pivot("phase", ["powerplay", "middle", "death"])
    .agg(
        F.first("strike_rate").alias("sr"),
        F.first("balls_faced").alias("balls"),
    )
)

bowling_phase_wide = (
    bowling_phase_splits
    .groupBy("bowler_key")
    .pivot("phase", ["powerplay", "middle", "death"])
    .agg(
        F.first("economy").alias("economy"),
        F.first("balls_bowled").alias("balls"),
    )
)

# COMMAND ----------

# gold.batter_profile -- recent form as the anchor row, everything else
# joined in as columns.
batting_recent = spark.table("cricsavant.gold.batting_form_recent")
batting_career = spark.table("cricsavant.gold.batting_form_t20_leagues")
batting_situational = spark.table("cricsavant.gold.batting_situational_profile")

batter_profile = (
    batting_recent.select(
        F.col("batter_key"),
        F.col("player_name"),
        F.col("innings").alias("recent_innings"),
        F.col("runs").alias("recent_runs"),
        F.col("balls_faced").alias("recent_balls_faced"),
        F.col("average").alias("recent_average"),
        F.col("strike_rate").alias("recent_strike_rate"),
        F.col("regressed_strike_rate"),
        F.col("not_out_pct").alias("recent_not_out_pct"),
        F.col("boundary_pct").alias("recent_boundary_pct"),
    )
    .join(
        batting_career.select(
            F.col("batter_key"),
            F.col("innings").alias("career_innings"),
            F.col("runs").alias("career_runs"),
            F.col("average").alias("career_average"),
            F.col("strike_rate").alias("career_strike_rate"),
        ),
        on="batter_key", how="left",
    )
    .join(batting_position_summary, on="batter_key", how="left")
    .join(
        batting_situational.select(
            "batter_key",
            F.col("chase_sr"), F.col("defend_sr"),
            F.col("close_match_sr"), F.col("knockout_sr"), F.col("finisher_pct"),
        ),
        on="batter_key", how="left",
    )
    .join(
        batting_phase_wide.select(
            "batter_key",
            F.col("powerplay_sr"), F.col("powerplay_balls"),
            F.col("middle_sr"), F.col("middle_balls"),
            F.col("death_sr"), F.col("death_balls"),
        ),
        on="batter_key", how="left",
    )
    .join(
        stumping_fielders.select(F.col("fielder_key").alias("batter_key"), "likely_keeper_signal"),
        on="batter_key", how="left",
    )
    .withColumn("likely_keeper_signal", F.coalesce(F.col("likely_keeper_signal"), F.lit(0)))
)

(
    batter_profile.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable("cricsavant.gold.batter_profile")
)
print("gold.batter_profile:", batter_profile.count(), "rows")

# COMMAND ----------

# gold.bowler_profile -- same anchor pattern, plus the strike-vs-
# containment role read.
bowling_recent = spark.table("cricsavant.gold.bowling_form_recent")
bowling_career = spark.table("cricsavant.gold.bowling_form_t20_leagues")
bowling_situational = spark.table("cricsavant.gold.bowling_situational_profile")

bowler_profile_base = (
    bowling_recent.select(
        F.col("bowler_key"),
        F.col("player_name"),
        F.col("innings").alias("recent_innings"),
        F.col("wickets").alias("recent_wickets"),
        F.col("balls_bowled").alias("recent_balls_bowled"),
        F.col("runs_conceded").alias("recent_runs_conceded"),
        F.col("economy").alias("recent_economy"),
        F.col("regressed_economy"),
        F.col("bowling_strike_rate").alias("recent_bowling_strike_rate"),
        F.col("bowling_average").alias("recent_bowling_average"),
        F.col("dot_pct").alias("recent_dot_pct"),
    )
    .join(
        bowling_career.select(
            F.col("bowler_key"),
            F.col("innings").alias("career_innings"),
            F.col("wickets").alias("career_wickets"),
            F.col("economy").alias("career_economy"),
            F.col("bowling_strike_rate").alias("career_bowling_strike_rate"),
        ),
        on="bowler_key", how="left",
    )
    .join(
        bowling_situational.select(
            "bowler_key",
            F.col("chase_economy"), F.col("close_match_economy"), F.col("knockout_economy"),
        ),
        on="bowler_key", how="left",
    )
    .join(
        bowling_phase_wide.select(
            "bowler_key",
            F.col("powerplay_economy"), F.col("powerplay_balls"),
            F.col("middle_economy"), F.col("middle_balls"),
            F.col("death_economy"), F.col("death_balls"),
        ),
        on="bowler_key", how="left",
    )
)

# Strike vs containment: percentile rank each qualified bowler on
# regressed_economy (lower = better) and recent_bowling_strike_rate
# (lower = better, i.e. fewer balls per wicket). ROLE_GAP_THRESHOLD is
# the one tunable knob -- how much better one percentile needs to be
# than the other before calling it a distinct role rather than
# "balanced." Both raw numbers stay on the table regardless of the
# label, so anyone can judge differently.
ROLE_GAP_THRESHOLD = 0.15

role_window_economy = Window.orderBy("regressed_economy")
role_window_strike_rate = Window.orderBy("recent_bowling_strike_rate")

bowler_profile = (
    bowler_profile_base
    .withColumn("economy_percentile", F.round(F.percent_rank().over(role_window_economy), 3))
    .withColumn("strike_rate_percentile", F.round(F.percent_rank().over(role_window_strike_rate), 3))
    .withColumn(
        "bowler_type",
        F.when(F.col("recent_wickets") == 0, F.lit(None))
        .when((F.col("strike_rate_percentile") + ROLE_GAP_THRESHOLD) < F.col("economy_percentile"), F.lit("strike bowler"))
        .when((F.col("economy_percentile") + ROLE_GAP_THRESHOLD) < F.col("strike_rate_percentile"), F.lit("containment bowler"))
        .otherwise(F.lit("balanced")),
    )
)

(
    bowler_profile.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable("cricsavant.gold.bowler_profile")
)
print("gold.bowler_profile:", bowler_profile.count(), "rows")

# COMMAND ----------

# Verification: pull a few well-known names directly (not a ranking --
# a lookup) and eyeball whether the full profile reads sanely.
print("Bowler profile lookup -- Bumrah:")
display(spark.table("cricsavant.gold.bowler_profile").filter(F.col("player_name").contains("Bumrah")))

print("Bowler profile lookup -- Rashid Khan (should read as a strike bowler if the role tag is working):")
display(spark.table("cricsavant.gold.bowler_profile").filter(F.col("player_name").contains("Rashid Khan")))

print("Batter profile lookup -- MS Dhoni (should show a high usual_batting_position and a nonzero likely_keeper_signal):")
display(spark.table("cricsavant.gold.batter_profile").filter(F.col("player_name").contains("Dhoni")))

print("Bowler type breakdown -- how many strike / containment / balanced bowlers qualified:")
display(spark.table("cricsavant.gold.bowler_profile").groupBy("bowler_type").count())

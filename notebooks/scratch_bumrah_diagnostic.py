# Databricks notebook source
# Scratch diagnostic -- not part of the pipeline. Paste into a notebook
# cell and run. Checks one well-known player across three levels to
# find out whether he's missing from the data entirely, present but
# with wrong numbers, or present-and-correct-but-outranked (which would
# confirm the small-sample-noise explanation rather than a bug).

from pyspark.sql import functions as F
from pyspark.sql.window import Window

NAME_SEARCH = "Bumrah"  # swap for any player you want to check

# COMMAND ----------

# Level 1: does this name even show up in silver -- and does it resolve
# to a real registry id (not a null/unresolved fallback)?
print("Level 1 -- silver.deliveries, raw name match:")
display(
    spark.table("cricsavant.silver.deliveries")
    .filter(F.col("bowler").contains(NAME_SEARCH))
    .select("bowler", "bowler_id", "competition")
    .distinct()
)

# COMMAND ----------

# Level 2: gold.bowling_innings -- how many matches, which competitions,
# what's his per-match wicket/economy spread look like.
print("Level 2 -- gold.bowling_innings, per-match rows:")
display(
    spark.table("cricsavant.gold.bowling_innings")
    .filter(F.col("bowler").contains(NAME_SEARCH))
    .select("match_id", "competition", "bowler", "bowler_key", "runs_conceded", "balls_bowled", "wickets", "economy", "match_date")
    .orderBy(F.desc("match_date"))
)

# COMMAND ----------

# Level 3: does he appear in the recent-form and t20-leagues summary
# tables, and if so, where would he actually rank?
print("Level 3a -- bowling_form_recent row for this player:")
display(spark.table("cricsavant.gold.bowling_form_recent").filter(F.col("player_name").contains(NAME_SEARCH)))

print("Level 3b -- his rank position by regressed_economy among ALL qualified recent-form bowlers:")
display(
    spark.table("cricsavant.gold.bowling_form_recent")
    .withColumn("rank", F.row_number().over(Window.orderBy("regressed_economy")))
    .filter(F.col("player_name").contains(NAME_SEARCH) | (F.col("rank") <= 10))
    .orderBy("rank")
)

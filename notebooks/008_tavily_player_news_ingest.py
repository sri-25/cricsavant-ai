# Databricks notebook source
# CricSavant AI -- Tavily player news ingestion.
#
# Satisfies two of the project's fixed requirements at once: third-
# party API integration (Tavily) and unstructured data processing
# (news article text, not structured ball-by-ball data).
#
# SCOPE: a shortlist built from gold.batter_profile / gold.bowler_profile
# (from 007) -- not every player Cricsheet has ever recorded. An IPL
# auction works off a defined shortlist, not an encyclopedia of every
# cricketer alive. The shortlist is a union of two lenses (most active
# recently, and best recent performer by the regressed rate stats) so
# neither pure playing volume nor pure form alone decides who's
# covered -- see the reasoning where the constants are defined below.
# This is still a Cricsheet-derived stopgap, not the real answer:
# once Phase 3 builds the actual Lakebase player_pool table (the
# explicitly-defined auction shortlist), that becomes the real source
# of truth for who gets news coverage.
#
# IDEMPOTENCY: same signature-checking instinct as bronze, adapted for
# an API that doesn't expose an ETag -- skip a player if we already
# fetched articles for them within REFRESH_WINDOW_DAYS, so a rerun
# doesn't burn Tavily quota re-fetching news that's still fresh.
#
# TAVILY_API_KEY must already exist as a Databricks secret (scope
# "cricsavant", key "tavily_api_key") -- set up via the CLI or workspace
# UI, never pasted into a notebook or chat.

# COMMAND ----------

%pip install tavily-python -q
dbutils.library.restartPython()

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.raw")

ARTICLES_TABLE = "cricsavant.raw.player_news_articles"
REFRESH_WINDOW_DAYS = 7
ARTICLES_PER_PLAYER = 5

# COMMAND ----------

from pyspark.sql import functions as F

# Player shortlist -- two lenses, not one, since "most games played
# recently" and "best recent performer" are genuinely different
# questions and neither alone is a fair proxy for "who should be
# covered." A durable-but-unremarkable player who racked up a lot of
# domestic matches shouldn't crowd out a standout who played fewer
# recent games (injury layoff, only turning out for marquee
# tournaments, etc). This is still a Cricsheet-stats-derived stopgap,
# not the real answer -- once Phase 3 builds the actual Lakebase
# player_pool table (the real, explicitly-defined auction shortlist),
# THAT becomes the source of truth for who gets news coverage, not an
# inferred ranking. Both N's below are adjustable constants.
TOP_N_BY_ACTIVITY = 100  # most recent innings played -- regular starters
TOP_N_BY_QUALITY = 75    # best regressed rate stat, min 60 balls -- standouts even with a lighter recent workload

batter_form = spark.table("cricsavant.gold.batter_profile")
bowler_form = spark.table("cricsavant.gold.bowler_profile")

active_batters = batter_form.orderBy(F.desc("recent_innings")).limit(TOP_N_BY_ACTIVITY).select(
    F.col("batter_key").alias("player_key"), "player_name"
)
quality_batters = (
    batter_form.filter(F.col("recent_balls_faced") >= 60)
    .orderBy(F.desc("regressed_strike_rate"))
    .limit(TOP_N_BY_QUALITY)
    .select(F.col("batter_key").alias("player_key"), "player_name")
)
active_bowlers = bowler_form.orderBy(F.desc("recent_innings")).limit(TOP_N_BY_ACTIVITY).select(
    F.col("bowler_key").alias("player_key"), "player_name"
)
quality_bowlers = (
    bowler_form.filter(F.col("recent_balls_bowled") >= 60)
    .orderBy(F.asc("regressed_economy"))
    .limit(TOP_N_BY_QUALITY)
    .select(F.col("bowler_key").alias("player_key"), "player_name")
)

player_pool = (
    active_batters.unionByName(quality_batters)
    .unionByName(active_bowlers)
    .unionByName(quality_bowlers)
    .dropDuplicates(["player_key"])
)

players_to_fetch = [(r["player_key"], r["player_name"]) for r in player_pool.collect()]
print(f"Player shortlist: {len(players_to_fetch)} players "
      f"(union of most-active and best-recent-performer, both batting and bowling)")

# COMMAND ----------

# Skip players already refreshed recently.
table_exists = spark.catalog.tableExists(ARTICLES_TABLE)
recently_covered = set()
if table_exists:
    recently_covered = {
        r["player_key"] for r in
        spark.table(ARTICLES_TABLE)
        .filter(F.col("ingested_at") >= F.date_sub(F.current_date(), REFRESH_WINDOW_DAYS))
        .select("player_key").distinct().collect()
    }
    print(f"{len(recently_covered)} players already have articles fetched within the last {REFRESH_WINDOW_DAYS} days -- skipping those.")

players_to_fetch = [p for p in players_to_fetch if p[0] not in recently_covered]
print(f"Fetching for {len(players_to_fetch)} players this run.")

# COMMAND ----------

import time
from datetime import datetime, timezone
from tavily import TavilyClient
from pyspark.sql import Row

tavily = TavilyClient(api_key=dbutils.secrets.get(scope="cricsavant", key="tavily_api_key"))

rows = []
succeeded, failed = [], []

for player_key, player_name in players_to_fetch:
    try:
        result = tavily.search(
            query=f"{player_name} cricket form news 2026",
            max_results=ARTICLES_PER_PLAYER,
            search_depth="basic",
            include_raw_content=True,
        )
        n = 0
        for item in result.get("results", []):
            rows.append(Row(
                player_key=player_key,
                player_name=player_name,
                title=item.get("title"),
                url=item.get("url"),
                content=item.get("raw_content") or item.get("content"),
                tavily_score=float(item.get("score", 0.0)),
                ingested_at=datetime.now(timezone.utc),
            ))
            n += 1
        succeeded.append((player_name, n))
        time.sleep(0.5)  # light pacing, not aggressive -- Tavily has its own rate limits
    except Exception as e:
        failed.append((player_name, str(e)))

print(f"Succeeded: {len(succeeded)} players, {len(rows)} articles total")
if failed:
    print(f"Failed: {len(failed)} players")
    for name, err in failed[:10]:
        print(f"  {name}: {err[:200]}")

# COMMAND ----------

# Vector Search's Delta Sync Index (built in 009) requires a genuinely
# unique primary key per row -- url alone isn't safe (the same article
# can legitimately mention, and so get pulled in for, more than one
# player). article_id is a deterministic hash of player_key+url, so
# the same article for the same player always gets the same id even
# across reruns, rather than duplicating.
if rows:
    articles_df = spark.createDataFrame(rows).withColumn(
        "article_id", F.sha2(F.concat_ws("|", F.col("player_key"), F.col("url")), 256)
    )
    (
        articles_df.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(ARTICLES_TABLE)
    )
    # CDF is what Vector Search's Delta Sync Index needs to stay
    # incrementally updated as new articles land, rather than
    # re-embedding the whole table every time.
    spark.sql(f"ALTER TABLE {ARTICLES_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    print(f"Wrote {articles_df.count()} rows to {ARTICLES_TABLE}")
else:
    print("Nothing new to write this run.")

# COMMAND ----------

# One-time repair: the very first run of this notebook (before this
# fix) wrote rows with no article_id at all. Backfill it in, harmless
# and skipped automatically on every future run once every row has one.
existing_cols = spark.table(ARTICLES_TABLE).columns
needs_backfill = (
    "article_id" not in existing_cols
    or spark.table(ARTICLES_TABLE).filter(F.col("article_id").isNull()).limit(1).count() > 0
)
if needs_backfill:
    backfilled = spark.table(ARTICLES_TABLE).withColumn(
        "article_id",
        F.coalesce(F.col("article_id"), F.sha2(F.concat_ws("|", F.col("player_key"), F.col("url")), 256))
        if "article_id" in existing_cols else
        F.sha2(F.concat_ws("|", F.col("player_key"), F.col("url")), 256),
    )
    (
        backfilled.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(ARTICLES_TABLE)
    )
    spark.sql(f"ALTER TABLE {ARTICLES_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    print("Backfilled article_id for pre-existing rows.")

# COMMAND ----------

display(
    spark.table(ARTICLES_TABLE)
    .groupBy("player_key", "player_name")
    .agg(F.count("*").alias("articles"), F.max("ingested_at").alias("last_fetched"))
    .orderBy(F.desc("last_fetched"))
    .limit(20)
)

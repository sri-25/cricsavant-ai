# Databricks notebook source
# CricSavant AI -- Bronze ingestion, walking skeleton on IPL only.
#
# Cricsheet ships one JSON file per match, nested (info / innings /
# overs / deliveries). This proves the download + landing + Spark
# read pattern on a single competition before we generalize to the
# full cross-format list (Tests, ODIs, T20Is, BBL, PSL, CPL, SA20,
# ILT20, etc.) -- see docs/PROJECT_PLAN.md Section 1.

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.raw")
spark.sql("CREATE VOLUME IF NOT EXISTS cricsavant.raw.landing")

VOLUME_PATH = "/Volumes/cricsavant/raw/landing"

# COMMAND ----------

import requests
import zipfile
import io
import os

url = "https://cricsheet.org/downloads/ipl_male_json.zip"
target_dir = f"{VOLUME_PATH}/ipl"
marker_path = f"{target_dir}/.source_signature"

# Idempotency guard, done correctly: a hardcoded file-count floor can't
# tell "already landed" apart from "landed but now stale" -- once we're
# past the floor it would skip forever, even after Cricsheet adds new
# matches to the zip. Instead, ask the server what the zip looks like
# right now via a HEAD request (near-free -- no file body is
# transferred) and compare its ETag/Content-Length/Last-Modified
# against what we recorded last time. Only re-download when that
# signature actually changed.
head = requests.head(url, timeout=30, allow_redirects=True)
head.raise_for_status()
remote_signature = "|".join([
    head.headers.get("ETag", ""),
    head.headers.get("Content-Length", ""),
    head.headers.get("Last-Modified", ""),
])

local_signature = None
if os.path.exists(marker_path):
    with open(marker_path) as f:
        local_signature = f.read().strip()

already_landed = (
    os.path.isdir(target_dir)
    and local_signature == remote_signature
    and len([f for f in os.listdir(target_dir) if f.endswith(".json")]) > 0
)

if already_landed:
    json_names = [f for f in os.listdir(target_dir) if f.endswith(".json")]
    print(f"Skipping download -- source unchanged, {len(json_names)} match files already in {target_dir}")
else:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    print(f"Downloaded {len(resp.content):,} bytes")

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    json_names = [n for n in zf.namelist() if n.endswith(".json")]
    print(f"Match files in zip: {len(json_names)}")

    os.makedirs(target_dir, exist_ok=True)
    for name in json_names:
        zf.extract(name, target_dir)

    with open(marker_path, "w") as f:
        f.write(remote_signature)

    print("Extracted to", target_dir)

# COMMAND ----------

# Let Spark infer the nested schema directly from the JSON files --
# this is the walking-skeleton check: does the structure parse cleanly?
raw_df = spark.read.option("multiLine", True).json(f"{target_dir}/*.json")
print("Matches read:", raw_df.count())
raw_df.printSchema()

# COMMAND ----------

display(raw_df.limit(3))

# COMMAND ----------

from pyspark.sql.functions import col, regexp_extract, lit

# input_file_name() is blocked under Unity Catalog governance -- use the
# hidden _metadata column instead, which UC provides on any DataFrame
# read from files.
#
# Deliberately NOT selecting info.registry or info.players: Spark's
# schema inference turns these dictionary-shaped fields (player name ->
# id, team name -> roster) into a struct with one field PER NAME ever
# seen. That's not just bloat -- many of those names contain spaces and
# parentheses (e.g. "AB de Villiers", "Arshad Khan (2)"), and Delta
# rejects those characters in column names outright, which is exactly
# the DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES error you just hit.
# We don't need either field: which team a player belonged to in a
# given match is already recoverable from innings.team once we flatten
# to ball-by-ball in the silver step.
bronze_df = raw_df.select(
    col("_metadata.file_path").alias("source_file"),
    regexp_extract(col("_metadata.file_path"), r"([0-9]+)\.json$", 1).alias("match_id"),
    lit("IPL").alias("competition"),
    col("info.dates").alias("dates"),
    col("info.event").alias("event"),
    col("info.gender").alias("gender"),
    col("info.match_type").alias("match_type"),
    col("info.outcome").alias("outcome"),
    col("info.overs").alias("overs_per_innings"),
    col("info.player_of_match").alias("player_of_match"),
    col("info.season").alias("season"),
    col("info.team_type").alias("team_type"),
    col("info.teams").alias("teams"),
    col("info.toss").alias("toss"),
    col("info.venue").alias("venue"),
    col("innings").alias("innings"),
)

bronze_df.write.format("delta").mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("cricsavant.raw.bronze_matches_ipl")

print("Bronze rows written:", bronze_df.count())

# COMMAND ----------

# Note: teams/dates are now top-level columns (not nested under info)
# since bronze_df selected them out directly above.
display(spark.sql("SELECT match_id, competition, teams, dates FROM cricsavant.raw.bronze_matches_ipl LIMIT 5"))

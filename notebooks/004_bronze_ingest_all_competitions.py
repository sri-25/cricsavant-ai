# Databricks notebook source
# CricSavant AI -- Bronze ingestion, generalized across all active
# competitions.
#
# This is the production version of the walking skeleton proven in 002
# (IPL only). Nothing here is hardcoded per-competition: the list of
# competitions comes from cricsavant.raw.competition_config (seeded by
# 003), and this notebook loops over whatever rows are is_active = TRUE.
#
# SCHEMA STRATEGY -- the actual fix for the run of DELTA_FAILED_TO_MERGE
# / FIELD_NOT_FOUND / VOID-type errors hit while generalizing past IPL:
#
# Earlier versions of this notebook let Spark INFER the schema
# separately for each competition, then reactively patched whichever
# field broke a write next (registry/players, then miscounted_overs,
# then outcome's shape, then a null-type fallback bug of our own). That
# pattern doesn't converge -- there's always one more field a different
# match type happens to omit or shape differently.
#
# Instead, MATCH_SCHEMA below is one explicit, hand-declared schema
# built directly from Cricsheet's official JSON format spec
# (https://cricsheet.org/format/json/, format version 1.2.0), and every
# competition is read against it via spark.read.schema(...) rather than
# inferred. A field the spec marks optional (e.g. info.overs, which
# doesn't apply to Tests; info.outcome.by.innings, which only applies
# to Tests) simply comes back null for competitions that don't have it
# -- never a crash, never drift between competitions, no per-field
# patching needed. Fields we deliberately don't want (registry, players,
# miscounted_overs -- all dictionary-shaped, keyed by player/team/over
# number, and explicitly documented as such) are simply left out of the
# schema, so Spark ignores them at parse time rather than us having to
# exclude them after the fact.
#
# All competitions land in ONE shared table, cricsavant.raw.bronze_matches,
# partitioned by `competition`, written via Delta's `replaceWhere` so
# each write only touches the partition for the competition it just
# processed. Now that every partition is on the same explicit
# MATCH_SCHEMA (see the one-time migration this notebook did to get
# here), a competition whose source zip hasn't changed since last run
# is skipped entirely -- no download, no re-read, no re-write -- so a
# rerun where nothing changed is a fast no-op, and a rerun after one
# competition's data updates only reprocesses that one.
#
# Per-competition isolation: each competition's land+build+write is
# wrapped in try/except, so one competition's failure doesn't abort the
# run for the others. Final summary reports successes and failures
# explicitly.
#
# PLAYER IDENTITY MIGRATION (this run): info.registry.people is now
# included -- Cricsheet's own stable ID for each player name string
# used in a match, which downstream silver/gold uses to group by a
# real identity instead of trusting that a name string like "V Kohli"
# always refers to the same one person. It's declared as MapType, not
# left to inference, which is what makes it safe this time (a real map
# type doesn't expand into one struct field per key the way the
# original inferred `registry` field did -- that expansion is what
# caused the very first DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES crash
# back in 002). Because every already-landed competition needs this
# new column even though its source zip hasn't changed, FORCE_FULL_REBUILD
# below bypasses the normal incremental-skip for this one run -- flip
# it back to False afterward so future reruns stay incremental.

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.raw")
spark.sql("CREATE VOLUME IF NOT EXISTS cricsavant.raw.landing")

VOLUME_PATH = "/Volumes/cricsavant/raw/landing"
BRONZE_TABLE = "cricsavant.raw.bronze_matches"

# COMMAND ----------

from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, DoubleType,
    BooleanType, ArrayType, MapType,
)

DELIVERY_SCHEMA = StructType([
    StructField("actual_delivery", StringType()),
    StructField("batter", StringType()),
    StructField("bowler", StringType()),
    StructField("non_striker", StringType()),
    StructField("extras", StructType([
        StructField("byes", LongType()),
        StructField("legbyes", LongType()),
        StructField("noballs", LongType()),
        StructField("penalty", LongType()),
        StructField("wides", LongType()),
    ])),
    StructField("runs", StructType([
        StructField("batter", LongType()),
        StructField("extras", LongType()),
        StructField("total", LongType()),
        StructField("non_boundary", BooleanType()),
    ])),
    StructField("replacements", StructType([
        StructField("match", ArrayType(StructType([
            StructField("in", StringType()),
            StructField("out", StringType()),
            StructField("reason", StringType()),
            StructField("team", StringType()),
        ]))),
        StructField("role", ArrayType(StructType([
            StructField("in", StringType()),
            StructField("out", StringType()),
            StructField("reason", StringType()),
            StructField("role", StringType()),
        ]))),
    ])),
    StructField("review", StructType([
        StructField("batter", StringType()),
        StructField("by", StringType()),
        StructField("decision", StringType()),
        StructField("type", StringType()),  # observed in real data; not in the spec's field table but present in samples
        StructField("umpire", StringType()),
        StructField("umpires_call", BooleanType()),
    ])),
    StructField("wickets", ArrayType(StructType([
        StructField("kind", StringType()),
        StructField("player_out", StringType()),
        StructField("fielders", ArrayType(StructType([
            StructField("name", StringType()),
            StructField("substitute", BooleanType()),
        ]))),
    ]))),
])

OVER_SCHEMA = StructType([
    StructField("over", LongType()),
    StructField("deliveries", ArrayType(DELIVERY_SCHEMA)),
])

INNINGS_SCHEMA = StructType([
    StructField("team", StringType()),
    StructField("overs", ArrayType(OVER_SCHEMA)),
    StructField("absent_hurt", ArrayType(StringType())),
    StructField("declared", BooleanType()),
    StructField("forfeited", BooleanType()),
    StructField("super_over", BooleanType()),
    StructField("powerplays", ArrayType(StructType([
        StructField("from", DoubleType()),
        StructField("to", DoubleType()),
        StructField("type", StringType()),
    ]))),
    StructField("target", StructType([
        StructField("overs", DoubleType()),
        StructField("runs", LongType()),
    ])),
    StructField("penalty_runs", StructType([
        StructField("pre", LongType()),
        StructField("post", LongType()),
    ])),
    # miscounted_overs deliberately excluded -- Cricsheet's own spec
    # documents it as "an object, with each key being the number of an
    # over", i.e. genuinely dictionary-shaped, not a fixed field set.
])

INFO_SCHEMA = StructType([
    StructField("balls_per_over", LongType()),
    StructField("city", StringType()),
    StructField("dates", ArrayType(StringType())),
    StructField("event", StructType([
        StructField("name", StringType()),
        StructField("match_number", LongType()),
        StructField("group", StringType()),
        StructField("stage", StringType()),
    ])),
    StructField("gender", StringType()),
    StructField("match_type", StringType()),
    StructField("match_type_number", LongType()),
    StructField("officials", StructType([
        StructField("match_referees", ArrayType(StringType())),
        StructField("reserve_umpires", ArrayType(StringType())),
        StructField("tv_umpires", ArrayType(StringType())),
        StructField("umpires", ArrayType(StringType())),
    ])),
    StructField("outcome", StructType([
        StructField("result", StringType()),
        StructField("winner", StringType()),
        StructField("method", StringType()),
        StructField("eliminator", StringType()),
        StructField("bowl_out", StringType()),
        StructField("by", StructType([
            StructField("innings", LongType()),  # Test margin: "won by an innings and N runs"
            StructField("runs", LongType()),
            StructField("wickets", LongType()),
        ])),
    ])),
    StructField("overs", LongType()),  # optional -- not applicable to Tests
    StructField("player_of_match", ArrayType(StringType())),
    StructField("season", StringType()),
    StructField("team_type", StringType()),
    StructField("teams", ArrayType(StringType())),
    StructField("toss", StructType([
        StructField("decision", StringType()),
        StructField("winner", StringType()),
        StructField("uncontested", BooleanType()),
    ])),
    StructField("venue", StringType()),
    # registry.people IS included -- the one dictionary-shaped field we
    # actually need: Cricsheet's own stable ID per player name string
    # used in this match, letting downstream layers tell apart two real
    # players who share a name string, and recognize the same player
    # across name-string variants. Declared as MapType (a real
    # key-value type) rather than left to inference -- a map doesn't
    # expand into one struct field per key the way an undeclared
    # dictionary-shaped field does, which is what caused the original
    # DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES crash. `players` (the
    # team-name -> roster-array field) stays excluded -- not needed,
    # same reasoning as miscounted_overs above.
    StructField("registry", StructType([
        StructField("people", MapType(StringType(), StringType())),
    ])),
])

MATCH_SCHEMA = StructType([
    StructField("info", INFO_SCHEMA),
    StructField("innings", ArrayType(INNINGS_SCHEMA)),
])

# COMMAND ----------

import requests
import zipfile
import io
import os
from pyspark.sql.functions import col, lit, regexp_extract


def land_competition_files(slug: str, competition_code: str) -> tuple[str, bool]:
    """Download + extract a competition's Cricsheet zip into its own
    Volume subfolder, skipping the network round trip entirely if the
    source hasn't changed since last time (HEAD-request signature
    check -- see 002 for the full rationale). Returns (target_dir,
    source_unchanged) so the caller can also skip the Spark read/write
    when there's genuinely nothing new to process."""
    url = f"https://cricsheet.org/downloads/{slug}.zip"
    target_dir = f"{VOLUME_PATH}/{competition_code.lower()}"
    marker_path = f"{target_dir}/.source_signature"

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
        n = len([f for f in os.listdir(target_dir) if f.endswith(".json")])
        print(f"  [{competition_code}] source unchanged -- skipping download ({n} files already landed)")
        return target_dir, True

    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    json_names = [n for n in zf.namelist() if n.endswith(".json")]

    os.makedirs(target_dir, exist_ok=True)
    for name in json_names:
        zf.extract(name, target_dir)
    with open(marker_path, "w") as f:
        f.write(remote_signature)

    print(f"  [{competition_code}] downloaded {len(resp.content):,} bytes, extracted {len(json_names)} matches")
    return target_dir, False


def build_bronze_df(target_dir: str, competition_code: str):
    """Read a competition's landed JSON against the fixed MATCH_SCHEMA
    (no inference) and project it into the bronze shape."""
    raw_df = spark.read.schema(MATCH_SCHEMA).option("multiLine", True).json(f"{target_dir}/*.json")

    return raw_df.select(
        col("_metadata.file_path").alias("source_file"),
        regexp_extract(col("_metadata.file_path"), r"([0-9]+)\.json$", 1).alias("match_id"),
        lit(competition_code).alias("competition"),
        col("info.dates").alias("dates"),
        col("info.event").alias("event"),
        col("info.gender").alias("gender"),
        col("info.match_type").alias("match_type"),
        col("info.outcome.result").alias("outcome_result"),
        col("info.outcome.winner").alias("outcome_winner"),
        col("info.outcome.method").alias("outcome_method"),
        col("info.outcome.eliminator").alias("outcome_eliminator"),
        col("info.outcome.by.runs").alias("outcome_by_runs"),
        col("info.outcome.by.wickets").alias("outcome_by_wickets"),
        col("info.outcome.by.innings").alias("outcome_by_innings"),
        col("info.overs").alias("overs_per_innings"),
        col("info.player_of_match").alias("player_of_match"),
        col("info.season").alias("season"),
        col("info.team_type").alias("team_type"),
        col("info.teams").alias("teams"),
        col("info.toss").alias("toss"),
        col("info.venue").alias("venue"),
        col("info.registry.people").alias("player_registry"),
        col("innings").alias("innings"),
    )

# COMMAND ----------

# One-time: player_registry is a new column, so every already-landed
# competition needs to be reprocessed even though its source zip hasn't
# changed (the normal skip logic only checks the SOURCE, not our
# schema). Set back to False after this run completes successfully --
# ordinary reruns should go back to skipping unchanged competitions.
FORCE_FULL_REBUILD = True

active_competitions = (
    spark.table("cricsavant.raw.competition_config")
    .filter("is_active = TRUE")
    .select("competition_code", "cricsheet_slug", "competition_name")
    .collect()
)

print(f"Ingesting {len(active_competitions)} active competitions: "
      f"{', '.join(r['competition_code'] for r in active_competitions)}")

succeeded, failed = [], []
table_exists = spark.catalog.tableExists(BRONZE_TABLE)
existing_partitions = set()
if table_exists:
    existing_partitions = {
        r["competition"] for r in spark.table(BRONZE_TABLE).select("competition").distinct().collect()
    }

for row in active_competitions:
    code, slug, name = row["competition_code"], row["cricsheet_slug"], row["competition_name"]
    print(f"\n--- {name} ({code}) ---")

    try:
        target_dir, source_unchanged = land_competition_files(slug, code)

        if source_unchanged and code in existing_partitions and not FORCE_FULL_REBUILD:
            existing_count = spark.table(BRONZE_TABLE).filter(f"competition = '{code}'").count()
            print(f"  [{code}] already up to date in {BRONZE_TABLE} -- skipping rebuild ({existing_count} rows)")
            succeeded.append((code, existing_count))
            continue
        elif source_unchanged and FORCE_FULL_REBUILD:
            print(f"  [{code}] source unchanged, but FORCE_FULL_REBUILD is on -- reprocessing anyway")

        bronze_df = build_bronze_df(target_dir, code)
        row_count = bronze_df.count()

        writer = bronze_df.write.format("delta").mode("overwrite").option("mergeSchema", "true")
        if not table_exists:
            writer.partitionBy("competition").saveAsTable(BRONZE_TABLE)
            table_exists = True
        else:
            writer.option("replaceWhere", f"competition = '{code}'").saveAsTable(BRONZE_TABLE)

        existing_partitions.add(code)
        print(f"  [{code}] wrote {row_count} rows to {BRONZE_TABLE}")
        succeeded.append((code, row_count))

    except Exception as e:
        print(f"  [{code}] FAILED -- {type(e).__name__}: {e}")
        failed.append((code, str(e)))

# COMMAND ----------

print("Summary:")
for code, count in succeeded:
    print(f"  OK   {code}: {count} matches")
for code, err in failed:
    print(f"  FAIL {code}: {err[:200]}")
print(f"\nTotal written: {sum(c for _, c in succeeded)} matches across {len(succeeded)}/{len(active_competitions)} competitions")
if failed:
    print(f"{len(failed)} competition(s) failed -- see errors above.")

# COMMAND ----------

display(
    spark.table(BRONZE_TABLE)
    .groupBy("competition")
    .count()
    .orderBy("competition")
)

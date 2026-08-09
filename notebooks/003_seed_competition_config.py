# Databricks notebook source
# CricSavant AI -- Competition config seed.
#
# This is what makes the bronze pipeline parameterized instead of
# hardcoded: the list of competitions to ingest lives here as DATA, in
# a Delta table, not as a Python list embedded in the ingestion
# notebook's code. Adding a new competition later means one INSERT,
# not editing and redeploying a notebook. Toggling one off (e.g. a
# source that's temporarily broken) means one UPDATE, not a code
# change either.
#
# Run this once to create + seed the table. Safe to re-run (idempotent
# upsert via MERGE below).

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.raw")

spark.sql("""
CREATE TABLE IF NOT EXISTS cricsavant.raw.competition_config (
    competition_code   STRING NOT NULL,  -- short code used as the partition value, e.g. 'IPL'
    competition_name   STRING NOT NULL,  -- human-readable, e.g. 'Indian Premier League'
    cricsheet_slug      STRING NOT NULL,  -- filename stem on cricsheet.org/downloads/, e.g. 'ipl_male_json'
    gender              STRING NOT NULL,  -- 'male' -- scope is men's cricket per PROJECT_PLAN.md
    is_active           BOOLEAN NOT NULL,  -- flip to FALSE to pause a source without deleting config; always set explicitly on insert
    notes               STRING
) USING DELTA
""")

# COMMAND ----------

from pyspark.sql import Row

# Slugs verified directly against https://cricsheet.org/downloads/ (not
# guessed -- SA20 and ILT20 in particular don't follow the obvious
# pattern: SA20's slug is "sat", ILT20's is "ilt").
competitions = [
    Row(competition_code="IPL",   competition_name="Indian Premier League",  cricsheet_slug="ipl_male_json",   gender="male", is_active=True, notes="Primary competition -- walking skeleton proven in 002."),
    Row(competition_code="TEST",  competition_name="Test matches",           cricsheet_slug="tests_male_json", gender="male", is_active=True, notes=None),
    Row(competition_code="ODI",   competition_name="One-day internationals", cricsheet_slug="odis_male_json",  gender="male", is_active=True, notes=None),
    Row(competition_code="T20I",  competition_name="T20 internationals",     cricsheet_slug="t20s_male_json",  gender="male", is_active=True, notes=None),
    Row(competition_code="BBL",   competition_name="Big Bash League",        cricsheet_slug="bbl_male_json",   gender="male", is_active=True, notes=None),
    Row(competition_code="PSL",   competition_name="Pakistan Super League",  cricsheet_slug="psl_male_json",   gender="male", is_active=True, notes=None),
    Row(competition_code="CPL",   competition_name="Caribbean Premier League", cricsheet_slug="cpl_male_json", gender="male", is_active=True, notes=None),
    Row(competition_code="SA20",  competition_name="SA20",                   cricsheet_slug="sat_male_json",   gender="male", is_active=True, notes="Cricsheet slug is 'sat', not 'sa20'."),
    Row(competition_code="ILT20", competition_name="International League T20", cricsheet_slug="ilt_male_json", gender="male", is_active=True, notes="Cricsheet slug is 'ilt', not 'ilt20'."),
]

config_df = spark.createDataFrame(competitions)
config_df.createOrReplaceTempView("new_config")

spark.sql("""
MERGE INTO cricsavant.raw.competition_config AS target
USING new_config AS source
ON target.competition_code = source.competition_code
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")

# COMMAND ----------

display(spark.table("cricsavant.raw.competition_config").orderBy("competition_code"))

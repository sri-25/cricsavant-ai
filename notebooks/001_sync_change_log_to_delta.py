# Databricks notebook source
# CricSavant AI -- Lakebase change_log -> Delta sync
#
# This is our stand-in for native Lakebase CDF (not reachable on Free
# Edition -- see docs/PROJECT_PLAN.md Section 2). It reads new rows
# from Lakebase's change_log table via Spark's JDBC connector and
# appends them into a managed Delta table in Unity Catalog, tracking
# a watermark so re-runs only pick up what's new.
#
# Run this manually first to prove the mechanism works end to end.
# Once proven, this becomes a scheduled Job (every few minutes).

# COMMAND ----------

# Fill these in from the Lakebase App -> your project -> "Connect" button.
# Choose your own Databricks identity under "OAuth roles" in the Role
# dropdown, copy the host from the psql snippet, and click "Copy OAuth
# token" for the token. The token expires in 1 hour -- fine for this
# manual proof run. The real scheduled job will need a longer-lived
# native Postgres password role instead; that's a follow-up step, not
# blocking this test.

LAKEBASE_HOST = "REPLACE_ME.databricks.com"
LAKEBASE_DB = "databricks_postgres"
LAKEBASE_USER = "REPLACE_ME@example.com"
LAKEBASE_TOKEN = "REPLACE_ME_OAUTH_TOKEN"

# COMMAND ----------

jdbc_url = f"jdbc:postgresql://{LAKEBASE_HOST}:5432/{LAKEBASE_DB}?sslmode=require"

# Operational/audit tables (like this sync's output and its watermark)
# live in their own schema, separate from the curated gold tables the
# Spark pipeline will produce later -- keeps "raw audit log" and
# "analytics-ready" data from getting mixed together.
spark.sql("CREATE SCHEMA IF NOT EXISTS cricsavant.ops")

TARGET_TABLE = "cricsavant.ops.lb_change_log_history"
WATERMARK_TABLE = "cricsavant.ops.sync_watermark"

# COMMAND ----------

# Watermark: only fetch change_log rows past what we've already synced.
if spark.catalog.tableExists(WATERMARK_TABLE):
    last_id = spark.table(WATERMARK_TABLE).collect()[0]["last_event_id"]
else:
    last_id = 0

print(f"Last synced event_id: {last_id}")

query = f"(SELECT * FROM change_log WHERE event_id > {last_id} ORDER BY event_id) AS new_events"

new_df = (
    spark.read.format("jdbc")
    .option("url", jdbc_url)
    .option("dbtable", query)
    .option("user", LAKEBASE_USER)
    .option("password", LAKEBASE_TOKEN)
    .option("driver", "org.postgresql.Driver")
    .load()
)

new_count = new_df.count()
print(f"New events fetched: {new_count}")

# COMMAND ----------

if new_count > 0:
    new_df.write.format("delta").mode("append").saveAsTable(TARGET_TABLE)
    max_id = new_df.agg({"event_id": "max"}).collect()[0][0]
    spark.createDataFrame([(max_id,)], ["last_event_id"]) \
        .write.format("delta").mode("overwrite").saveAsTable(WATERMARK_TABLE)
    print(f"Synced through event_id {max_id}")
else:
    print("Nothing new to sync -- did you insert the test row in Lakebase first?")

# COMMAND ----------

display(spark.table(TARGET_TABLE))

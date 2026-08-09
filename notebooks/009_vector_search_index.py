# Databricks notebook source
# CricSavant AI -- Vector Search index for player news.
#
# Makes cricsavant.raw.player_news_articles searchable by meaning, not
# just keyword match. This is the retrieval half of what becomes the
# agent's search_player_news tool in Phase 4 -- same index gets reused
# there, nothing separate to build later.
#
# Delta Sync Index, not a manually-managed one: Databricks watches the
# source table via Change Data Feed and computes/refreshes the
# embeddings itself against databricks-gte-large-en (confirmed working
# in the Phase 2 capability check). We never touch the actual vectors.
#
# TRIGGERED sync, not continuous: this corpus updates in batches
# whenever 008 runs, not in real time, so refreshing manually after
# each ingestion run is the right cost/complexity tradeoff here --
# continuous sync costs more for no benefit at this scale.

# COMMAND ----------

%pip install databricks-vectorsearch -q
dbutils.library.restartPython()

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

ENDPOINT_NAME = "cricsavant_endpoint"
SOURCE_TABLE = "cricsavant.raw.player_news_articles"
INDEX_NAME = "cricsavant.raw.player_news_articles_index"

# COMMAND ----------

existing_endpoints = [e["name"] for e in vsc.list_endpoints().get("endpoints", [])]
if ENDPOINT_NAME not in existing_endpoints:
    vsc.create_endpoint(name=ENDPOINT_NAME, endpoint_type="STANDARD")
    print(f"Created endpoint '{ENDPOINT_NAME}'.")
else:
    print(f"Endpoint '{ENDPOINT_NAME}' already exists.")

# COMMAND ----------

existing_indexes = [i["name"] for i in vsc.list_indexes(ENDPOINT_NAME).get("vector_indexes", [])]
if INDEX_NAME not in existing_indexes:
    vsc.create_delta_sync_index(
        endpoint_name=ENDPOINT_NAME,
        source_table_name=SOURCE_TABLE,
        index_name=INDEX_NAME,
        pipeline_type="TRIGGERED",
        primary_key="article_id",
        embedding_source_column="content",
        embedding_model_endpoint_name="databricks-gte-large-en",
    )
    print(f"Created Delta Sync Index '{INDEX_NAME}'.")
else:
    # Not triggering sync() here even though the index already exists --
    # calling sync() while one's still initializing/running is itself an
    # error (exactly what happened last run). The polling cell below
    # will wait for whatever state it's actually in and only proceed
    # once it's genuinely idle and ready.
    print(f"Index '{INDEX_NAME}' already exists.")

# COMMAND ----------

# This cell does its own waiting -- no more guessing how long to pause
# or which cell to re-run. It polls the index's status every 20 seconds
# (up to 10 minutes) and only runs the actual search once Databricks
# reports it's ready. Just run this one cell and let it work; no need
# to babysit it or re-run anything above.
import time

index = vsc.get_index(ENDPOINT_NAME, INDEX_NAME)

READY_STATES = {"ONLINE", "ONLINE_NO_PENDING_UPDATE"}
max_wait_seconds = 600
waited = 0
state = "UNKNOWN"

while waited < max_wait_seconds:
    status = index.describe()
    state = status.get("status", {}).get("detailed_state", "UNKNOWN")
    print(f"  [{waited}s] index state: {state}")
    if state in READY_STATES:
        break
    time.sleep(20)
    waited += 20

if state not in READY_STATES:
    print(f"Still not ready after {max_wait_seconds}s (last state: {state}). "
          "This is unusual -- worth checking the index directly in the workspace UI "
          "(Catalog Explorer -> cricsavant.raw -> player_news_articles_index) before re-running.")
else:
    print("Index ready -- running the test search.")
    results = index.similarity_search(
        query_text="explosive death overs finisher in great recent form",
        columns=["player_name", "title", "url"],
        num_results=5,
    )
    for row in results.get("result", {}).get("data_array", []):
        print(row)

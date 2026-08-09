# Databricks notebook source
# Scratch diagnostic -- not part of the pipeline. Read-only, creates
# nothing persistent. Checks whether the two things Phase 2 (Tavily +
# unstructured article embeddings + retrieval) depends on actually work
# on this Free Edition account, before any real build effort goes in:
#
#   1. Foundation Model embedding endpoint, via the ai_query() SQL
#      function -- this is what turns article text into vectors.
#   2. Databricks Vector Search -- this is what makes those vectors
#      searchable at query time (the retrieval half of the agent's
#      search_player_news tool).
#
# If either is unavailable, we need to know NOW, not on day 2, so the
# design can adapt (e.g. a Delta-table-of-embeddings + brute-force
# cosine similarity fallback is entirely feasible at the scale a
# player-news corpus would actually be -- hundreds to low thousands of
# articles, not billions of vectors).

# COMMAND ----------

# Check 1: Foundation Model embedding endpoint reachable via SQL.
try:
    result = spark.sql("""
        SELECT ai_query(
            'databricks-gte-large-en',
            'Virat Kohli scored a century in the IPL final.'
        ) AS embedding_result
    """).collect()[0]["embedding_result"]
    print("EMBEDDING ENDPOINT: reachable.")
    print("Result type:", type(result))
    print("Preview:", str(result)[:200])
except Exception as e:
    print("EMBEDDING ENDPOINT: FAILED --", type(e).__name__, str(e)[:500])

# COMMAND ----------

# Check 2: Vector Search client + endpoint listing. First run installs
# the client library into the notebook's environment -- this was
# missing last time (ModuleNotFoundError), which says nothing yet about
# whether the underlying SERVICE is available, only that the Python
# package wasn't installed. restartPython() is required after %pip
# install before the new import will be visible.
%pip install databricks-vectorsearch -q
dbutils.library.restartPython()

# COMMAND ----------

try:
    from databricks.vector_search.client import VectorSearchClient
    vsc = VectorSearchClient()
    endpoints = vsc.list_endpoints()
    print("VECTOR SEARCH: client reachable.")
    print("Existing endpoints:", endpoints)
except Exception as e:
    print("VECTOR SEARCH: FAILED --", type(e).__name__, str(e)[:1000])

# COMMAND ----------

# Check 2b: can we actually CREATE a standard (non-serverless) vector
# search endpoint? list_endpoints() succeeding just means the API is
# reachable -- creation is where a Free Edition entitlement limit would
# actually show up. This creates a real endpoint if it succeeds, so
# only run it if Check 2 above passed.
try:
    vsc.create_endpoint(name="cricsavant_capability_test", endpoint_type="STANDARD")
    print("VECTOR SEARCH ENDPOINT CREATION: succeeded.")
except Exception as e:
    print("VECTOR SEARCH ENDPOINT CREATION: FAILED --", type(e).__name__, str(e)[:1000])

"""CricSavant AI -- Vector Search access (unstructured/news retrieval).

Thin wrapper around the Delta Sync Index built in
notebooks/009_vector_search_index.py. Uses the same VectorSearchClient
SDK the notebooks already validated (rather than hand-rolling the REST
call), so the query shape is proven, not guessed. In this App context
there's no dbutils/notebook token -- VectorSearchClient() with no args
resolves credentials the same way `Config()` does (env-based unified
auth), which is the same auto-injected DATABRICKS_CLIENT_ID/SECRET the
app already uses for the SQL warehouse and model-serving connections.

Needs, in addition to the app's existing 3 resources: USE CATALOG +
USE SCHEMA + SELECT on cricsavant.raw granted to the app's service
principal, AND "Can Query" on the cricsavant_endpoint Vector Search
endpoint (Compute > Vector Search > cricsavant_endpoint > Permissions).
Without those two grants this fails the same way the gold-schema
lookups did before that grant was added.
"""

VS_ENDPOINT_NAME = "cricsavant_endpoint"
VS_INDEX_NAME = "cricsavant.raw.player_news_articles_index"

_client = None


def _get_client():
    global _client
    if _client is None:
        from databricks.vector_search.client import VectorSearchClient
        _client = VectorSearchClient(disable_notice=True)
    return _client


def search_player_news(query: str, player_name: str = None, num_results: int = 5) -> dict:
    search_text = f"{player_name}: {query}" if player_name else query
    try:
        index = _get_client().get_index(VS_ENDPOINT_NAME, VS_INDEX_NAME)
        results = index.similarity_search(
            query_text=search_text,
            columns=["player_name", "title", "url"],
            num_results=num_results,
        )
        rows = results.get("result", {}).get("data_array", [])
        articles = [{"player_name": r[0], "title": r[1], "url": r[2]} for r in rows]
        return {"query": search_text, "article_count": len(articles), "articles": articles}
    except Exception as e:
        return {"query": search_text, "article_count": 0, "articles": [], "error": str(e)[:300]}

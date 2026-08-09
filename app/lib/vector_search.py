"""CricSavant AI -- Vector Search access (unstructured/news retrieval).

Thin wrapper around the Delta Sync Index built in
notebooks/009_vector_search_index.py.

AUTH: VectorSearchClient()'s no-args constructor does NOT reliably
pick up the app's service-principal credentials the same way
`Config()` does for the SQL warehouse / model-serving connections --
that assumption broke in testing ("authentication issues"). Instead,
this passes the service-principal client ID/secret through explicitly,
pulled from the same `Config()` the rest of the app already trusts.
Those values come from the DATABRICKS_CLIENT_ID/DATABRICKS_CLIENT_SECRET
env vars Databricks Apps auto-injects -- this is the documented pattern
for calling Vector Search from a service (as opposed to a notebook
with a personal token).

Needs, in addition to the app's existing 3 resources: USE CATALOG +
USE SCHEMA + SELECT on cricsavant.raw granted to the app's service
principal, AND "Can Use" on the cricsavant_endpoint Vector Search
endpoint (Compute > Vector Search > cricsavant_endpoint > Permissions
-- "Can Use" lets it query indexes on that endpoint; "Can Manage" is
for administering the endpoint itself and isn't needed here).
"""

VS_ENDPOINT_NAME = "cricsavant_endpoint"
VS_INDEX_NAME = "cricsavant.raw.player_news_articles_index"

_client = None


def _get_client():
    global _client
    if _client is None:
        from databricks.sdk.core import Config
        from databricks.vector_search.client import VectorSearchClient
        cfg = Config()
        _client = VectorSearchClient(
            workspace_url=cfg.host,
            service_principal_client_id=cfg.client_id,
            service_principal_client_secret=cfg.client_secret,
            disable_notice=True,
        )
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

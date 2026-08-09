# Databricks notebook source
# One-time setup: creates the "cricsavant" secret scope and stores the
# Tavily API key in it.
#
# SAFE TO COMMIT TO GITHUB -- this file never contains the actual key.
# The value is entered at runtime via the widget textbox below, which
# is separate from the notebook's saved source; only the empty widget
# declaration gets checked in, never what you type into it.
#
# To use: open this notebook, run the first cell so the widget appears
# at the top, type your Tavily key into the "Tavily API Key" box, then
# run the rest top to bottom.

dbutils.widgets.text("tavily_api_key", "", "Tavily API Key")

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
key_value = dbutils.widgets.get("tavily_api_key")

if not key_value:
    raise ValueError("Enter your Tavily API key in the 'tavily_api_key' widget above, then run this cell again.")

existing_scopes = [s.name for s in w.secrets.list_scopes()]
if "cricsavant" not in existing_scopes:
    w.secrets.create_scope(scope="cricsavant")
    print("Scope 'cricsavant' created.")
else:
    print("Scope 'cricsavant' already exists.")

w.secrets.put_secret(scope="cricsavant", key="tavily_api_key", string_value=key_value)
print("Secret stored -- 008_tavily_player_news_ingest.py can now read it.")

# COMMAND ----------

# Clear the widget's current value out of this session -- doesn't
# affect the saved file (which never had the real value in it), just
# tidies up so the key isn't sitting in the notebook's live state.
dbutils.widgets.remove("tavily_api_key")

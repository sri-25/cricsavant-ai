# Databricks notebook source
# One-time setup: stores the cricsavant_app Postgres role's password
# (created by sql/006_create_app_role.sql) as a Databricks secret.
#
# SAFE TO COMMIT TO GITHUB -- same pattern as setup_secrets.py. The
# real password is only ever entered into the widget textbox at
# runtime, never saved into this file's source.
#
# Prerequisite: you've already run sql/006_create_app_role.sql in the
# Lakebase SQL Editor, with a real generated password typed directly
# into the editor (not this file).
#
# To use: run the first cell so the widget appears, type the SAME
# password you used in sql/006 into the "Lakebase App Password" box,
# then run the rest top to bottom.

dbutils.widgets.text("lakebase_app_password", "", "Lakebase App Password")

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
password_value = dbutils.widgets.get("lakebase_app_password")

if not password_value:
    raise ValueError("Enter the cricsavant_app role's password in the widget above, then run this cell again.")

existing_scopes = [s.name for s in w.secrets.list_scopes()]
if "cricsavant" not in existing_scopes:
    w.secrets.create_scope(scope="cricsavant")
    print("Scope 'cricsavant' created.")
else:
    print("Scope 'cricsavant' already exists.")

w.secrets.put_secret(scope="cricsavant", key="lakebase_app_password", string_value=password_value)
print("Secret stored as cricsavant/lakebase_app_password -- Phase 4 tools can now read it.")

# COMMAND ----------

# Same non-secret connection details as 001/010 -- fill these in from
# the Lakebase App -> your project -> "Connect" button. Only the
# password is secret; host/db/role name are fine to have in code, but
# we'll pull them from a small config cell here so every future
# notebook references the same values instead of re-typing them.
LAKEBASE_HOST = "REPLACE_ME.databricks.com"
LAKEBASE_DB = "databricks_postgres"

dbutils.widgets.text("lakebase_host_check", LAKEBASE_HOST, "Lakebase Host (for verification only)")

# COMMAND ----------

# Verification: connect AS cricsavant_app (not your admin identity)
# using the stored secret, and confirm it can see what it should and
# nothing it shouldn't.
#
# Using pg8000 here, not psycopg2-binary -- psycopg2-binary's compiled
# C extension crashes the Python process outright (SIGABRT) on this
# serverless environment rather than raising a catchable error. pg8000
# is a pure-Python driver (no compiled extension), same DB-API surface,
# sidesteps the crash entirely.
%pip install pg8000 -q
dbutils.library.restartPython()

# COMMAND ----------

import pg8000

LAKEBASE_HOST = "REPLACE_ME.databricks.com"  # re-set after restart -- widget state doesn't survive the restart above
LAKEBASE_DB = "databricks_postgres"

conn = pg8000.connect(
    host=LAKEBASE_HOST,
    port=5432,
    database=LAKEBASE_DB,
    user="cricsavant_app",
    password=dbutils.secrets.get(scope="cricsavant", key="lakebase_app_password"),
    ssl_context=True,
)
cur = conn.cursor()

cur.execute("SELECT count(*) FROM franchises")
print("franchises visible:", cur.fetchone()[0])

cur.execute("SELECT count(*) FROM player_pool")
print("player_pool visible:", cur.fetchone()[0])

try:
    cur.execute("DROP TABLE change_log")
    print("UNEXPECTED: cricsavant_app was able to drop a table -- privileges are too broad, check sql/006.")
except Exception as e:
    conn.rollback()
    print("Expected failure (cricsavant_app correctly cannot drop tables):", str(e)[:150])

cur.close()
conn.close()

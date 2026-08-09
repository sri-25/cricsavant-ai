import os

import pandas as pd
import pg8000
import streamlit as st
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

# CricSavant AI -- Phase 5 spike.
#
# A Databricks App is a separate service from our notebooks -- no
# `spark` session, no `dbutils`. It reaches Unity Catalog through a SQL
# warehouse connection, reaches secrets/model endpoints through
# declared "resources" injected as env vars (see app.yaml), and
# authenticates as its OWN service principal (auto-injected
# DATABRICKS_CLIENT_ID/SECRET), not as the person using the app.
#
# This page proves the 3 connection paths independently before the
# real 4-tab app gets built on top of them. If a section below shows
# red, that's the specific thing to fix -- the other two sections
# passing tells you the problem is scoped to just that one piece.

st.set_page_config(page_title="CricSavant AI -- Spike Test", layout="wide")
st.title("CricSavant AI -- Integration Spike Test")
st.caption("Proving the 3 connection paths work before building the real app.")

cfg = Config()

# ---- Test 1: Unity Catalog (Lakehouse) via SQL warehouse ----
st.header("1. Unity Catalog -- gold.batter_profile via SQL warehouse")
try:
    warehouse_id = os.environ["WAREHOUSE_ID"]
    http_path = f"/sql/1.0/warehouses/{warehouse_id}"
    server_hostname = cfg.host.replace("https://", "").replace("http://", "")

    conn = sql.connect(
        server_hostname=server_hostname,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT player_name, recent_innings, regressed_strike_rate "
            "FROM cricsavant.gold.batter_profile ORDER BY recent_innings DESC LIMIT 5"
        )
        df = cur.fetchall_arrow().to_pandas()
    conn.close()
    st.success("Unity Catalog connection OK")
    st.dataframe(df)
except Exception as e:
    st.error(f"Unity Catalog connection FAILED: {e}")

# ---- Test 2: Lakebase via the cricsavant_app credential ----
st.header("2. Lakebase -- franchises via cricsavant_app + secret resource")
try:
    LAKEBASE_HOST = "ep-curly-dream-d85sia2d.database.us-east-2.cloud.databricks.com"
    LAKEBASE_DB = "databricks_postgres"
    lb_password = os.environ["LAKEBASE_APP_PASSWORD"]

    lb_conn = pg8000.connect(
        host=LAKEBASE_HOST,
        port=5432,
        database=LAKEBASE_DB,
        user="cricsavant_app",
        password=lb_password,
        ssl_context=True,
    )
    lb_cur = lb_conn.cursor()
    lb_cur.execute("SELECT count(*) FROM franchises")
    franchise_count = lb_cur.fetchone()[0]
    lb_cur.close()
    lb_conn.close()
    st.success(f"Lakebase connection OK -- {franchise_count} franchises visible")
except Exception as e:
    st.error(f"Lakebase connection FAILED: {e}")

# ---- Test 3: Foundation Model serving endpoint ----
st.header("3. Foundation Model endpoint -- chat completion")
try:
    chat_model = os.environ.get("CHAT_MODEL_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")
    w = WorkspaceClient()
    client = w.serving_endpoints.get_open_ai_client()
    response = client.chat.completions.create(
        model=chat_model,
        messages=[{"role": "user", "content": "Reply with exactly: CricSavant model connection OK"}],
        max_tokens=20,
    )
    st.success("Model serving connection OK")
    st.write(response.choices[0].message.content)
except Exception as e:
    st.error(f"Model serving connection FAILED: {e}")

st.divider()
st.caption("If all 3 sections above are green, the real app gets built on this foundation.")

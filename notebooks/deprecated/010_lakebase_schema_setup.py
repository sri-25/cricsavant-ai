# Databricks notebook source
# ============================================================
# DEPRECATED -- DO NOT RUN THIS NOTEBOOK.
#
# Real, cited schema + seed data already exists in sql/001-004
# (sql/001_lakebase_schema.sql, 002_seed_auction_rules.sql,
# 003_seed_player_pool.sql, 004_add_format_rules_context.sql).
# Those were written earlier, already have real BCCI-cited auction
# rules and the actual 369-player IPL 2026 shortlist (with pace/spin,
# capped status, real base prices), and are meant to be run directly
# in the Lakebase SQL Editor per their own header comments.
#
# This file predates that discovery and duplicates the same tables
# with generic, non-cited placeholder data. Left in place (not
# deleted) for reference only. Use sql/001-004 instead.
# ============================================================
#
# CricSavant AI -- Lakebase schema setup.
#
# Creates the operational tables Lakebase holds, per the split
# discussed earlier: small, write-heavy, transactionally-consistent
# state, the opposite of the large, read-heavy, batch-computed
# Cricsheet data sitting in the Lakehouse.
#
#   franchises        -- the teams in this auction, their purse
#   auction_rules      -- config (squad size limits, bid increments) as
#                         DATA, not hardcoded logic -- change a rule by
#                         updating a row, not editing code
#   player_pool         -- the actual defined auction shortlist. This
#                         REPLACES the Cricsheet-stats-inferred shortlist
#                         used to scope Tavily news pulls in 008 -- that
#                         was always a stopgap standing in for this real
#                         table. Seeded from the gold profiles as a
#                         starting point, but this is now the editable
#                         source of truth (add/drop players, adjust base
#                         prices by hand from here on).
#   franchise_roster    -- who bought whom, at what price
#   change_log          -- append-only event log of every write action.
#                         This is what 001_sync_change_log_to_delta.py
#                         reads from -- Lakebase's native CDF isn't
#                         reachable on Free Edition, so this table IS
#                         the CDC mechanism the project's requirement
#                         is built on.
#
# player_key in player_pool/franchise_roster is deliberately the SAME
# identity key gold.batter_profile/bowler_profile use (registry id, or
# the name-fallback key for the rare unresolved case) -- so the app and
# agent can join Lakebase's operational state straight into the
# Lakehouse's analytical gold tables with no separate mapping layer.
#
# Same manual-OAuth-token bootstrap as 001 for this one-time DDL run --
# hardening the credential for the ongoing scheduled sync is a
# separate next step, not blocking getting the schema created today.

# COMMAND ----------

%pip install psycopg2-binary -q
dbutils.library.restartPython()

# COMMAND ----------

# Fill these in from the Lakebase App -> your project -> "Connect"
# button, same as you did for 001. Token expires in 1 hour -- fine for
# this one-time run.
LAKEBASE_HOST = "REPLACE_ME.databricks.com"
LAKEBASE_DB = "databricks_postgres"
LAKEBASE_USER = "REPLACE_ME@example.com"
LAKEBASE_TOKEN = "REPLACE_ME_OAUTH_TOKEN"

# COMMAND ----------

import psycopg2

conn = psycopg2.connect(
    host=LAKEBASE_HOST,
    port=5432,
    dbname=LAKEBASE_DB,
    user=LAKEBASE_USER,
    password=LAKEBASE_TOKEN,
    sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()
print("Connected.")

# COMMAND ----------

DDL_STATEMENTS = {
    "franchises": """
        CREATE TABLE IF NOT EXISTS franchises (
            franchise_id SERIAL PRIMARY KEY,
            franchise_name TEXT NOT NULL UNIQUE,
            owner_name TEXT,
            total_purse NUMERIC(12,2) NOT NULL,
            remaining_purse NUMERIC(12,2) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
    "auction_rules": """
        CREATE TABLE IF NOT EXISTS auction_rules (
            rule_key TEXT PRIMARY KEY,
            rule_value TEXT NOT NULL,
            description TEXT
        )
    """,
    "player_pool": """
        CREATE TABLE IF NOT EXISTS player_pool (
            player_key TEXT PRIMARY KEY,
            player_name TEXT NOT NULL,
            base_price NUMERIC(12,2) NOT NULL,
            role TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            added_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
    "franchise_roster": """
        CREATE TABLE IF NOT EXISTS franchise_roster (
            roster_id SERIAL PRIMARY KEY,
            franchise_id INTEGER NOT NULL REFERENCES franchises(franchise_id),
            player_key TEXT NOT NULL REFERENCES player_pool(player_key) UNIQUE,
            purchase_price NUMERIC(12,2) NOT NULL,
            purchased_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
    "change_log": """
        CREATE TABLE IF NOT EXISTS change_log (
            event_id SERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
}

for name, stmt in DDL_STATEMENTS.items():
    cur.execute(stmt)
    print(f"OK: {name}")

print("Schema setup complete.")

# COMMAND ----------

# Seed auction_rules with sensible starting defaults -- config as data,
# adjustable later with a plain UPDATE, not a code change. Idempotent:
# safe to rerun this notebook without duplicating or clobbering rows
# you've since edited by hand.
DEFAULT_RULES = [
    ("max_squad_size", "25", "Maximum players a franchise can roster"),
    ("min_squad_size", "18", "Minimum players a franchise must roster"),
    ("min_bid_increment", "0.05", "Minimum bid increment, in crore"),
    ("default_total_purse", "100", "Default franchise purse, in crore"),
]

for rule_key, rule_value, description in DEFAULT_RULES:
    cur.execute(
        """
        INSERT INTO auction_rules (rule_key, rule_value, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (rule_key) DO NOTHING
        """,
        (rule_key, rule_value, description),
    )

print("Default auction rules seeded (existing rows left untouched).")

# COMMAND ----------

cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
print("Tables in Lakebase:")
for row in cur.fetchall():
    print(" -", row[0])

cur.execute("SELECT rule_key, rule_value, description FROM auction_rules ORDER BY rule_key")
print("\nauction_rules:")
for row in cur.fetchall():
    print(" -", row)

cur.close()
conn.close()

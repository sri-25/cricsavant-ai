-- =========================================================
-- CricSavant AI — dedicated, least-privilege Postgres role for the
-- agent/app to connect as (instead of your own admin identity).
-- =========================================================
-- Why: the OAuth-token pattern used in 001_sync_change_log_to_delta.py
-- and setup_secrets.py expires after 1 hour -- fine for a one-off
-- manual run, not fine for an agent you'll be calling repeatedly
-- during testing or a live demo. A native Postgres role with a
-- password doesn't expire, so this removes that failure mode for
-- Phase 4 onward.
--
-- Least privilege, not "grant everything": this role can read the
-- reference tables, read/write the roster (that's the actual auction
-- action), and append to change_log (the audit trail) -- but can't
-- touch auction_rules or player_pool, and can't drop/alter anything.
--
-- >>> PREREQUISITE (one-time, do this first): password-based Postgres
-- roles are OFF by default on a Lakebase instance. Go to Apps ->
-- Lakebase Postgres -> Provisioned -> your instance -> Edit -> turn on
-- "Enable Postgres Native Role Login" -> Save. This CREATE ROLE
-- statement will error until you do this.
--
-- (There's a separate "Add role" button on the instance's Roles page
-- -- that creates a DIFFERENT kind of role, tied to a Databricks
-- identity/service principal, still authenticated via an hourly-
-- expiring OAuth token. That's the right tool for letting a person or
-- service principal log in as themselves; it does not give us a
-- non-expiring credential, which is the actual problem being solved
-- here, so we want the plain password role below instead.)
--
-- >>> BEFORE RUNNING: replace REPLACE_ME_STRONG_PASSWORD below with a
-- real generated password IN THE SQL EDITOR ONLY -- do not type a real
-- password into this file and do not commit a real password to git.
-- Pick/generate the password, paste it into the editor, run this
-- script once, then immediately go store that same password via
-- notebooks/011_setup_lakebase_app_credential.py (which is git-safe,
-- same widget pattern as setup_secrets.py).

CREATE ROLE cricsavant_app WITH LOGIN PASSWORD 'REPLACE_ME_STRONG_PASSWORD';

GRANT CONNECT ON DATABASE databricks_postgres TO cricsavant_app;
GRANT USAGE ON SCHEMA public TO cricsavant_app;

-- Read-only reference data -- EXCEPT franchises.purse_remaining_cr,
-- which execute_player_bid must decrement on every successful bid.
-- Column-level grant keeps everything else on franchises (name,
-- owner_label, purse_total_cr, max_squad_size, max_overseas) locked.
GRANT SELECT ON franchises, auction_rules, player_pool TO cricsavant_app;
GRANT UPDATE (purse_remaining_cr) ON franchises TO cricsavant_app;

-- Read/write: this is the actual auction action (drafting a player)
GRANT SELECT, INSERT, UPDATE ON franchise_roster TO cricsavant_app;

-- Append-only audit trail -- no UPDATE/DELETE, matches its
-- append-only design in 001_lakebase_schema.sql
GRANT SELECT, INSERT ON change_log TO cricsavant_app;

-- Needed so INSERT can populate the BIGSERIAL primary keys on
-- franchise_roster.roster_id and change_log.event_id
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cricsavant_app;

-- Sanity check after running:
-- SELECT rolname FROM pg_roles WHERE rolname = 'cricsavant_app';

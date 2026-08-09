-- =========================================================
-- CricSavant AI — Lakebase (OLTP) schema, v1
-- =========================================================
-- Run this in the Lakebase SQL Editor against your cricsavant-oltp
-- project. Four tables, on purpose — kept lean for a 2-day build.
-- See docs/PROJECT_PLAN.md Section 2 for why there's no native
-- Change Data Feed here: it isn't reachable on Free Edition, so
-- change_log (table 4) is our own stand-in, read by a scheduled
-- Spark job into a Delta table.

-- ---------------------------------------------------------
-- 1. FRANCHISES
-- One row per franchise a user creates (the "bring your own
-- franchise" feature). Free Edition = one shared Lakebase project,
-- and there's no real auth system in scope for 2 days, so
-- owner_label is just a free-text label, not a login — fine for a
-- demo, worth knowing as a real limitation if this ever went further.
-- ---------------------------------------------------------
CREATE TABLE franchises (
    franchise_id        BIGSERIAL PRIMARY KEY,
    name                 TEXT NOT NULL UNIQUE,
    owner_label          TEXT,
    purse_total_cr        NUMERIC(10,2) NOT NULL CHECK (purse_total_cr > 0),
    purse_remaining_cr    NUMERIC(10,2) NOT NULL,
    max_squad_size        INT NOT NULL DEFAULT 25,
    max_overseas          INT NOT NULL DEFAULT 8,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active             BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------
-- 2. FRANCHISE_ROSTER
-- Every player a franchise has ever held, imported or auction-won.
-- Rows are never deleted, only marked 'released' — so this table is
-- both "current roster" (status='active') and the full acquisition
-- history/ledger in one place, which is why there's no separate
-- player_investments table.
--
-- player_name is a plain-text join key back to the Spark gold Delta
-- table (built from Cricsheet). That's a deliberate simplification —
-- fragile if names don't match exactly between the two sides — worth
-- a normalization pass later, not something to fix right now.
-- ---------------------------------------------------------
CREATE TABLE franchise_roster (
    roster_id         BIGSERIAL PRIMARY KEY,
    franchise_id       BIGINT NOT NULL REFERENCES franchises(franchise_id),
    player_name        TEXT NOT NULL,
    role               TEXT NOT NULL CHECK (role IN ('batter','bowler','all-rounder','wicketkeeper')),
    bowling_style      TEXT NOT NULL DEFAULT 'na' CHECK (bowling_style IN ('pace','spin','na')),
    is_overseas        BOOLEAN NOT NULL DEFAULT FALSE,
    acquisition_type   TEXT NOT NULL CHECK (acquisition_type IN ('imported','auction')),
    price_cr           NUMERIC(10,2) NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','released')),
    acquired_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at         TIMESTAMPTZ
);

CREATE INDEX idx_franchise_roster_franchise ON franchise_roster (franchise_id, status);

-- ---------------------------------------------------------
-- 3. AUCTION_RULES
-- Current BCCI rules — purse cap, squad size, overseas cap, RTM
-- cards. Deliberately NOT written to by the agent. One row per rule
-- version, each stamped with a source URL and when it was verified.
-- The agent reads the row where is_current = TRUE as always-on
-- context every turn; it never edits this table itself. This table
-- starts EMPTY on purpose — we populate it with real, cited BCCI
-- numbers as its own next step, not made up now just to fill a row.
-- ---------------------------------------------------------
CREATE TABLE auction_rules (
    rule_version              BIGSERIAL PRIMARY KEY,
    effective_from             DATE NOT NULL,
    max_purse_cr               NUMERIC(10,2) NOT NULL,
    max_squad_size             INT NOT NULL,
    min_squad_size             INT NOT NULL,
    max_overseas_players       INT NOT NULL,
    max_overseas_playing_xi    INT NOT NULL,
    rtm_cards_per_team         INT NOT NULL,
    notes                      TEXT,
    source_url                 TEXT NOT NULL,
    verified_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_current                  BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------
-- 4. CHANGE_LOG
-- Unified event feed: every data-changing write (a bid, a roster
-- import) AND every agent tool call (including reads), one row
-- each. This is what a scheduled Spark job reads on a timer and
-- appends into a Delta table in Unity Catalog — our stand-in for
-- native Lakebase CDF. result_status lets us count things like
-- "bids blocked by the rules validator," which is good evidence
-- the guardrail actually works, not just that it exists.
-- ---------------------------------------------------------
CREATE TABLE change_log (
    event_id       BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL CHECK (event_type IN ('data_change','tool_call')),
    table_name      TEXT,
    tool_name       TEXT,
    franchise_id    BIGINT REFERENCES franchises(franchise_id),
    payload         JSONB NOT NULL,
    result_status   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_change_log_created_at ON change_log (created_at);

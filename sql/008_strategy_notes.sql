-- =========================================================
-- CricSavant AI — strategy_notes: the agent's WRITE surface after the
-- practice Auction Console was dropped (user decision, product pivot
-- to franchise strategy). Replaces execute_player_bid as the capstone
-- "agent write tool": the agent (and the UI) save retention plans,
-- auction-target lists, and simulated XIs here, and every save is
-- also logged to change_log — so the Lakebase→Delta CDF sync
-- requirement keeps demonstrating real write traffic.
--
-- Run in the Lakebase SQL editor as the instance owner (same place
-- you ran 001/006/007).
-- =========================================================

CREATE TABLE IF NOT EXISTS strategy_notes (
    note_id      BIGSERIAL PRIMARY KEY,
    franchise_id INT REFERENCES franchises(franchise_id),
    note_type    TEXT NOT NULL,      -- 'retention_plan' | 'auction_targets' | 'playing_xi' | 'scouting' | 'general'
    content      TEXT NOT NULL,
    created_by   TEXT NOT NULL DEFAULT 'agent',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Same least-privilege stance as sql/006: the app role can read and
-- append, but not edit or delete history.
GRANT SELECT, INSERT ON strategy_notes TO cricsavant_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cricsavant_app;

-- Sanity check:
-- SELECT count(*) FROM strategy_notes;

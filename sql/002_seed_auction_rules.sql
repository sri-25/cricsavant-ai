-- =========================================================
-- CricSavant AI — seed auction_rules with the last officially
-- confirmed BCCI/IPL rule set.
-- =========================================================
-- These are the IPL 2026 mini-auction rules (Dec 16, 2025, Etihad
-- Arena, Abu Dhabi) — the auction that built squads for the season
-- that just finished. As of this writing, BCCI has not yet
-- officially announced IPL 2027 auction terms (expected ~Nov 2026),
-- so this is deliberately the most recent CONFIRMED rule set, not a
-- guess at what's next. Update this row (insert a new one, flip the
-- old one's is_current to FALSE) the moment BCCI actually announces
-- 2027 terms — don't just assume "same as last time."

UPDATE auction_rules SET is_current = FALSE WHERE is_current = TRUE;

INSERT INTO auction_rules (
    effective_from, max_purse_cr, max_squad_size, min_squad_size,
    max_overseas_players, max_overseas_playing_xi, rtm_cards_per_team,
    notes, source_url, is_current
) VALUES (
    '2025-12-16',
    125.00,
    25,
    18,
    8,
    4,
    0,  -- mini-auction year: no Right to Match cards (RTM is mega-auction only)
    'IPL 2026 mini-auction rules (last officially confirmed cycle as of Aug 2026). '
    'Overseas player salary effectively capped around Rs 18cr (tied to the highest '
    'retention price from the 2025 mega auction). 350 players shortlisted (240 Indian, '
    '110 overseas) competing for 77 total slots across 10 franchises, 31 of those '
    'slots reserved for overseas players. IPL 2027 auction rules (expected ~Nov 2026, '
    'likely another mini-auction) are NOT yet officially announced by BCCI as of this '
    'writing -- do not assume identical terms without checking.',
    'https://thesportstak.com/cricket/ipl/story/ipl-2026-auction-rules-explained-salary-caps-purse-limits-overseas-player-guideline-3220162-2025-12-11',
    TRUE
);

-- Sanity check after running:
-- SELECT * FROM auction_rules WHERE is_current = TRUE;

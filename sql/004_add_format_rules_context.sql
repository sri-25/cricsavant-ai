-- =========================================================
-- CricSavant AI -- extend auction_rules with match-format
-- knowledge (playing-XI composition, Impact Player, capped/
-- uncapped definitions).
-- =========================================================
-- These are NOT transactional constraints -- you can't "violate"
-- the playing-XI overseas limit by buying a player, only by how
-- you field a match squad later. But they matter just as much to
-- a buy decision (a 5th overseas seamer is bench depth, not a
-- guaranteed starter), so this is injected into the same agent
-- context as the hard auction rules, just kept in its own column
-- so the distinction between "hard constraint" and "strategic
-- knowledge" stays visible in the data model, not just in prose.

ALTER TABLE auction_rules ADD COLUMN IF NOT EXISTS format_rules_notes TEXT;

UPDATE auction_rules
SET format_rules_notes =
    'PLAYING XI: max 4 overseas players in the starting XI (matches '
    'max_overseas_playing_xi). IMPACT PLAYER (in effect for the IPL '
    '2025-27 regulations cycle): each team gets exactly one Impact '
    'Player substitution per match, swapping in for any player in the '
    'starting XI; once in, the Impact Player bats/bowls/fields with no '
    'restriction. This interacts with the overseas cap: if a team '
    'starts 4 overseas players, its Impact Player must be Indian (the '
    'on-field overseas count can never exceed 4, including via the '
    'Impact Player). If a team starts 3 or fewer overseas players, it '
    'may use an overseas player as its Impact Player. '
    'CAPPED VS UNCAPPED: general rule -- a player who has played at '
    'least one international match (Test/ODI/T20I) for their country '
    'is "capped"; otherwise "uncapped". IPL-specific twist for INDIAN '
    'players only: a capped Indian player is reclassified back to '
    '"uncapped" for retention/auction purposes if he has not played a '
    'Test/ODI/T20I starting-XI match AND has not held a BCCI central '
    'contract in the preceding 5 calendar years. This 5-year '
    'reclassification does NOT apply to overseas players -- for them, '
    'capped/uncapped is simply whether they have ever played one '
    'international match. Note: player_pool.capped_status reflects '
    'BCCI''s own official classification for each auction, not an '
    'independently recomputed value -- treat it as authoritative, '
    'don''t second-guess it against the 5-year rule yourself.'
WHERE is_current = TRUE;

-- Sanity check after running:
-- SELECT max_overseas_playing_xi, format_rules_notes FROM auction_rules WHERE is_current = TRUE;

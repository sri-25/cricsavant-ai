-- =========================================================
-- CricSavant AI -- add home_venue to franchises.
-- =========================================================
-- Needed for venue-aware retention analysis: a franchise's real home
-- ground, matched (fuzzily -- Cricsheet's venue strings vary in
-- naming across seasons, e.g. Delhi's ground has been called both
-- "Feroz Shah Kotla" and "Arun Jaitley Stadium") against
-- gold.batting_form_by_venue / gold.bowling_form_by_venue to answer
-- "how does this player actually perform at OUR home ground."

ALTER TABLE franchises ADD COLUMN IF NOT EXISTS home_venue TEXT;

-- Real, current (2026 season) primary home venues. Several franchises
-- split home matches across two venues in practice (RCB: Bengaluru +
-- Raipur; PBKS: New Chandigarh + Dharamshala; RR: Jaipur + Guwahati) --
-- this stores the PRIMARY one; the app matches venue names with
-- substring/keyword matching, not exact string equality, since
-- Cricsheet's own venue naming has changed over the 2008-2025 window
-- this data covers (see notebooks/014_seed_real_squads.py for the
-- keyword list used per team).
UPDATE franchises SET home_venue = 'MA Chidambaram Stadium, Chennai' WHERE name = 'Chennai Super Kings';
UPDATE franchises SET home_venue = 'Wankhede Stadium, Mumbai' WHERE name = 'Mumbai Indians';
UPDATE franchises SET home_venue = 'M Chinnaswamy Stadium, Bengaluru' WHERE name = 'Royal Challengers Bengaluru';
UPDATE franchises SET home_venue = 'Eden Gardens, Kolkata' WHERE name = 'Kolkata Knight Riders';
UPDATE franchises SET home_venue = 'Arun Jaitley Stadium, Delhi' WHERE name = 'Delhi Capitals';
UPDATE franchises SET home_venue = 'Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh' WHERE name = 'Punjab Kings';
UPDATE franchises SET home_venue = 'Sawai Mansingh Stadium, Jaipur' WHERE name = 'Rajasthan Royals';
UPDATE franchises SET home_venue = 'Rajiv Gandhi International Stadium, Hyderabad' WHERE name = 'Sunrisers Hyderabad';
UPDATE franchises SET home_venue = 'Narendra Modi Stadium, Ahmedabad' WHERE name = 'Gujarat Titans';
UPDATE franchises SET home_venue = 'Ekana Cricket Stadium, Lucknow' WHERE name = 'Lucknow Super Giants';

-- Sanity check after running:
-- SELECT name, home_venue FROM franchises ORDER BY name;
-- Expect all 10 rows populated.

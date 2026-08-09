-- =========================================================
-- CricSavant AI — seed the 10 real IPL franchises.
-- =========================================================
-- All 10 current IPL teams, real names and real (as of Aug 2026)
-- ownership groups. owner_label is descriptive context for the app,
-- not used in any auction-logic calculation.
--
-- PURSE ASSUMPTION (explicit, not fabricated data dressed up as
-- fact): every franchise is seeded at the full max_purse_cr from the
-- current row in auction_rules (125.00cr, the real Dec 2025 BCCI
-- mini-auction cap). Real franchises' actual remaining purses after
-- their 2025 mega-auction retentions are NOT reliably available/cited
-- as a clean public dataset, so rather than guess per-team numbers,
-- every franchise starts this app's auction on equal footing at the
-- full cap. This is a simplifying assumption for how the app's demo
-- auction runs, not a claim about real-world remaining budgets.
--
-- max_squad_size / max_overseas use the schema defaults (25 / 8),
-- matching the current auction_rules row -- change here if a future
-- rule update ever diverges the two.
--
-- Ownership sources (Aug 2026):
--   CSK, MI, PBKS, SRH, GT, LSG: https://www.whereig.com/cricket/ipl-team-owners.html
--   RCB, KKR, DC, RR: https://www.chaseyoursport.com/ipl/ipl-team-owners-list/11916
--   GT (Torrent Group / CVC / Adani): https://www.outlookindia.com/sports/cricket/ipl-gujarat-titans-ownership-transitions-as-torrent-group-acquires-majority-stake
--   LSG (RPSG / Sanjiv Goenka): https://en.wikipedia.org/wiki/Lucknow_Super_Giants

INSERT INTO franchises (name, owner_label, purse_total_cr, purse_remaining_cr, max_squad_size, max_overseas)
VALUES
    ('Chennai Super Kings',          'India Cements (N. Srinivasan)',                                   125.00, 125.00, 25, 8),
    ('Mumbai Indians',               'Reliance Industries (Mukesh Ambani)',                             125.00, 125.00, 25, 8),
    ('Royal Challengers Bengaluru',  'Aditya Birla Group / UltraTech Cement consortium (with Times Group, Blackstone, David Blitzer)', 125.00, 125.00, 25, 8),
    ('Kolkata Knight Riders',        'Red Chillies Entertainment (Shah Rukh Khan)',                     125.00, 125.00, 25, 8),
    ('Delhi Capitals',               'JSW Group & GMR Group (joint ownership)',                         125.00, 125.00, 25, 8),
    ('Punjab Kings',                 'Mohit Burman, Ness Wadia, Preity Zinta, Karan Paul',              125.00, 125.00, 25, 8),
    ('Rajasthan Royals',             'Kal Somani-led consortium (with Rob Walton & the Hamp family)',  125.00, 125.00, 25, 8),
    ('Sunrisers Hyderabad',          'Sun TV Network (Kavya Maran)',                                    125.00, 125.00, 25, 8),
    ('Gujarat Titans',               'Torrent Group & CVC Capital Partners (Adani Group joined 2025)', 125.00, 125.00, 25, 8),
    ('Lucknow Super Giants',         'RPSG Group (Sanjiv Goenka)',                                      125.00, 125.00, 25, 8)
ON CONFLICT (name) DO NOTHING;

-- Sanity check after running:
-- SELECT name, owner_label, purse_remaining_cr FROM franchises ORDER BY name;
-- Expect 10 rows.

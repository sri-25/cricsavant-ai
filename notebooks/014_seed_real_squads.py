# Databricks notebook source
# CricSavant AI -- seed REAL current (2026 season) IPL squads.
#
# WHY THIS EXISTS
# ----------------
# Every franchise in this app previously started from an empty roster
# at the full purse cap -- a deliberate simplification documented in
# sql/005, made because no reliable per-team post-retention roster
# data was readily available at the time. That's no longer true: the
# IPL 2026 mini-auction (Dec 16 2025, Abu Dhabi) has been fully
# reported, and the 2026 season itself has since been played (today
# is Aug 2026) -- so the real "who's actually on each team right now"
# answer is public record, not a guess. This notebook seeds that.
#
# This directly enables the thing a "bring your own franchise" app
# should actually be able to do before the real IPL 2027 auction:
# look at a team's REAL current squad + REAL recent/venue-specific
# form and reason about who's a retain vs release candidate -- not
# just simulate bidding into an empty roster.
#
# SOURCES (see README/PROJECT_PLAN citation conventions)
# --------------------------------------------------------
# - Roster (retained + auctioned) per team, and real post-auction
#   purse remaining per team:
#   https://www.business-standard.com/cricket/ipl/ipl-2026-auction-remaining-purse-retained-players-list-of-all-10-teams-125121500242_1.html
#   (published Dec 16, 2025)
# - Real primary home venues: see sql/007_add_home_venue.sql header.
#
# WHAT'S GROUNDED VS. BEST-EFFORT (being explicit, not burying it):
#   - ROSTER MEMBERSHIP (which real player is on which real team) --
#     directly from the cited source above. High confidence.
#   - ROLE (batter/bowler/all-rounder/wicketkeeper) and BOWLING_STYLE --
#     derived from EXISTING verified data wherever possible: matched
#     against player_pool (the real, BCCI-cited 369-player shortlist,
#     which already has these fields) first, then against
#     gold.batter_profile/bowler_profile (real Cricsheet match data)
#     using the same surname-matching logic the app already uses.
#     Only players who match NEITHER source fall back to a plain
#     default -- and those fallbacks are printed at the end of this
#     run, not silently accepted, so they can be reviewed/corrected.
#   - IS_OVERSEAS -- classified from general cricket knowledge (each
#     of these is a current, publicly known international or Indian
#     domestic player), NOT from a single structured citation the way
#     player_pool's is_overseas was. Flagged here as lower-confidence
#     than the roster membership itself; worth a spot-check.
#   - PRICE_CR -- deliberately NOT populated per-player for this real
#     seed (acquisition_type='imported', price_cr=0). Individual
#     retention/purchase prices for all ~250 players aren't uniformly
#     available from one clean, citable source the way the roster
#     membership is. What IS real and used: each team's actual
#     post-auction purse_remaining_cr (see PURSE_REMAINING below),
#     which this notebook writes to franchises directly. The app's
#     own practice-bidding purse math (Live Auction Console) continues
#     to deduct from that real baseline, not a fabricated per-player
#     price on these rows.
#
# RE-RUNNING: idempotent -- deletes any previously-seeded 'imported'
# rows before re-inserting, so running this twice doesn't duplicate
# the roster.

# COMMAND ----------

%pip install pg8000 -q
dbutils.library.restartPython()

# COMMAND ----------

import pg8000
from pyspark.sql import functions as F

LAKEBASE_HOST = "ep-curly-dream-d85sia2d.database.us-east-2.cloud.databricks.com"
LAKEBASE_DB = "databricks_postgres"


def get_conn():
    return pg8000.connect(
        host=LAKEBASE_HOST,
        port=5432,
        database=LAKEBASE_DB,
        user="cricsavant_app",
        password=dbutils.secrets.get(scope="cricsavant", key="lakebase_app_password"),
        ssl_context=True,
    )

# COMMAND ----------

# Real post-auction remaining purse per team, Dec 16 2025 (source:
# business-standard.com, cited above). This REPLACES the "everyone
# starts at the full 125cr cap" placeholder from sql/005.
PURSE_REMAINING = {
    "Chennai Super Kings": 2.4,
    "Delhi Capitals": 0.35,
    "Gujarat Titans": 1.95,
    "Kolkata Knight Riders": 0.45,
    "Lucknow Super Giants": 4.55,
    "Mumbai Indians": 0.55,
    "Punjab Kings": 3.5,
    "Rajasthan Royals": 2.65,
    "Royal Challengers Bengaluru": 0.25,
    "Sunrisers Hyderabad": 5.45,
}

# Real IPL 2026 rosters -- (player_name, is_overseas_best_effort).
# "retained" = kept before the Dec 2025 mini-auction; "auctioned" =
# bought AT the Dec 2025 mini-auction. Both are equally real/current
# squad members -- the split is just provenance, not used downstream.
ROSTERS = {
    "Chennai Super Kings": {
        "retained": [
            ("MS Dhoni", False), ("Ruturaj Gaikwad", False), ("Sanju Samson", False),
            ("Ayush Mhatre", False), ("Dewald Brewis", True), ("Shivam Dube", False),
            ("Urvil Patel", False), ("Noor Ahmad", True), ("Nathan Ellis", True),
            ("Shreyas Gopal", False), ("Khaleel Ahmed", False), ("Ramakrishna Ghosh", False),
            ("Mukesh Choudhary", False), ("Jamie Overton", True), ("Gurjapneet Singh", False),
            ("Anshul Kamboj", False),
        ],
        "auctioned": [
            ("Prashant Veer", False), ("Kartik Sharma", False), ("Rahul Chahar", False),
            ("Akeal Hosein", True), ("Matt Henry", True), ("Matthew Short", True),
            ("Sarfaraz Khan", False), ("Aman Khan", False), ("Zak Foulkes", True),
        ],
    },
    "Delhi Capitals": {
        "retained": [
            ("Nitish Rana", False), ("Abhishek Porel", False), ("Ajay Mandal", False),
            ("Ashutosh Sharma", False), ("Axar Patel", False), ("Dushmantha Chameera", True),
            ("Karun Nair", False), ("KL Rahul", False), ("Kuldeep Yadav", False),
            ("Madhav Tiwari", False), ("Mitchell Starc", True), ("Sameer Rizvi", False),
            ("T Natarajan", False), ("Tripurana Vijay", False), ("Tristan Stubbs", True),
            ("Vipraj Nigam", False), ("Mukesh Kumar", False),
        ],
        "auctioned": [
            ("Auqib Dhar", False), ("Pathum Nissanka", True), ("David Miller", True),
            ("Ben Duckett", True), ("Lungi Ngidi", True), ("Sahil Parakh", False),
            ("Prithvi Shaw", False), ("Kyle Jamieson", True),
        ],
    },
    "Gujarat Titans": {
        "retained": [
            ("Anuj Rawat", False), ("Glenn Phillips", True), ("Gurnoor Brar", False),
            ("Ishant Sharma", False), ("Jayant Yadav", False), ("Jos Buttler", True),
            ("Kagiso Rabada", True), ("Kumar Kushagra", False), ("Manav Suthar", False),
            ("Mohammed Siraj", False), ("Arshad Khan", False), ("Nishant Sindhu", False),
            ("Prasidh Krishna", False), ("R Sai Kishore", False), ("Rahul Tewatia", False),
            ("Rashid Khan", True), ("B Sai Sudharsan", False), ("M Shahrukh Khan", False),
            ("Shubman Gill", False), ("Washington Sundar", False),
        ],
        "auctioned": [
            ("Jason Holder", True), ("Ashok Sharma", False), ("Tom Banton", True),
            ("Prithvi Raj", False), ("Luke Wood", True),
        ],
    },
    "Kolkata Knight Riders": {
        "retained": [
            ("Ajinkya Rahane", False), ("Angkrish Raghuvanshi", False), ("Anukul Roy", False),
            ("Harshit Rana", False), ("Manish Pandey", False), ("Ramandeep Singh", False),
            ("Rinku Singh", False), ("Rovman Powell", True), ("Sunil Narine", True),
            ("Umran Malik", False), ("Vaibhav Arora", False), ("Varun Chakravarthy", False),
        ],
        "auctioned": [
            ("Cameron Green", True), ("Matheesha Pathirana", True), ("Rachin Ravindra", True),
            ("Finn Allen", True), ("Tim Seifert", True), ("Tejasvi Singh", False),
            ("Akash Deep", False), ("Rahul Tripathi", False), ("Kartik Tyagi", False),
            ("Prashant Solanki", False), ("Sarthak Ranjan", False), ("Daksh Kamra", False),
            # Mustafizur Rahman was sold to KKR but released by BCCI in Jan 2026
            # per cricketstadium.com.in -- deliberately omitted here since he's
            # not actually on the roster the 2026 season was played with.
        ],
    },
    "Lucknow Super Giants": {
        "retained": [
            ("Abdul Samad", False), ("Aiden Markram", True), ("Akash Singh", False),
            ("Arshin Kulkarni", False), ("Avesh Khan", False), ("Ayush Badoni", False),
            ("Digvesh Rathi", False), ("Himmat Singh", False), ("Manimaran Siddharth", False),
            ("Matthew Breetzke", True), ("Mayank Yadav", False), ("Mohammed Shami", False),
            ("Mitchell Marsh", True), ("Mohsin Khan", False), ("Nicholas Pooran", True),
            ("Prince Yadav", False), ("Rishabh Pant", False), ("Shahbaz Ahmed", False),
        ],
        "auctioned": [
            ("Josh Inglis", True), ("Wanindu Hasaranga", True), ("Anrich Nortje", True),
            ("Mukul Choudhary", False), ("Akshat Raghuvanshi", False), ("Naman Tiwari", False),
        ],
    },
    "Mumbai Indians": {
        "retained": [
            ("Shardul Thakur", False), ("Sherfane Rutherford", True), ("Mayank Markande", False),
            ("AM Ghazanfar", True), ("Ashwani Kumar", False), ("Corbin Bosch", True),
            ("Deepak Chahar", False), ("Hardik Pandya", False), ("Jasprit Bumrah", False),
            ("Mitchell Santner", True), ("Naman Dhir", False), ("Raghu Sharma", False),
            ("Raj Bawa", False), ("Robin Minz", False), ("Rohit Sharma", False),
            ("Ryan Rickelton", True), ("Suryakumar Yadav", False), ("Tilak Varma", False),
            ("Trent Boult", True), ("Will Jacks", True),
        ],
        "auctioned": [
            ("Quinton de Kock", True), ("Danish Malewar", False), ("Md Izhar", False),
            ("Atharva Ankolekar", False), ("Mayank Rawat", False),
        ],
    },
    "Punjab Kings": {
        "retained": [
            ("Arshdeep Singh", False), ("Azmatullah Omarzai", True), ("Harnoor Pannu", False),
            ("Harpreet Brar", False), ("Lockie Ferguson", True), ("Marco Jansen", True),
            ("Marcus Stoinis", True), ("Mitch Owen", True), ("Musheer Khan", False),
            ("Nehal Wadhera", False), ("Prabhsimran Singh", False), ("Priyansh Arya", False),
            ("Pyla Avinash", False), ("Shashank Singh", False), ("Shreyas Iyer", False),
            ("Suryansh Shedge", False), ("Vishnu Vinod", False), ("Vyshak Vijaykumar", False),
            ("Xavier Bartlett", True), ("Yash Thakur", False), ("Yuzvendra Chahal", False),
        ],
        "auctioned": [
            ("Ben Dwarshuis", True), ("Cooper Connolly", True), ("Pravin Dubey", False),
            ("Vishal Nishad", False),
        ],
    },
    "Rajasthan Royals": {
        "retained": [
            ("Donovan Ferreira", True), ("Ravindra Jadeja", False), ("Sam Curran", True),
            ("Dhruv Jurel", False), ("Jofra Archer", True), ("Kwena Maphaka", True),
            ("Lhuan-Dre Pretorius", True), ("Nandre Burger", True), ("Riyan Parag", False),
            ("Sandeep Sharma", False), ("Shimron Hetmyer", True), ("Shubham Dubey", False),
            ("Tushar Deshpande", False), ("Vaibhav Suryavanshi", False), ("Yashasvi Jaiswal", False),
            ("Yudhvir Singh", False),
        ],
        "auctioned": [
            ("Ravi Bishnoi", False), ("Ravi Singh", False), ("Sushant Mishra", False),
            ("Yash Raj Punja", False), ("Vignesh Puthur", False), ("Aman Rao", False),
            ("Brijesh Sharma", False), ("Adam Milne", True), ("Kuldeep Sen", False),
        ],
    },
    "Royal Challengers Bengaluru": {
        "retained": [
            ("Virat Kohli", False), ("Phil Salt", True), ("Devdutt Padikkal", False),
            ("Rajat Patidar", False), ("Tim David", True), ("Krunal Pandya", False),
            ("Romario Shepherd", True), ("Jitesh Sharma", False), ("Bhuvneshwar Kumar", False),
            ("Yash Dayal", False), ("Josh Hazlewood", True), ("Suyash Sharma", False),
            ("Abhinandan Singh", False), ("Jacob Bethell", True), ("Nuwan Thushara", True),
            ("Rasikh Dar", False), ("Swapnil Singh", False),
        ],
        "auctioned": [
            ("Venkatesh Iyer", False), ("Mangesh Yadav", False), ("Jacob Duffy", True),
            ("Jordan Cox", True), ("Satvik Deswal", False), ("Vickey Ostwal", False),
            ("Vihaan Malhotra", False), ("Kanishk Chouhan", False),
        ],
    },
    "Sunrisers Hyderabad": {
        "retained": [
            ("Abhishek Sharma", False), ("Aniket Verma", False), ("Brydon Carse", True),
            ("Eshan Malinga", True), ("Harsh Dubey", False), ("Harshal Patel", False),
            ("Heinrich Klaasen", True), ("Ishan Kishan", False), ("Jaydev Unadkat", False),
            ("Kamindu Mendis", True), ("Nitish Kumar Reddy", False), ("Pat Cummins", True),
            ("R Smaran", False), ("Travis Head", True), ("Zeeshan Ansari", False),
        ],
        "auctioned": [
            ("Liam Livingstone", True), ("Jack Edwards", True), ("Salil Arora", False),
            ("Shivam Mavi", False), ("Shivang Kumar", False), ("Sakib Hussain", False),
            ("Onkar Tarmale", False), ("Amit Kumar", False), ("Praful Hinge", False),
            ("Krains Fuletra", False),
        ],
    },
}

# COMMAND ----------

# Build a name -> (role, bowling_style) lookup from the two REAL,
# already-verified sources, in priority order: player_pool (exact
# BCCI-cited role) first, then gold profiles (real Cricsheet match
# history, surname-matched the same way the app does it).

conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT player_name, role, bowling_style FROM player_pool WHERE is_current_reference")
pool_lookup = {name.lower(): (role, style) for name, role, style in cur.fetchall()}
cur.close()
conn.close()

batter_df = spark.table("cricsavant.gold.batter_profile").select("player_name").distinct()
bowler_df = spark.table("cricsavant.gold.bowler_profile").select("player_name").distinct()
bat_names = set(r["player_name"] for r in batter_df.collect())
bowl_names = set(r["player_name"] for r in bowler_df.collect())


def match_gold(name, name_set):
    if name in name_set:
        return True
    parts = name.strip().split()
    if not parts:
        return False
    surname = parts[-1].lower()
    first_initial = parts[0][0].lower()
    candidates = [n for n in name_set if n.lower().split()[-1] == surname]
    if len(candidates) == 1:
        return True
    narrowed = [n for n in candidates if n.strip()[0].lower() == first_initial]
    return len(narrowed) == 1


def infer_role(name):
    pool_hit = pool_lookup.get(name.lower())
    if pool_hit:
        return pool_hit[0], pool_hit[1], "player_pool"
    has_bat = match_gold(name, bat_names)
    has_bowl = match_gold(name, bowl_names)
    if has_bat and has_bowl:
        return "all-rounder", "na", "gold (bat+bowl)"
    if has_bowl:
        return "bowler", "pace", "gold (bowl only, style not tracked -- see README data-gaps note)"
    if has_bat:
        return "batter", "na", "gold (bat only)"
    return "batter", "na", "DEFAULT -- no match in player_pool or gold, review manually"

# COMMAND ----------

fallback_log = []
rows_to_insert = []  # (franchise_name, player_name, role, bowling_style, is_overseas)

for franchise_name, groups in ROSTERS.items():
    for category, players in groups.items():
        for player_name, is_overseas in players:
            role, bowling_style, source = infer_role(player_name)
            if source.startswith("DEFAULT"):
                fallback_log.append((franchise_name, player_name))
            rows_to_insert.append((franchise_name, player_name, role, bowling_style, is_overseas))

print(f"Prepared {len(rows_to_insert)} real roster rows across {len(ROSTERS)} franchises.")
print(f"{len(fallback_log)} player(s) matched neither player_pool nor gold tables -- defaulted to 'batter':")
for franchise_name, player_name in fallback_log:
    print(f"  - {player_name} ({franchise_name})")

# COMMAND ----------

# Idempotent write: clear any previously-seeded 'imported' rows (never
# touches 'auction' rows -- those are real practice bids placed
# through the app, not something this reseed should ever discard),
# then insert the real current rosters and update real purse figures.

conn = get_conn()
cur = conn.cursor()

cur.execute("DELETE FROM franchise_roster WHERE acquisition_type = 'imported'")
deleted = cur.rowcount
print(f"Cleared {deleted} previously-imported roster row(s).")

cur.execute("SELECT franchise_id, name FROM franchises")
fid_by_name = {name: fid for fid, name in cur.fetchall()}

inserted = 0
for franchise_name, player_name, role, bowling_style, is_overseas in rows_to_insert:
    fid = fid_by_name.get(franchise_name)
    if fid is None:
        print(f"WARNING: no franchise row for '{franchise_name}' -- skipping {player_name}")
        continue
    cur.execute(
        "INSERT INTO franchise_roster (franchise_id, player_name, role, bowling_style, is_overseas, "
        "acquisition_type, price_cr, status) VALUES (%s, %s, %s, %s, %s, 'imported', 0, 'active')",
        (fid, player_name, role, bowling_style, is_overseas),
    )
    inserted += 1

for franchise_name, purse in PURSE_REMAINING.items():
    cur.execute(
        "UPDATE franchises SET purse_remaining_cr = %s WHERE name = %s",
        (purse, franchise_name),
    )

conn.commit()
cur.close()
conn.close()
print(f"Inserted {inserted} real roster rows. Updated purse_remaining_cr for {len(PURSE_REMAINING)} franchises.")

# COMMAND ----------

# Verification
conn = get_conn()
cur = conn.cursor()
cur.execute(
    "SELECT f.name, count(*) AS squad_size, f.purse_remaining_cr "
    "FROM franchise_roster r JOIN franchises f ON f.franchise_id = r.franchise_id "
    "WHERE r.status = 'active' GROUP BY f.name, f.purse_remaining_cr ORDER BY f.name"
)
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()

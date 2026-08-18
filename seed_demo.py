"""Build demo.db from scratch for the DEMO_MODE screenshots/recording.

Standalone: never opens epl.db, and refuses to run if its hardcoded output
path is ever renamed to epl.db. Run with:

    python3 seed_demo.py
"""
import os
import random
import subprocess
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import SCHEMA

REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = REPO_ROOT / "demo.db"

if OUTPUT_PATH.name == "epl.db":
    raise SystemExit("Refusing to write to a file named epl.db")

SEASON = "2026-27"
PLAYERS = ("Alex", "Sam", "Jordan")

# Real Premier League matchday 1-5 fixture matchups for the 2026-27 season
# (copied from epl.db's fixture list -- public schedule data, not
# predictions). Kickoff times below are the real ones *relative to each
# other*; build_matches() shifts the whole block so matchday 1 always
# lands safely in the past and matchday 5 always lands just ahead of
# "now", whatever day this script is run.
FIXTURES = [
    (1, "2026-08-21T19:00:00Z", "Arsenal FC", "Coventry City FC"),
    (1, "2026-08-22T11:30:00Z", "Hull City AFC", "Manchester United FC"),
    (1, "2026-08-22T14:00:00Z", "Ipswich Town FC", "Sunderland AFC"),
    (1, "2026-08-22T14:00:00Z", "Nottingham Forest FC", "Leeds United FC"),
    (1, "2026-08-22T14:00:00Z", "Everton FC", "Crystal Palace FC"),
    (1, "2026-08-22T16:30:00Z", "Brentford FC", "Tottenham Hotspur FC"),
    (1, "2026-08-23T13:00:00Z", "Manchester City FC", "AFC Bournemouth"),
    (1, "2026-08-23T13:00:00Z", "Brighton & Hove Albion FC", "Aston Villa FC"),
    (1, "2026-08-23T15:30:00Z", "Newcastle United FC", "Liverpool FC"),
    (1, "2026-08-24T19:00:00Z", "Fulham FC", "Chelsea FC"),
    (2, "2026-08-28T19:00:00Z", "Crystal Palace FC", "Manchester City FC"),
    (2, "2026-08-29T11:30:00Z", "Liverpool FC", "Nottingham Forest FC"),
    (2, "2026-08-29T14:00:00Z", "AFC Bournemouth", "Everton FC"),
    (2, "2026-08-29T14:00:00Z", "Coventry City FC", "Hull City AFC"),
    (2, "2026-08-29T16:30:00Z", "Tottenham Hotspur FC", "Newcastle United FC"),
    (2, "2026-08-30T13:00:00Z", "Sunderland AFC", "Fulham FC"),
    (2, "2026-08-30T13:00:00Z", "Chelsea FC", "Brighton & Hove Albion FC"),
    (2, "2026-08-30T13:00:00Z", "Leeds United FC", "Brentford FC"),
    (2, "2026-08-30T15:30:00Z", "Manchester United FC", "Ipswich Town FC"),
    (2, "2026-08-31T19:00:00Z", "Aston Villa FC", "Arsenal FC"),
    (3, "2026-09-04T19:00:00Z", "Ipswich Town FC", "Liverpool FC"),
    (3, "2026-09-05T11:30:00Z", "Newcastle United FC", "AFC Bournemouth"),
    (3, "2026-09-05T14:00:00Z", "Nottingham Forest FC", "Tottenham Hotspur FC"),
    (3, "2026-09-05T14:00:00Z", "Manchester City FC", "Coventry City FC"),
    (3, "2026-09-05T14:00:00Z", "Brighton & Hove Albion FC", "Leeds United FC"),
    (3, "2026-09-05T14:00:00Z", "Brentford FC", "Sunderland AFC"),
    (3, "2026-09-05T14:00:00Z", "Fulham FC", "Crystal Palace FC"),
    (3, "2026-09-05T16:30:00Z", "Hull City AFC", "Aston Villa FC"),
    (3, "2026-09-06T13:00:00Z", "Everton FC", "Manchester United FC"),
    (3, "2026-09-06T15:30:00Z", "Arsenal FC", "Chelsea FC"),
    (4, "2026-09-12T14:00:00Z", "Crystal Palace FC", "Ipswich Town FC"),
    (4, "2026-09-12T14:00:00Z", "Liverpool FC", "Fulham FC"),
    (4, "2026-09-12T14:00:00Z", "Aston Villa FC", "Nottingham Forest FC"),
    (4, "2026-09-12T14:00:00Z", "AFC Bournemouth", "Brentford FC"),
    (4, "2026-09-12T14:00:00Z", "Chelsea FC", "Hull City AFC"),
    (4, "2026-09-12T16:30:00Z", "Tottenham Hotspur FC", "Everton FC"),
    (4, "2026-09-12T19:00:00Z", "Sunderland AFC", "Arsenal FC"),
    (4, "2026-09-13T13:00:00Z", "Coventry City FC", "Brighton & Hove Albion FC"),
    (4, "2026-09-13T15:30:00Z", "Manchester United FC", "Manchester City FC"),
    (4, "2026-09-14T19:00:00Z", "Leeds United FC", "Newcastle United FC"),
    (5, "2026-09-18T19:00:00Z", "Brentford FC", "Chelsea FC"),
    (5, "2026-09-19T11:30:00Z", "Tottenham Hotspur FC", "Aston Villa FC"),
    (5, "2026-09-19T14:00:00Z", "Everton FC", "Ipswich Town FC"),
    (5, "2026-09-19T14:00:00Z", "Leeds United FC", "Crystal Palace FC"),
    (5, "2026-09-19T14:00:00Z", "Brighton & Hove Albion FC", "Arsenal FC"),
    (5, "2026-09-19T14:00:00Z", "Newcastle United FC", "Hull City AFC"),
    (5, "2026-09-19T14:00:00Z", "Manchester City FC", "Sunderland AFC"),
    (5, "2026-09-19T16:30:00Z", "Nottingham Forest FC", "Coventry City FC"),
    (5, "2026-09-20T13:00:00Z", "AFC Bournemouth", "Liverpool FC"),
    (5, "2026-09-20T15:30:00Z", "Fulham FC", "Manchester United FC"),
]

# Invented final scores for matchdays 1-4 (40 fixtures, in fixture order
# above) -- decisive results with a handful of draws.
FINAL_SCORES = [
    (2, 1), (1, 0), (3, 1), (0, 2), (1, 1), (2, 0), (1, 2), (3, 0), (2, 2), (0, 1),
    (1, 0), (2, 1), (0, 0), (3, 2), (1, 3), (2, 0), (0, 1), (1, 1), (4, 1), (2, 2),
    (2, 0), (1, 1), (0, 1), (3, 1), (1, 0), (2, 3), (0, 0), (1, 2), (2, 1), (3, 0),
    (1, 2), (2, 0), (0, 0), (1, 1), (3, 2), (0, 1), (2, 1), (1, 0), (2, 2), (4, 0),
]

# (exact, correct-result, wrong) counts out of the 40 settled predictions
# per player -- tuned so Alex and Sam land level on points but split by
# exact-score count.
CATEGORY_COUNTS = {
    "Alex": (4, 12, 24),     # 3*4 + 1*12 = 24 pts, 4 exact
    "Sam": (2, 18, 20),      # 3*2 + 1*18 = 24 pts, 2 exact
    "Jordan": (1, 12, 27),   # 3*1 + 1*12 = 15 pts, 1 exact
}

# Explicit categories for the chronologically-last 5 settled matches (the
# tail of matchday 4) -- this is exactly the leaderboard's recent-form
# chip row, so pin it to a lumpy pattern per player instead of leaving it
# to chance.
LAST5_CATEGORIES = {
    "Alex": ["E", "W", "C", "C", "W"],     # chips: 3 0 1 1 0
    "Sam": ["W", "E", "C", "W", "C"],      # chips: 0 3 1 0 1
    "Jordan": ["W", "W", "C", "E", "W"],   # chips: 0 0 1 3 0
}


def result_of(h, a):
    if h > a:
        return "H"
    if h < a:
        return "A"
    return "D"


def make_pred(actual, category):
    """A predicted score matching `category` against `actual`:
    'E' exact, 'C' correct result but different scoreline, 'W' wrong result."""
    h, a = actual
    res = result_of(h, a)
    if category == "E":
        return h, a
    if category == "C":
        if res == "D":
            return (h + 1, a + 1) if h < 3 else (0, 0)
        if res == "H":
            return (h, a - 1) if a > 0 else (h + 1, a)
        return (h - 1, a) if h > 0 else (h, a + 1)
    # category == "W": force a different result entirely
    if res == "D":
        return (h + 1, a)
    return (a, h)


def build_category_list(player, match_ids):
    """Category ('E'/'C'/'W') for each id in `match_ids`, matching the
    player's overall counts with the last 5 (the form chip row) pinned to
    LAST5_CATEGORIES and everything else shuffled deterministically."""
    e, c, w = CATEGORY_COUNTS[player]
    assert e + c + w == len(match_ids)

    last5_ids = match_ids[-5:]
    last5_cats = LAST5_CATEGORIES[player]
    remaining_ids = match_ids[:-5]

    used = {k: last5_cats.count(k) for k in "ECW"}
    rest = ["E"] * (e - used["E"]) + ["C"] * (c - used["C"]) + ["W"] * (w - used["W"])
    assert len(rest) == len(remaining_ids)
    random.Random(f"seed-demo-{player}").shuffle(rest)

    cats_by_id = dict(zip(remaining_ids, rest))
    cats_by_id.update(zip(last5_ids, last5_cats))
    return [cats_by_id[mid] for mid in match_ids]


def shifted_fixtures():
    """Shift the whole fixture block so matchday 1 starts ~26 days in the
    past and matchday 5 (28 real days later) starts a couple of days in
    the future, regardless of what day this script runs."""
    original_md1_start = datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc)
    target_md1_start = datetime.now(timezone.utc) - timedelta(days=26)
    shift = target_md1_start - original_md1_start

    out = []
    for matchday, utc_date, home, away in FIXTURES:
        dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00")) + shift
        out.append((matchday, dt.strftime("%Y-%m-%dT%H:%M:%SZ"), home, away))
    return out


def main():
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    conn = sqlite3.connect(OUTPUT_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("ALTER TABLE matches ADD COLUMN season TEXT")
    conn.execute("ALTER TABLE matches ADD COLUMN competition TEXT")

    player_ids = {}
    for name in PLAYERS:
        conn.execute("INSERT INTO players (name) VALUES (?)", (name,))
        player_ids[name] = conn.execute(
            "SELECT id FROM players WHERE name = ?", (name,)
        ).fetchone()["id"]

    match_ids = []
    for i, (matchday, utc_date, home, away) in enumerate(shifted_fixtures(), start=1):
        if matchday <= 4:
            home_score, away_score = FINAL_SCORES[i - 1]
            status = "FINISHED"
        else:
            home_score, away_score = None, None
            status = "TIMED"
        conn.execute(
            """INSERT INTO matches (id, matchday, utc_date, home, away, home_score,
                                     away_score, status, season, competition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i, matchday, utc_date, home, away, home_score, away_score, status, SEASON, "PL"),
        )
        match_ids.append(i)

    settled_ids = match_ids[:40]  # matchdays 1-4; matchday 5 gets no predictions
    for name in PLAYERS:
        cats = build_category_list(name, settled_ids)
        for match_id, cat in zip(settled_ids, cats):
            actual = FINAL_SCORES[match_id - 1]
            pred_h, pred_a = make_pred(actual, cat)
            conn.execute(
                "INSERT INTO predictions (player_id, match_id, pred_home, pred_away) VALUES (?, ?, ?, ?)",
                (player_ids[name], match_id, pred_h, pred_a),
            )

    conn.commit()
    conn.close()
    print(f"Built {OUTPUT_PATH}\n")

    # Run the real settle.py against demo.db to compute points -- points
    # are never written directly, only exercised through the scoring engine.
    result = subprocess.run(
        [sys.executable, "settle.py"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_PATH": str(OUTPUT_PATH)},
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

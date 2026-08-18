import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# DATABASE_PATH lets a separate run (e.g. demo mode) point at its own
# SQLite file without touching epl.db. Relative paths resolve against the
# repo root, not the process cwd, so behaviour doesn't depend on where the
# app is launched from. Unset (the production default) keeps epl.db.
_database_path_env = os.environ.get("DATABASE_PATH")
DB_PATH = (REPO_ROOT / _database_path_env) if _database_path_env else (REPO_ROOT / "epl.db")

# Season label backfilled onto every existing row that predates the
# `season` column. Update this once a year when the fixture list rolls
# over to a new season.
CURRENT_SEASON = "2026-27"

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    matchday INT,
    utc_date TEXT,
    home TEXT,
    away TEXT,
    home_score INT,
    away_score INT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY,
    player_id INT,
    match_id INT,
    pred_home INT,
    pred_away INT,
    UNIQUE(player_id, match_id),
    FOREIGN KEY(player_id) REFERENCES players(id),
    FOREIGN KEY(match_id) REFERENCES matches(id)
);

CREATE TABLE IF NOT EXISTS auth_attempts (
    ip TEXT PRIMARY KEY,
    fail_count INT NOT NULL DEFAULT 0,
    locked_until TEXT
);
"""


def _migrate(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(matches)")]
    if "season" not in cols:
        conn.execute("ALTER TABLE matches ADD COLUMN season TEXT")
        conn.execute("UPDATE matches SET season = ? WHERE season IS NULL", (CURRENT_SEASON,))
        conn.commit()
    if "competition" not in cols:
        conn.execute("ALTER TABLE matches ADD COLUMN competition TEXT")
        # Every row that predates this column is Premier League (current
        # season fetch + the 5-season historical import) -- ELC/CL rows
        # are only ever inserted with competition already set.
        conn.execute("UPDATE matches SET competition = 'PL' WHERE competition IS NULL")
        conn.commit()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn

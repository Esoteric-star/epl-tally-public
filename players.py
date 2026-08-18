import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from db import get_conn

AVATARS_DIR = Path(__file__).resolve().parent / "static" / "avatars"


def parse_utc(dt_str):
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def get_player(conn, name):
    return conn.execute("SELECT id, name FROM players WHERE name = ?", (name,)).fetchone()


def avatar_file(name):
    """Filename in static/avatars/ for this player, or None if missing --
    callers fall back to the initials circle, never a broken <img>."""
    if not name:
        return None
    file = f"{name.lower()}.png"
    return file if (AVATARS_DIR / file).is_file() else None


def add_player(conn):
    name = input("Player name: ").strip()
    if not name:
        print("Name cannot be empty.")
        return
    try:
        conn.execute("INSERT INTO players (name) VALUES (?)", (name,))
        conn.commit()
        print(f"Added player '{name}'.")
    except sqlite3.IntegrityError:
        print(f"Player '{name}' already exists.")


def enter_predictions(conn):
    name = input("Player name: ").strip()
    player = get_player(conn, name)
    if not player:
        print(f"No player named '{name}'. Add them first.")
        return
    try:
        matchday = int(input("Matchday number: ").strip())
    except ValueError:
        print("Matchday must be a number.")
        return

    matches = conn.execute(
        "SELECT id, utc_date, home, away, status FROM matches WHERE matchday = ? ORDER BY utc_date",
        (matchday,),
    ).fetchall()
    if not matches:
        print(f"No fixtures found for matchday {matchday}. Run fetch_matches.py first.")
        return

    now = datetime.now(timezone.utc)
    print(f"\nMatchday {matchday} fixtures for {name}:\n")
    for m in matches:
        kickoff = parse_utc(m["utc_date"])
        if kickoff <= now:
            print(f"  [locked]  {m['home']} vs {m['away']} ({m['status']}) - kickoff has passed, skipping")
            continue

        existing = conn.execute(
            "SELECT pred_home, pred_away FROM predictions WHERE player_id = ? AND match_id = ?",
            (player["id"], m["id"]),
        ).fetchone()
        current = f" [current: {existing['pred_home']}-{existing['pred_away']}]" if existing else ""

        raw = input(f"  {m['home']} vs {m['away']}{current} - enter 'H-A' or blank to skip: ").strip()
        if not raw:
            continue
        try:
            h_str, a_str = raw.split("-")
            pred_home, pred_away = int(h_str), int(a_str)
        except ValueError:
            print("    Invalid format, expected e.g. '2-1'. Skipped.")
            continue

        conn.execute(
            """INSERT INTO predictions (player_id, match_id, pred_home, pred_away)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(player_id, match_id) DO UPDATE SET
                 pred_home = excluded.pred_home,
                 pred_away = excluded.pred_away""",
            (player["id"], m["id"], pred_home, pred_away),
        )
        conn.commit()
        print("    Saved.")


def list_predictions(conn):
    name = input("Player name: ").strip()
    player = get_player(conn, name)
    if not player:
        print(f"No player named '{name}'.")
        return
    try:
        matchday = int(input("Matchday number: ").strip())
    except ValueError:
        print("Matchday must be a number.")
        return

    rows = conn.execute(
        """SELECT m.home, m.away, m.status, m.home_score, m.away_score,
                  pr.pred_home, pr.pred_away
           FROM matches m
           LEFT JOIN predictions pr ON pr.match_id = m.id AND pr.player_id = ?
           WHERE m.matchday = ?
           ORDER BY m.utc_date""",
        (player["id"], matchday),
    ).fetchall()
    if not rows:
        print(f"No fixtures found for matchday {matchday}.")
        return

    print(f"\n{name}'s predictions for matchday {matchday}:\n")
    for r in rows:
        pred = f"{r['pred_home']}-{r['pred_away']}" if r["pred_home"] is not None else "-- (no prediction)"
        actual = f"{r['home_score']}-{r['away_score']}" if r["status"] == "FINISHED" else r["status"]
        print(f"  {r['home']} vs {r['away']}: predicted {pred}, actual {actual}")


def main():
    conn = get_conn()
    menu = """
EPL Tally - Players & Predictions
  1) Add player
  2) Enter predictions for a matchday
  3) List predictions for a matchday
  4) Exit
"""
    while True:
        print(menu)
        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_player(conn)
        elif choice == "2":
            enter_predictions(conn)
        elif choice == "3":
            list_predictions(conn)
        elif choice == "4":
            break
        else:
            print("Invalid choice.")
    conn.close()


if __name__ == "__main__":
    main()

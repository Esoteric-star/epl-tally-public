"""One-time historical PL match import (last 5 completed seasons).

Source: datahub.io/football/english-premier-league, a PDDL (public domain)
mirror of football-data.co.uk's results CSVs. Per-season CSV columns used:
Date, HomeTeam, AwayTeam, FTHG, FTAG (everything else -- odds, referee,
shot counts -- is ignored).

This script makes network calls (to fetch the CSVs) but never touches the
live football-data.org API and never runs automatically -- it's invoked
by hand, once. Default is a dry run; pass --commit to actually write.
"""
import argparse
import csv
import hashlib
import io
import urllib.request

from db import get_conn

DATAHUB_URL = "https://datahub.io/football/english-premier-league/r/season-{code}.csv"

# Last 5 completed PL seasons before the current one (db.CURRENT_SEASON).
SEASON_CODES = ["2122", "2223", "2324", "2425", "2526"]

# CSV team name -> our exact matches.home/away name, for clubs that are
# part of the current 20-team roster in epl.db (see teams.py). Anything
# NOT in this map is stored under its raw CSV name rather than dropped --
# almost always a club that isn't in this season's roster (relegated in
# real life, or, for Coventry/Hull, simply not part of the real-world top
# flight in these 5 real seasons, so they have no rows here at all).
NAME_MAP = {
    "Arsenal": "Arsenal FC",
    "Aston Villa": "Aston Villa FC",
    "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford FC",
    "Brighton": "Brighton & Hove Albion FC",
    "Chelsea": "Chelsea FC",
    "Crystal Palace": "Crystal Palace FC",
    "Everton": "Everton FC",
    "Fulham": "Fulham FC",
    "Ipswich": "Ipswich Town FC",
    "Leeds": "Leeds United FC",
    "Liverpool": "Liverpool FC",
    "Man City": "Manchester City FC",
    "Man United": "Manchester United FC",
    "Newcastle": "Newcastle United FC",
    "Nott'm Forest": "Nottingham Forest FC",
    "Sunderland": "Sunderland AFC",
    "Tottenham": "Tottenham Hotspur FC",
}


def season_label(code):
    return f"20{code[:2]}-{code[2:]}"


def fetch_season_csv(code):
    url = DATAHUB_URL.format(code=code)
    with urllib.request.urlopen(url, timeout=20) as resp:
        text = resp.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def normalize_name(raw):
    return NAME_MAP.get(raw, raw)


def synthetic_id(season, home_raw, away_raw, date_str):
    """Deterministic id so re-running the import is a no-op (idempotent
    upsert via ON CONFLICT(id), same pattern fetch_matches.py already
    uses). Offset well clear of football-data.org's real match ids."""
    key = f"hist|{season}|{home_raw}|{away_raw}|{date_str}"
    digest = hashlib.sha1(key.encode()).hexdigest()
    return 1_000_000_000_000 + (int(digest[:15], 16) % 900_000_000_000)


def build_rows(code):
    season = season_label(code)
    rows = []
    for r in fetch_season_csv(code):
        date, home_raw, away_raw = r["Date"], r["HomeTeam"], r["AwayTeam"]
        if not r.get("FTHG") or not r.get("FTAG"):
            continue  # postponed/no result recorded
        rows.append(
            {
                "id": synthetic_id(season, home_raw, away_raw, date),
                "season": season,
                "utc_date": f"{date}T12:00:00Z",
                "home": normalize_name(home_raw),
                "away": normalize_name(away_raw),
                "home_score": int(r["FTHG"]),
                "away_score": int(r["FTAG"]),
                "home_raw": home_raw,
                "away_raw": away_raw,
            }
        )
    return rows


def dry_run():
    unmapped = set()
    total = 0
    print(f"{'Season':<10}{'Matches':>10}")
    for code in SEASON_CODES:
        rows = build_rows(code)
        total += len(rows)
        print(f"{season_label(code):<10}{len(rows):>10}")
        for r in rows:
            if r["home_raw"] not in NAME_MAP:
                unmapped.add(r["home_raw"])
            if r["away_raw"] not in NAME_MAP:
                unmapped.add(r["away_raw"])
    print(f"{'TOTAL':<10}{total:>10}")
    print()
    print(f"Unmapped team names ({len(unmapped)}) -- stored as-is, not normalised:")
    for name in sorted(unmapped):
        print(" ", name)
    return total, unmapped


def import_all():
    conn = get_conn()
    written = 0
    for code in SEASON_CODES:
        for r in build_rows(code):
            conn.execute(
                """INSERT INTO matches
                     (id, matchday, utc_date, home, away, home_score, away_score, status, season)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, 'FINISHED', ?)
                   ON CONFLICT(id) DO UPDATE SET
                     utc_date = excluded.utc_date,
                     home = excluded.home,
                     away = excluded.away,
                     home_score = excluded.home_score,
                     away_score = excluded.away_score,
                     status = excluded.status,
                     season = excluded.season""",
                (r["id"], r["utc_date"], r["home"], r["away"], r["home_score"], r["away_score"], r["season"]),
            )
            written += 1
    conn.commit()
    conn.close()
    print(f"Imported/updated {written} historical matches across {len(SEASON_CODES)} seasons.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually write to the database. Without this flag, only a dry-run summary is printed.",
    )
    args = parser.parse_args()

    dry_run()
    print()
    if args.commit:
        import_all()
    else:
        print("Dry run only -- no rows written. Re-run with --commit to import.")


if __name__ == "__main__":
    main()

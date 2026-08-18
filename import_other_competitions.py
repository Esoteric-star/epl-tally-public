"""Current-season import for non-PL competitions (ELC, CL), used ONLY to
enrich team_form() with recent form outside the Premier League. These
rows must never be reachable by the predictor, the leaderboard, or PL
head-to-head -- see the Phase 1 query audit for how that's enforced
(matchday left NULL, everything else explicitly filters competition='PL').

Unlike import_history.py (a one-off historical backfill from a static
CSV), this hits the live football-data.org API -- same as
fetch_matches.py -- so it's meant to be re-run periodically once
approved, not just once. Idempotent via the same ON CONFLICT(id) DO
UPDATE upsert pattern, using football-data.org's own globally-unique
match ids (no synthetic id needed here, unlike the CSV import).
"""
import argparse

from api_client import get
from db import get_conn
from teams import TEAM_MAP

# football-data.org uses the same canonical team name for a club across
# every competition it covers (verified empirically: all 6 English clubs
# in this season's Champions League data are exact string matches for
# our existing DB/TEAM_MAP names, e.g. "Arsenal FC"). This map exists as
# a safety net for any competition/club combination where that ever
# isn't true -- currently empty, nothing needed it.
NAME_MAP = {}

COMPETITIONS = ["ELC", "CL"]


def normalize_name(raw):
    return NAME_MAP.get(raw, raw)


def season_label(start_date):
    year = int(start_date[:4])
    return f"{year}-{str(year + 1)[-2:]}"


def fetch_competition(code):
    data = get(f"/competitions/{code}/matches", params={"status": "FINISHED"})
    return data.get("matches", [])


def build_rows(code):
    rows = []
    for m in fetch_competition(code):
        home_raw = m["homeTeam"]["name"]
        away_raw = m["awayTeam"]["name"]
        rows.append(
            {
                "id": m["id"],
                "competition": code,
                "season": season_label(m["season"]["startDate"]),
                "utc_date": m["utcDate"],
                "home": normalize_name(home_raw),
                "away": normalize_name(away_raw),
                "home_score": m["score"]["fullTime"]["home"],
                "away_score": m["score"]["fullTime"]["away"],
                "status": m["status"],
                "home_raw": home_raw,
                "away_raw": away_raw,
            }
        )
    return rows


def dry_run(competitions):
    unmapped = set()
    total = 0
    print(f"{'Competition':<14}{'Matches':>10}")
    for code in competitions:
        rows = build_rows(code)
        total += len(rows)
        print(f"{code:<14}{len(rows):>10}")
        for r in rows:
            if r["home_raw"] not in NAME_MAP and r["home_raw"] not in TEAM_MAP:
                unmapped.add(r["home_raw"])
            if r["away_raw"] not in NAME_MAP and r["away_raw"] not in TEAM_MAP:
                unmapped.add(r["away_raw"])
    print(f"{'TOTAL':<14}{total:>10}")
    print()
    print(f"Names stored raw -- not a current DB team ({len(unmapped)}):")
    for name in sorted(unmapped):
        print(" ", name)
    return total, unmapped


def import_all(competitions):
    conn = get_conn()
    written = 0
    for code in competitions:
        for r in build_rows(code):
            conn.execute(
                """INSERT INTO matches
                     (id, matchday, utc_date, home, away, home_score, away_score, status, season, competition)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     utc_date = excluded.utc_date,
                     home = excluded.home,
                     away = excluded.away,
                     home_score = excluded.home_score,
                     away_score = excluded.away_score,
                     status = excluded.status,
                     season = excluded.season,
                     competition = excluded.competition""",
                (
                    r["id"], r["utc_date"], r["home"], r["away"],
                    r["home_score"], r["away_score"], r["status"], r["season"], r["competition"],
                ),
            )
            written += 1
    conn.commit()
    conn.close()
    print(f"Imported/updated {written} matches across {len(competitions)} competition(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually write to the database. Without this flag, only a dry-run summary is printed.",
    )
    parser.add_argument(
        "--only", metavar="CODE,CODE",
        help=f"Comma-separated subset of {COMPETITIONS} to run (default: all).",
    )
    args = parser.parse_args()
    competitions = args.only.split(",") if args.only else COMPETITIONS

    dry_run(competitions)
    print()
    if args.commit:
        import_all(competitions)
    else:
        print("Dry run only -- no rows written. Re-run with --commit to import.")


if __name__ == "__main__":
    main()

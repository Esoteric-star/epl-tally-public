import argparse

from api_client import get
from db import get_conn


def upsert_match(conn, m):
    conn.execute(
        """INSERT INTO matches (id, matchday, utc_date, home, away, home_score, away_score, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             matchday = excluded.matchday,
             utc_date = excluded.utc_date,
             home = excluded.home,
             away = excluded.away,
             home_score = excluded.home_score,
             away_score = excluded.away_score,
             status = excluded.status""",
        (
            m["id"],
            m["matchday"],
            m["utcDate"],
            m["homeTeam"]["name"],
            m["awayTeam"]["name"],
            m["score"]["fullTime"]["home"],
            m["score"]["fullTime"]["away"],
            m["status"],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description="Fetch PL fixtures/results from football-data.org")
    parser.add_argument("--matchday", type=int, help="Fetch only this matchday (default: all matchdays)")
    args = parser.parse_args()

    params = {"matchday": args.matchday} if args.matchday else None
    data = get("/competitions/PL/matches", params=params)
    matches = data.get("matches", [])

    conn = get_conn()
    for m in matches:
        upsert_match(conn, m)
    conn.commit()
    conn.close()

    scope = f"matchday {args.matchday}" if args.matchday else "all matchdays"
    print(f"Fetched and upserted {len(matches)} matches ({scope}).")


if __name__ == "__main__":
    main()

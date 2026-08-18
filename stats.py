"""Form / upcoming-fixtures / head-to-head queries, derived entirely from
matches already stored in the DB. No network calls -- see import_history.py
for the one-time historical backfill and fetch_matches.py for the ongoing
current-season cron.

utc_date is stored as text in uniform "YYYY-MM-DDTHH:MM:SSZ" form, so a
plain SQL ORDER BY utc_date is chronologically correct (verified against
all 2,280 stored rows -- lexical order matches parsed-datetime order).
"""
from db import CURRENT_SEASON, get_conn


def _result(team_score, opp_score):
    if team_score > opp_score:
        return "W"
    if team_score < opp_score:
        return "L"
    return "D"


def team_form(team, n=5):
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM matches
           WHERE (home = ? OR away = ?) AND status = 'FINISHED'
           ORDER BY utc_date DESC
           LIMIT ?""",
        (team, team, n),
    ).fetchall()
    conn.close()

    form = []
    for r in rows:
        is_home = r["home"] == team
        team_score = r["home_score"] if is_home else r["away_score"]
        opp_score = r["away_score"] if is_home else r["home_score"]
        form.append(
            {
                "id": r["id"],
                "season": r["season"],
                "competition": r["competition"],
                "utc_date": r["utc_date"],
                "opponent": r["away"] if is_home else r["home"],
                "is_home": is_home,
                "team_score": team_score,
                "opp_score": opp_score,
                "result": _result(team_score, opp_score),
            }
        )
    return form


def team_upcoming(team, n=5):
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM matches
           WHERE (home = ? OR away = ?) AND status != 'FINISHED' AND competition = 'PL'
           ORDER BY utc_date ASC
           LIMIT ?""",
        (team, team, n),
    ).fetchall()
    conn.close()

    upcoming = []
    for r in rows:
        is_home = r["home"] == team
        upcoming.append(
            {
                "id": r["id"],
                "season": r["season"],
                "utc_date": r["utc_date"],
                "opponent": r["away"] if is_home else r["home"],
                "is_home": is_home,
                "status": r["status"],
            }
        )
    return upcoming


def head_to_head(team_a, team_b, n=10):
    conn = get_conn()
    meetings_rows = conn.execute(
        """SELECT * FROM matches
           WHERE ((home = ? AND away = ?) OR (home = ? AND away = ?))
             AND status = 'FINISHED' AND competition = 'PL'
           ORDER BY utc_date DESC
           LIMIT ?""",
        (team_a, team_b, team_b, team_a, n),
    ).fetchall()

    next_row = conn.execute(
        """SELECT * FROM matches
           WHERE ((home = ? AND away = ?) OR (home = ? AND away = ?))
             AND status != 'FINISHED'
             AND season = ? AND competition = 'PL'
           ORDER BY utc_date ASC
           LIMIT 1""",
        (team_a, team_b, team_b, team_a, CURRENT_SEASON),
    ).fetchone()
    conn.close()

    meetings = [
        {
            "id": r["id"],
            "season": r["season"],
            "utc_date": r["utc_date"],
            "home": r["home"],
            "away": r["away"],
            "home_score": r["home_score"],
            "away_score": r["away_score"],
        }
        for r in meetings_rows
    ]

    next_meeting = None
    if next_row:
        next_meeting = {
            "id": next_row["id"],
            "season": next_row["season"],
            "utc_date": next_row["utc_date"],
            "home": next_row["home"],
            "away": next_row["away"],
            "status": next_row["status"],
        }

    return {"meetings": meetings, "next": next_meeting}

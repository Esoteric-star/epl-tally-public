from db import get_conn


def outcome(h, a):
    if h > a:
        return "H"
    if h < a:
        return "A"
    return "D"


def score(pred_h, pred_a, actual_h, actual_a):
    if pred_h == actual_h and pred_a == actual_a:
        return 3, 1
    if outcome(pred_h, pred_a) == outcome(actual_h, actual_a):
        return 1, 0
    return 0, 0


def main():
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.name AS name, pr.pred_home, pr.pred_away, m.home_score, m.away_score
           FROM players p
           LEFT JOIN predictions pr ON pr.player_id = p.id
           LEFT JOIN matches m ON m.id = pr.match_id
           WHERE m.id IS NULL OR m.status = 'FINISHED'"""
    ).fetchall()
    conn.close()

    stats = {}
    for r in rows:
        name = r["name"]
        if name not in stats:
            stats[name] = {"points": 0, "exact": 0}
        if r["pred_home"] is None or r["home_score"] is None:
            continue
        pts, exact = score(r["pred_home"], r["pred_away"], r["home_score"], r["away_score"])
        stats[name]["points"] += pts
        stats[name]["exact"] += exact

    leaderboard = sorted(
        stats.items(), key=lambda kv: (-kv[1]["points"], -kv[1]["exact"], kv[0])
    )

    if not leaderboard:
        print("No players yet. Add one with players.py.")
        return

    name_width = max(len("Player"), *(len(n) for n, _ in leaderboard))
    print(f"{'Player'.ljust(name_width)}  Points  Exact")
    print(f"{'-' * name_width}  ------  -----")
    for name, s in leaderboard:
        print(f"{name.ljust(name_width)}  {str(s['points']).rjust(6)}  {str(s['exact']).rjust(5)}")


if __name__ == "__main__":
    main()

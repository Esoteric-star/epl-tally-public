import hmac
import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from db import CURRENT_SEASON, DB_PATH, PROD_DB_PATH, get_conn
from players import avatar_file, get_player, parse_utc
from settle import score
from stats import head_to_head, team_form, team_upcoming
from teams import CODE_TO_NAME, comp_view, roster_team_view, team_view

DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
# Independent of DEMO_MODE's other branding swaps -- lets a demo run show
# real club crests (e.g. for a screenshot that wants them) while keeping
# the wordmark, avatars, and competition badges as placeholders.
DEMO_SHOW_CRESTS = os.environ.get("DEMO_SHOW_CRESTS", "").lower() in ("1", "true", "yes")

# DEMO_MODE disables the passcode gate; refuse to boot rather than serve the
# live database with the gate off because DATABASE_PATH was left unset (or
# was pointed at epl.db) by mistake.
if DEMO_MODE and DB_PATH.resolve() == PROD_DB_PATH.resolve():
    raise SystemExit(
        "DEMO_MODE is on but DATABASE_PATH resolves to epl.db -- refusing to "
        "start. Set DATABASE_PATH to a separate file, e.g. DATABASE_PATH=demo.db."
    )

APP_PASSCODE = os.environ["APP_PASSCODE"]
FLASK_SECRET_KEY = os.environ["FLASK_SECRET_KEY"]

LONDON = ZoneInfo("Europe/London")
PLAYER_NAMES = ("Alex", "Sam", "Jordan") if DEMO_MODE else ("Alex", "Sam")
LOCK_THRESHOLD = 5
LOCK_MINUTES = 15

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.jinja_env.globals["avatar_file"] = avatar_file
app.jinja_env.globals["DEMO_MODE"] = DEMO_MODE
app.jinja_env.globals["DEMO_SHOW_CRESTS"] = DEMO_SHOW_CRESTS


def seed_players():
    conn = get_conn()
    for name in PLAYER_NAMES:
        conn.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


seed_players()


# ------------------------------------------------------------------
# auth helpers
# ------------------------------------------------------------------
def player_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not DEMO_MODE and not session.get("authed"):
            return redirect(url_for("gate"))
        if not session.get("player_id"):
            return redirect(url_for("who"))
        return fn(*args, **kwargs)

    return wrapper


def authed_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not DEMO_MODE and not session.get("authed"):
            return redirect(url_for("gate"))
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------------
# fixture / scoring helpers
# ------------------------------------------------------------------
def fmt_kickoff(utc_date):
    local = parse_utc(utc_date).astimezone(LONDON)
    # football-data.org stamps far-future fixtures with T00:00:00Z as a
    # placeholder until the broadcaster kickoff time is confirmed -- show
    # the date only for those, never a fake "00:00".
    time_confirmed = not utc_date.endswith("T00:00:00Z")
    return {
        "day_label": f"{local.strftime('%A')} {local.day} {local.strftime('%B')}",
        "time": local.strftime("%H:%M") if time_confirmed else None,
        "date_short": f"{local.day} {local.strftime('%b')}",
    }


def ko_display(utc_date):
    ko = fmt_kickoff(utc_date)
    return ko["time"] if ko["time"] else ko["date_short"]


def is_locked(utc_date, now):
    return parse_utc(utc_date) <= now


def with_comp(rows):
    for r in rows:
        r["comp"] = comp_view(r["competition"])
    return rows


def build_fixture(row, pred_row, now, include_stats=False):
    ko = fmt_kickoff(row["utc_date"])
    display_time = ko["time"] if ko["time"] else ko["date_short"]
    locked = is_locked(row["utc_date"], now)

    pred = None
    if pred_row and pred_row["pred_home"] is not None:
        pred = (pred_row["pred_home"], pred_row["pred_away"])
    actual = None
    if row["home_score"] is not None:
        actual = (row["home_score"], row["away_score"])

    points = None
    if pred and actual and row["status"] == "FINISHED":
        points, _ = score(pred[0], pred[1], actual[0], actual[1])

    sides = []
    for i, key in enumerate(("home", "away")):
        team = team_view(row[key])
        p = pred[i] if pred else None
        a = actual[i] if actual else None
        other_a = actual[1 - i] if actual else None
        sides.append(
            {
                "code": team["code"],
                "colour": team["colour"],
                "name": team["name"],
                "badge_file": team["badge_file"],
                "pred": p,
                "actual": a,
                "lose": a is not None and other_a is not None and a < other_a,
                "hit": p is not None and a is not None and p == a,
                "input_name": f"{'h' if i == 0 else 'a'}_{row['id']}",
            }
        )

    if row["status"] == "IN_PLAY":
        tag = {"text": "Live", "cls": "tag--live"}
    elif row["status"] == "FINISHED":
        if points is None:
            tag = {"text": "No prediction", "cls": ""}
        else:
            tag = {"text": f"+{points} {'point' if points == 1 else 'points'}", "cls": f"tag--p{points}"}
    elif locked:
        tag = {"text": "Locked", "cls": ""}
    else:
        tag = {"text": "Open", "cls": "tag--open"}

    foot = None
    if locked:
        if row["status"] == "IN_PLAY":
            foot = "Kicked off — predictions closed"
        elif row["status"] == "FINISHED":
            foot = "Full time"
        else:
            foot = "Kicked off — predictions closed"

    stats = None
    if include_stats:
        h2h_meetings = head_to_head(row["home"], row["away"], n=4)["meetings"]
        stats = {
            "home_form": with_comp(team_form(row["home"], n=5)),
            "away_form": with_comp(team_form(row["away"], n=5)),
            "h2h": [
                {
                    **m,
                    "home_short": team_view(m["home"])["name"],
                    "away_short": team_view(m["away"])["name"],
                }
                for m in h2h_meetings
            ],
            "kickoff_display": display_time,
        }

    return {
        "id": row["id"],
        "time": display_time,
        "day_label": ko["day_label"],
        "status": row["status"],
        "locked": locked,
        "points": points,
        "home": sides[0],
        "away": sides[1],
        "tag": tag,
        "foot": foot,
        "stats": stats,
    }


def default_matchday():
    # season-scoped: historical import rows (season != CURRENT_SEASON,
    # matchday NULL) must never leak into "what matchday is live now".
    conn = get_conn()
    rows = conn.execute(
        "SELECT matchday, utc_date FROM matches WHERE season = ? AND competition = 'PL' ORDER BY utc_date",
        (CURRENT_SEASON,),
    ).fetchall()
    conn.close()
    now = datetime.now(timezone.utc)
    for r in rows:
        if parse_utc(r["utc_date"]) > now:
            return r["matchday"]
    return rows[-1]["matchday"] if rows else 1


def matchday_strip(conn, now):
    rows = conn.execute(
        "SELECT matchday, utc_date FROM matches WHERE season = ? AND competition = 'PL' ORDER BY matchday",
        (CURRENT_SEASON,),
    ).fetchall()
    open_counts = {}
    for r in rows:
        open_counts.setdefault(r["matchday"], 0)
        if parse_utc(r["utc_date"]) > now:
            open_counts[r["matchday"]] += 1
    return [{"md": md, "open": n} for md, n in sorted(open_counts.items())]


def load_fixtures(conn, matchday, player_id, now, include_stats=False):
    rows = conn.execute(
        "SELECT * FROM matches WHERE matchday = ? ORDER BY utc_date", (matchday,)
    ).fetchall()
    preds = conn.execute(
        "SELECT match_id, pred_home, pred_away FROM predictions WHERE player_id = ?",
        (player_id,),
    ).fetchall()
    pred_map = {p["match_id"]: p for p in preds}

    fixtures = []
    last_day = None
    for row in rows:
        f = build_fixture(row, pred_map.get(row["id"]), now, include_stats=include_stats)
        f["show_day"] = f["day_label"] != last_day
        last_day = f["day_label"]
        fixtures.append(f)
    return fixtures


def leaderboard():
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.name AS name, pr.pred_home, pr.pred_away, m.home_score, m.away_score, m.status
           FROM players p
           LEFT JOIN predictions pr ON pr.player_id = p.id
           LEFT JOIN matches m ON m.id = pr.match_id"""
    ).fetchall()
    conn.close()

    stats = {name: {"points": 0, "exact": 0, "played": 0} for name in PLAYER_NAMES}
    for r in rows:
        if r["status"] != "FINISHED" or r["pred_home"] is None or r["home_score"] is None:
            continue
        pts, exact = score(r["pred_home"], r["pred_away"], r["home_score"], r["away_score"])
        stats[r["name"]]["points"] += pts
        stats[r["name"]]["exact"] += exact
        stats[r["name"]]["played"] += 1

    ranked = sorted(stats.items(), key=lambda kv: (-kv[1]["points"], -kv[1]["exact"], kv[0]))
    return [
        {"name": name, "position": i + 1, **s}
        for i, (name, s) in enumerate(ranked)
    ]


def last5_form():
    # season-scoped for the same reason as default_matchday(): otherwise,
    # once fewer than 5 current-season matches have finished, this would
    # backfill with unrelated historical results nobody predicted on.
    conn = get_conn()
    finished = conn.execute(
        "SELECT id, home_score, away_score FROM matches WHERE status = 'FINISHED' AND season = ? AND competition = 'PL' ORDER BY utc_date ASC",
        (CURRENT_SEASON,),
    ).fetchall()
    last5 = finished[-5:]
    form = {name: [] for name in PLAYER_NAMES}
    if not last5:
        conn.close()
        return form

    match_ids = [m["id"] for m in last5]
    placeholders = ",".join("?" * len(match_ids))
    preds = conn.execute(
        f"""SELECT p.name, pr.match_id, pr.pred_home, pr.pred_away
            FROM predictions pr JOIN players p ON p.id = pr.player_id
            WHERE pr.match_id IN ({placeholders})""",
        match_ids,
    ).fetchall()
    conn.close()

    pred_map = {(r["name"], r["match_id"]): (r["pred_home"], r["pred_away"]) for r in preds}
    for name in PLAYER_NAMES:
        for m in last5:
            p = pred_map.get((name, m["id"]))
            if p is None:
                form[name].append(None)
            else:
                pts, _ = score(p[0], p[1], m["home_score"], m["away_score"])
                form[name].append(pts)
    return form


# ------------------------------------------------------------------
# routes
# ------------------------------------------------------------------
@app.route("/")
def gate():
    if DEMO_MODE or session.get("authed"):
        if session.get("player_id"):
            return redirect(url_for("predict"))
        return redirect(url_for("who"))
    return render_template("gate.html")


@app.route("/auth", methods=["POST"])
def auth():
    ip = request.remote_addr or "unknown"
    now = datetime.now(timezone.utc)
    conn = get_conn()
    row = conn.execute(
        "SELECT fail_count, locked_until FROM auth_attempts WHERE ip = ?", (ip,)
    ).fetchone()

    if row and row["locked_until"]:
        locked_until = datetime.fromisoformat(row["locked_until"])
        if now < locked_until:
            remaining = max(1, int((locked_until - now).total_seconds() // 60) + 1)
            conn.close()
            flash(f"Too many attempts. Try again in {remaining} minute(s).", "error")
            return redirect(url_for("gate"))

    submitted = request.form.get("passcode", "")
    if hmac.compare_digest(submitted.strip().upper(), APP_PASSCODE.strip().upper()):
        conn.execute("DELETE FROM auth_attempts WHERE ip = ?", (ip,))
        conn.commit()
        conn.close()
        session.clear()
        session["authed"] = True
        session.permanent = True
        return redirect(url_for("who"))

    fail_count = (row["fail_count"] if row else 0) + 1
    locked_until = None
    if fail_count >= LOCK_THRESHOLD:
        locked_until = (now + timedelta(minutes=LOCK_MINUTES)).isoformat()
    conn.execute(
        """INSERT INTO auth_attempts (ip, fail_count, locked_until) VALUES (?, ?, ?)
           ON CONFLICT(ip) DO UPDATE SET
             fail_count = excluded.fail_count, locked_until = excluded.locked_until""",
        (ip, fail_count, locked_until),
    )
    conn.commit()
    conn.close()

    if locked_until:
        flash(f"Too many attempts. Locked for {LOCK_MINUTES} minutes.", "error")
    else:
        flash("That passcode isn't right. Try again.", "error")
    return redirect(url_for("gate"))


@app.route("/who", methods=["GET", "POST"])
@authed_required
def who():
    if request.method == "POST":
        name = request.form.get("player", "")
        if name not in PLAYER_NAMES:
            flash("Pick a valid player.", "error")
            return redirect(url_for("who"))
        conn = get_conn()
        player = get_player(conn, name)
        conn.close()
        session["player_id"] = player["id"]
        session["player_name"] = player["name"]
        return redirect(url_for("predict"))

    return render_template("who.html", players=leaderboard())


@app.route("/predict", methods=["GET"])
@player_required
def predict():
    now = datetime.now(timezone.utc)
    matchday = request.args.get("matchday", type=int) or default_matchday()
    conn = get_conn()
    strip = matchday_strip(conn, now)
    fixtures = load_fixtures(conn, matchday, session["player_id"], now, include_stats=True)
    conn.close()

    open_n = sum(1 for f in fixtures if not f["locked"])
    done_n = sum(1 for f in fixtures if not f["locked"] and f["home"]["pred"] is not None)

    return render_template(
        "predict.html",
        fixtures=fixtures,
        strip=strip,
        matchday=matchday,
        open_n=open_n,
        done_n=done_n,
        me=session.get("player_name"),
    )


@app.route("/predict", methods=["POST"])
@player_required
def predict_post():
    matchday = request.form.get("matchday", type=int) or default_matchday()
    now = datetime.now(timezone.utc)
    conn = get_conn()

    saved = 0
    rejected = []
    for key in list(request.form.keys()):
        m = re.fullmatch(r"h_(\d+)", key)
        if not m:
            continue
        match_id = int(m.group(1))
        h_raw = request.form.get(f"h_{match_id}", "")
        a_raw = request.form.get(f"a_{match_id}", "")
        if h_raw == "" or a_raw == "":
            continue
        try:
            h, a = int(h_raw), int(a_raw)
        except ValueError:
            continue
        if not (0 <= h <= 19) or not (0 <= a <= 19):
            continue

        row = conn.execute(
            "SELECT utc_date, home, away FROM matches WHERE id = ? AND competition = 'PL'", (match_id,)
        ).fetchone()
        if row is None:
            continue
        if is_locked(row["utc_date"], now):
            rejected.append(f"{row['home']} vs {row['away']}")
            continue

        conn.execute(
            """INSERT INTO predictions (player_id, match_id, pred_home, pred_away)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(player_id, match_id) DO UPDATE SET
                 pred_home = excluded.pred_home, pred_away = excluded.pred_away""",
            (session["player_id"], match_id, h, a),
        )
        saved += 1

    conn.commit()
    conn.close()

    if saved:
        flash(f"{saved} prediction{'s' if saved != 1 else ''} saved.", "success")
    if rejected:
        flash(
            "Not saved — kickoff had already passed for: " + ", ".join(rejected),
            "error",
        )
    if not saved and not rejected:
        flash("No changes to save.", "info")

    return redirect(url_for("predict", matchday=matchday))


@app.route("/mine")
@player_required
def mine():
    now = datetime.now(timezone.utc)
    matchday = request.args.get("matchday", type=int) or default_matchday()
    conn = get_conn()
    strip = matchday_strip(conn, now)
    fixtures = load_fixtures(conn, matchday, session["player_id"], now)
    conn.close()

    missing = sum(1 for f in fixtures if f["home"]["pred"] is None)
    settled = sum(1 for f in fixtures if f["status"] == "FINISHED")
    earned = sum(f["points"] or 0 for f in fixtures)
    exact = sum(1 for f in fixtures if f["points"] == 3)
    any_activity = any(f["home"]["pred"] is not None or f["locked"] for f in fixtures)

    return render_template(
        "mine.html",
        fixtures=fixtures,
        strip=strip,
        matchday=matchday,
        missing=missing,
        settled=settled,
        earned=earned,
        exact=exact,
        any_activity=any_activity,
        me=session.get("player_name"),
    )


@app.route("/table")
@authed_required
def table():
    board = leaderboard()
    form = last5_form()
    for row in board:
        row["form"] = form.get(row["name"], [])

    current_md = default_matchday()
    now = datetime.now(timezone.utc)
    conn = get_conn()
    md_rows = conn.execute(
        "SELECT utc_date, status FROM matches WHERE matchday = ?", (current_md,)
    ).fetchall()
    conn.close()
    live = sum(1 for r in md_rows if r["status"] == "IN_PLAY")
    open_count = sum(1 for r in md_rows if not is_locked(r["utc_date"], now))

    leader = board[0] if board else None
    runner_up = board[1] if len(board) > 1 else None
    gap = (leader["points"] - runner_up["points"]) if leader and runner_up else 0

    return render_template(
        "table.html",
        board=board,
        current_md=current_md,
        live=live,
        open_count=open_count,
        leader=leader,
        runner_up=runner_up,
        gap=gap,
        me=session.get("player_name"),
    )


@app.route("/team/<code>")
@authed_required
def team_page(code):
    full_name = CODE_TO_NAME.get(code.upper())
    if not full_name:
        abort(404)

    view = team_view(full_name)

    form_rows = with_comp(team_form(full_name, n=5))
    for r in form_rows:
        r["opponent_view"] = roster_team_view(r["opponent"])
        r["date_short"] = fmt_kickoff(r["utc_date"])["date_short"]

    upcoming_rows = team_upcoming(full_name, n=5)
    for r in upcoming_rows:
        r["opponent_view"] = roster_team_view(r["opponent"])
        r["ko_display"] = ko_display(r["utc_date"])

    return render_template(
        "team.html",
        team=view,
        form=form_rows,
        upcoming=upcoming_rows,
        me=session.get("player_name"),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)

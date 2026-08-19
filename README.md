
/











Readme · MD
EPL Tally
A private Premier League score prediction app. You pick a scoreline for each upcoming fixture, and points get settled automatically once the results are in.

I built and deployed the whole thing myself: data pipeline, scoring engine, web app, server, TLS, the lot. It runs on a single Hetzner VPS behind nginx.

Status: live and in use for the full season, no downtime worth mentioning.

Screenshots
Fixtures	Table	My picks
Show Image	Show Image	Show Image
Captured in DEMO_MODE (fictional players, fictional predictions) with DEMO_SHOW_CRESTS=true so the crest art shows up in the shot. See seed_demo.py and the demo mode notes below. The wordmark, avatars, and competition badges stay as placeholders even with crests switched on.

Demo mode
DEMO_MODE skips the passcode gate and swaps in placeholder branding, so you can have a look round without touching the real data:

bash
python3 seed_demo.py    # builds demo.db from scratch; never touches epl.db
DEMO_MODE=1 DATABASE_PATH=demo.db DEMO_SHOW_CRESTS=1 flask run
DATABASE_PATH=demo.db matters here. Leave it out and DEMO_MODE will drop the passcode gate in front of the real database, which you don't want. Drop DEMO_SHOW_CRESTS if you'd rather see the text-code fallback instead of the crest art.

Scoring rules
Outcome	Points
Exact scoreline	3
Correct result, wrong scoreline	1
Wrong result	0
Ties are broken by exact scorelines first, then alphabetically. Predictions lock at kick-off, and that's enforced server-side too, not just hidden in the UI, so you can't get round it by poking about in devtools.

Architecture
fetch_matches.py pulls fixtures and results from the football-data.org API every six hours via cron, and writes them into epl.db (SQLite). Historical seasons went in once, via import_history.py, sourced from public domain CSVs on footballcsv and datahub.io. settle.py reads results back out of epl.db and works out everyone's points.

On the web side, nginx handles TLS on :443 and passes requests through to gunicorn on 127.0.0.1:8000, which runs the Flask app and renders the Jinja2 templates. Browsers never touch football-data.org directly, they only ever hit the local app.

Stack: Python 3, Flask, Jinja2, gunicorn, SQLite, nginx, certbot, systemd, UFW. No frontend framework, no build step.

Repository layout
fetch_matches.py     Pull fixtures and results from football-data.org
import_history.py    One-off backfill of historical seasons from CSV
settle.py            Scoring engine, awards points for completed fixtures
players.py           Player management
teams.py             Team reference data and normalisation
stats.py             Aggregate stats and leaderboard queries
app.py               Flask routes and view logic
templates/           Jinja2 templates (5 screens)
static/              CSS and minimal JS
.env.example         Configuration template
Data
Live data: football-data.org free tier, competition code PL. Chosen deliberately over scraping, more on that below.
Historical data: public-domain CSVs (footballcsv / datahub.io), backfilled once via import_history.py.
Volume: 2,469 matches across 6 Premier League seasons, plus Champions League fixtures.
Team names don't match up between the API and the historical CSVs, "Spurs" versus "Tottenham Hotspur FC" and so on. teams.py holds a canonical team table with an alias map, so both sources resolve to the same team ID instead of creating duplicates.

Design
Mobile first, because that's the only way anyone actually uses it. It also gives it the feel of an app without the hassle and cost of getting into an app store.

Light grey canvas, white cards, Inter typeface, one accent colour, dark header. The look is borrowed from broadcaster sport pages on purpose. A mate of mine said he's on the BBC Sport app most days, so that's the direction I went with.

Two decisions I went back and forth on:

Crest badges. I nearly stripped these out for a flatter, purely typographic list. Kept them in the end. On a phone, at a glance, a crest is quicker to read than a team name, and the fixture list is the screen that gets the most traffic by far.
The leaderboard header. A dark block with a generated one-line summary ("It's all square at the top") rather than dropping straight into the table. It breaks up the otherwise uniform light UI on purpose. That's the one screen everybody actually cares about, so it earns the bit of contrast.
Score inputs are stepper controls rather than free text. Predictions are almost always 0 to 3, steppers dodge the numeric keyboard entirely, and there is no way to type in an invalid value.

Club crests, competition badges, and player avatar images are not distributed with this repo. The UI falls back to text codes and name initials when those files are absent, so the app runs unmodified without them.

I used AI image and layout tools to knock together reference mock-ups while exploring directions. The implemented markup, CSS, and final design decisions are my own.

Engineering decisions
Official API over a scraper. There was an existing GitHub scraper I could have used for fixture data, and it would have been the quicker route. I used the official football-data.org API instead. It's within their terms, it has a documented schema, and it won't break the first time somebody changes a CSS class on the page it would have been scraping. The free tier's rate limit is the constraint that shapes the polling design.

Poll on a schedule, not on request. Fixtures refresh via cron every six hours into SQLite. Web requests only ever read local data. Page loads stay fast, the app survives an upstream outage, and the rate limit never becomes a user-facing problem.

nginx over Caddy. Caddy would have meant fewer moving parts for automatic TLS, and on a clean box it's the better choice. This box already runs nginx for a separate project though, so the two would have been contending for :80 and :443. Reusing the existing reverse proxy and adding certbot was the right call for this server, even if Caddy would win on a greenfield build.

SQLite over Postgres. Two users, a few thousand rows, read-heavy. Postgres would be operational overhead for no real benefit. The schema is portable enough if that ever needs to change.

Settlement is idempotent. settle.py can be re-run over any matchday without double-awarding points. Scoring is derived from stored results rather than incremented in place, so a bad run gets fixed by running it again, not by going in and manually repairing the points table.

Security
The app is passcode-gated rather than account-based, which is the right level for a two-person private app, and it's one fewer credential store to get wrong.

Shared passcode with SQLite-backed rate limiting: 5 attempts, then a 15-minute lockout keyed on client identity, enforced server-side.
Name selection bound to the session, so predictions can't be written on another player's behalf by editing the request.
All secrets in .env (chmod 600, gitignored). Nothing sensitive is committed and nothing sensitive reaches the client.
Parameterised SQL throughout, no string-built queries.
TLS via certbot with automatic renewal. UFW default-deny, only 22/80/443 open.
SSH hardened: ed25519 key authentication only, password auth disabled.
Running locally
bash
git clone https://github.com/Esoteric-star/epl-tally-public.git
cd epl-tally
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # add your football-data.org token
python3 teams.py --init   # seed team reference data
python3 fetch_matches.py  # pull current season fixtures
python3 seed_demo.py      # optional: demo players and predictions

flask run
Free API tokens are available from football-data.org.

Deployment
Production runs under systemd with gunicorn bound to 127.0.0.1:8000 (TCP, loopback only), proxied by nginx. Example unit and server-block files are in deploy/ as .example templates. Populate the domain and paths for your own environment.

bash
systemctl status epl-tally
journalctl -u epl-tally -f
Fixture refresh is a cron entry that sources .env explicitly before running. Cron does not inherit a login shell environment, so skip this and the job just fails quietly:

cron
0 */6 * * * cd /opt/epl-tally && set -a && . .env && set +a && \
  /opt/epl-tally/venv/bin/python fetch_matches.py >> /var/log/epl-tally.log 2>&1
Next
Cup competition support (Champions League data is already in the schema)
Per-matchday form and streak stats
Push notification when a matchday is settled
Licence
MIT. Football data is provided by football-data.org under their terms; historical CSVs are public domain.



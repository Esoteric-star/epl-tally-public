# EPL Tally

A private Premier League score-prediction app. Users predict exact scorelines for
upcoming fixtures, and points are settled automatically once results come in.

Built and deployed end to end: data pipeline, scoring engine, web app, server,
TLS, and hardening. Runs on a single Hetzner VPS behind nginx.

**Status:** live in production, in continuous use across a full season.

---

## Scoring rules

| Outcome | Points |
|---|---|
| Exact scoreline | 3 |
| Correct result, wrong scoreline | 1 |
| Wrong result | 0 |

Ties are broken by number of exact scorelines, then alphabetically by name.
Predictions lock at kick-off; late entries are rejected server-side, not just
hidden in the UI.

---

## Architecture

```
                    ┌──────────────────────┐
   football-data.org│  fetch_matches.py    │  cron, every 6h
   REST API ───────▶│  (fixtures/results)  │──┐
                    └──────────────────────┘  │
                                              ▼
   footballcsv /     ┌──────────────────────┐ ┌──────────┐
   datahub.io ──────▶│  import_history.py   │▶│ epl.db   │
   (public domain)   │  (6 seasons backfill)│ │ SQLite   │
                     └──────────────────────┘ └────┬─────┘
                                                   │
                     ┌──────────────────────┐      │
                     │  settle.py           │◀─────┤
                     │  (scoring engine)    │──────┘
                     └──────────────────────┘
                                                   │
   Browser ──▶ nginx (TLS) ──▶ gunicorn ──▶ Flask ─┘
                 :443          127.0.0.1:8000  Jinja2
```

**Stack:** Python 3 · Flask · Jinja2 · gunicorn · SQLite · nginx · certbot ·
systemd · UFW. No frontend framework, no build step.

---

## Repository layout

```
fetch_matches.py     Pull fixtures and results from football-data.org
import_history.py    One-off backfill of historical seasons from CSV
settle.py            Scoring engine — awards points for completed fixtures
players.py           Player management
teams.py             Team reference data and normalisation
stats.py             Aggregate stats and leaderboard queries
app.py               Flask routes and view logic
templates/           Jinja2 templates (5 screens)
static/              CSS and minimal JS
.env.example         Configuration template
```

---

## Data

- **Live data:** [football-data.org](https://www.football-data.org/) free tier,
  competition code `PL`. Chosen deliberately over scraping — see decisions below.
- **Historical data:** public-domain CSVs (footballcsv / datahub.io), backfilled
  once via `import_history.py`.
- **Volume:** 2,469 matches across 6 Premier League seasons, plus Champions
  League fixtures.

Team names differ between the API and the historical CSVs ("Spurs" vs "Tottenham
Hotspur FC", and so on). `teams.py` holds a canonical team table with an alias
map, so both sources resolve to the same team ID rather than creating duplicates.

---

## Design

Mobile-first, because that is the only way it is ever used — thirty seconds at a
time, usually on the way somewhere. The priority was scanning speed over
character.

Light grey canvas, white cards, Inter, a single accent colour, dark header. The
patterns are borrowed from broadcaster sport pages on purpose: pill tabs for
matchday selection, day-grouped fixture lists, a status chip per fixture. Nobody
has to learn the interface.

Two decisions I went back and forth on:

- **Crest badges.** Considered stripping them for a flatter, purely typographic
  list. Kept them: at a glance on a phone, a crest is faster to identify than a
  team name, and the fixture list is the screen that gets the most traffic.
- **The leaderboard header.** A dark block with a generated one-line summary
  ("It's all square at the top") rather than dropping straight into the table.
  It breaks the otherwise uniform light UI, which is the point — it is the one
  piece of the app anyone actually cares about.

Score inputs are stepper controls rather than free text. Predictions are almost
always 0–3, steppers avoid the numeric keyboard entirely, and the input cannot
produce an invalid value.

> Club crests, competition badges, and player avatar images are not distributed
> with this repo. The UI falls back to text codes and name initials when those
> files are absent, so the app runs unmodified without them.

I used AI image and layout tools to generate reference mock-ups while exploring
directions; the implemented markup, CSS, and final design decisions are my own.

---

## Engineering decisions

**Official API over a scraper.**
The obvious shortcut was an existing GitHub scraper for fixture data. I used the
official football-data.org API instead — it is within terms, has a documented
schema, and does not break the first time someone changes a CSS class. The free
tier's rate limit is the constraint that shapes the polling design.

**Poll on a schedule, not on request.**
Fixtures refresh via cron every six hours into SQLite; web requests only ever
read local data. Page loads stay fast, the app survives an upstream outage, and
the rate limit is never a user-facing failure mode.

**nginx over Caddy.**
Caddy would have been fewer moving parts for automatic TLS. The box already runs
nginx for a separate project, so the two would have contended for :80/:443.
Reusing the existing reverse proxy and adding certbot was the correct call for
this server, even though Caddy is the better greenfield choice.

**SQLite over Postgres.**
Two users, a few thousand rows, read-heavy. Postgres would be operational
overhead with no benefit. The schema is portable if that ever changes.

**Settlement is idempotent.**
`settle.py` can be re-run over any matchday without double-awarding points.
Scoring is derived from stored results rather than incremented in place, so a bad
run is fixed by re-running it, not by manual repair of the points table.

---

## Security

The app is passcode-gated rather than account-based — appropriate for a two-person
private app, and one fewer credential store to get wrong.

- Shared passcode with SQLite-backed rate limiting: 5 attempts, then a 15-minute
  lockout keyed on client identity, enforced server-side.
- Name selection bound to the session; predictions cannot be written on another
  player's behalf by editing the request.
- All secrets in `.env` (`chmod 600`, gitignored). Nothing sensitive is committed
  and nothing sensitive reaches the client.
- Parameterised SQL throughout; no string-built queries.
- TLS via certbot with automatic renewal. UFW default-deny, only 22/80/443 open.
- SSH hardened: ed25519 key authentication only, password auth disabled.

---

## Running locally

```bash
git clone https://github.com/Esoteric-star/epl-tally-public.git
cd epl-tally
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # add your football-data.org token
python3 teams.py --init   # seed team reference data
python3 fetch_matches.py  # pull current season fixtures
python3 seed_demo.py      # optional: demo players and predictions

flask run
```

Free API tokens are available from football-data.org.

---

## Deployment

Production runs under systemd with gunicorn bound to `127.0.0.1:8000` (TCP,
loopback only), proxied by nginx. Example unit and server-block files are in
`deploy/` as `.example` templates — populate the domain and paths for your own
environment.

```bash
systemctl status epl-tally
journalctl -u epl-tally -f
```

Fixture refresh is a cron entry that sources `.env` explicitly before running —
cron does not inherit a login shell environment:

```cron
0 */6 * * * cd /opt/epl-tally && set -a && . .env && set +a && \
  /opt/epl-tally/venv/bin/python fetch_matches.py >> /var/log/epl-tally.log 2>&1
```

---

## Next

- Cup competition support (Champions League data is already in the schema)
- Per-matchday form and streak stats
- Push notification when a matchday is settled

---

## Licence

MIT. Football data is provided by football-data.org under their terms; historical
CSVs are public domain.

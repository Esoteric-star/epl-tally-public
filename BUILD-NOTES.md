# Build notes

A record of how this was built and the problems that came up. Written mainly for
my own reference, and because the failures are more instructive than the plan.

---

## Phase 1 — Data before anything else

The temptation was to start with the UI, because that is the visible part. I
started with the data instead, on the assumption that if the fixture pipeline was
unreliable everything downstream would be worthless.

**Sourcing.** The quickest option was a community GitHub repo scraping fixture
tables. I rejected it: no terms coverage, no schema guarantee, and it breaks
silently when the source page changes. Registered for a free
[football-data.org](https://www.football-data.org/) token instead — documented
JSON, a published rate limit, and legitimate.

**Schema.** Four core tables:

```
teams        (id, name, short_name, tla)
matches      (id, season, matchday, home_team, away_team, utc_date,
              status, home_score, away_score)
players      (id, name)
predictions  (id, player_id, match_id, home_pred, away_pred, created_at)
```

Points are not stored on `predictions`. They are derived from `matches` at read
time. This turned out to matter later — see settlement below.

**Backfill.** Historical seasons came from public-domain CSVs
(footballcsv / datahub.io) via `import_history.py`. 2,469 matches across six
seasons.

**Problem: team names did not match.** The API returns `Tottenham Hotspur FC`;
the CSVs return `Spurs`, `Tottenham`, or `Tottenham Hotspur` depending on the
season. A naive import created three Tottenhams. Fixed by adding a canonical
teams table plus an alias map in `teams.py`, and resolving every import through
it. Ran the backfill again from a clean database rather than trying to merge the
duplicates — cheaper and less error-prone.

---

## Phase 2 — Scoring engine

`settle.py` walks finished fixtures, compares each prediction to the result, and
awards 3 / 1 / 0.

**Design constraint I set up front: settlement must be idempotent.** The first
version incremented a running total on the player row. That is fragile — one
double-run and the leaderboard is silently wrong with no way to detect it. Any
manual correction is then guesswork.

Rewrote it so points are always computed from stored results. Re-running
`settle.py` over the whole season is safe and produces the same answer every
time. Recovery from a bad run is `python3 settle.py` again, not surgery on a
points table.

**Tiebreaks.** Equal points broken by number of exact scorelines, then
alphabetically. Alphabetical is arbitrary but it is deterministic, which is the
actual requirement — the leaderboard must not reorder between page loads.

**Lock enforcement.** Predictions lock at kick-off. First version hid the input
after kick-off. That is not a lock; it is a suggestion. Moved the check to the
route handler, so a crafted POST after kick-off is rejected server-side.

---

## Phase 3 — Fetching on a schedule

Polling on page load would have been simpler but puts the free-tier rate limit
directly in the user's path — a burst of refreshes and the app 429s.

`fetch_matches.py` runs on cron every six hours and writes to SQLite. Web
requests only read local data. Page loads are fast, and an upstream outage
degrades to stale fixtures rather than an error page.

**Problem: the cron job silently did nothing.** Worked perfectly by hand, no
output from cron. Root cause: cron runs with a near-empty environment and does
not source shell profiles, so `.env` was never loaded and the API token was
absent. The script's error handling swallowed the failure.

Fix:

```cron
0 */6 * * * cd /opt/epl-tally && set -a && . .env && set +a && \
  /opt/epl-tally/venv/bin/python fetch_matches.py >> /var/log/epl-tally.log 2>&1
```

Two lessons kept: source `.env` explicitly in any cron entry, and always redirect
cron output to a log. The bug was invisible for a day purely because nothing was
being written anywhere.

---

## Phase 4 — Frontend

Five screens: passcode gate, name picker, predictions by matchday, my
predictions, leaderboard.

Prototyped as a single self-contained HTML file with inline CSS before touching
Flask — faster iteration on layout without templating in the way. Split into
Jinja2 templates once the layout was settled.

**Direction: borrowed, not invented.** Mobile-first, patterns lifted from
broadcaster sport pages — pill tabs for matchday, day-grouped fixtures, a status
chip per match. Light grey canvas, white cards, Inter, one accent colour, dark
header. The goal was that nobody has to learn it.

**Score entry was the one real interaction problem.** Free-text number inputs
meant summoning a numeric keyboard for twenty values per matchday, and accepting
whatever was typed. Replaced with `−` / `+` steppers: no keyboard, larger tap
targets, and invalid values are unrepresentable rather than validated after the
fact.

**Two things I went back and forth on:**

- *Crest badges.* Tried a flat typographic list without them. Kept the crests —
  on a phone, a crest resolves faster than a team name, and the fixture list is
  the highest-traffic screen. The alternative build with three-letter codes is
  still in the CSS behind a flag.
- *The dark leaderboard header.* It breaks the otherwise uniform light UI.
  Considered flattening it to a white card for consistency, decided against —
  the standings are the only thing anyone opens the app for, and the summary
  line ("It's all square at the top") is generated from the actual gap between
  the top two.

I used AI image and layout tools during this phase to generate reference mock-ups
and explore directions quickly. The implemented markup and CSS, and the design
judgements above, are mine.

No framework, no build step. For five server-rendered screens, a bundler would
have been overhead with nothing to show for it.

---

## Phase 5 — Deployment

Hetzner VPS, Ubuntu. gunicorn under systemd, nginx in front, certbot for TLS.

**Reverse proxy choice.** Caddy was the obvious pick — automatic TLS, minimal
config. Ruled out because the box already runs nginx for another project and both
want :80 and :443. Fighting that would have meant either moving the existing
service or a container layer, neither justified for this. Added a server block to
the existing nginx and paired it with certbot. Correct decision for this
server; on a clean box I would use Caddy.

**Problem: SSH key auth stopped working after hardening.** Correct key,
correct `authorized_keys`, correct permissions on `.ssh` and `authorized_keys` —
still prompted for a password. Password auth was already disabled, so this was
close to a lockout.

`journalctl -u ssh` had the answer: sshd refuses key auth if any directory in the
path to `authorized_keys` is group- or world-writable, including the home
directory itself. Permissions were `drwx--x`. Set to `drwx------` and it worked
immediately.

Worth knowing generally: sshd's strict-mode failures are logged clearly but never
surfaced to the client, so the client-side symptom tells you nothing. Read the
server log first.

**Firewall.** UFW default-deny inbound, allow 22/80/443 only. gunicorn binds to
127.0.0.1:8000 — TCP, but loopback-only — so it is not reachable from outside
the box at all.

**Secrets.** `.env`, `chmod 600`, gitignored from the first commit. Nothing
sensitive in the repo, nothing sensitive rendered to the client.

---

## What I would do differently

- **Alias table from the start.** Reconciling team names is the kind of dull data
  problem that is trivial before the import and annoying afterwards.
- **Log everything the cron job does, from day one.** A silent job is
  indistinguishable from a working one.
- **Prototype the UI in the boring style first.** The characterful version was an
  hour I did not need to spend to learn something I could have reasoned about.
- **Not root.** The first deploy ran out of `/root` as root because it was
  quickest. Moved to a dedicated service user with `nologin` and `/opt`. Should
  have been that way from the first `systemctl enable`.

---

## Open items

- Cup competition support — Champions League fixtures are already in the schema
- Per-matchday form and streak stats
- Notification on matchday settlement

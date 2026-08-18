# full DB team name -> (3-letter code, badge colour, short display name)
# Exactly the 20 teams in epl.db for the current season. Coventry/Hull/
# Ipswich aren't in the original mockup's roster, so use each club's own
# primary colour instead of one borrowed from the mockup.
from pathlib import Path

BADGES_DIR = Path(__file__).resolve().parent / "static" / "badges"

TEAM_MAP = {
    "AFC Bournemouth":            ("BOU", "#DA291C", "Bournemouth"),
    "Arsenal FC":                 ("ARS", "#EF0107", "Arsenal"),
    "Aston Villa FC":             ("AVL", "#670E36", "Aston Villa"),
    "Brentford FC":                ("BRE", "#D20000", "Brentford"),
    "Brighton & Hove Albion FC":  ("BHA", "#0057B8", "Brighton"),
    "Chelsea FC":                  ("CHE", "#034694", "Chelsea"),
    "Coventry City FC":            ("COV", "#4B9CD3", "Coventry"),
    "Crystal Palace FC":           ("CRY", "#1B458F", "Crystal Palace"),
    "Everton FC":                  ("EVE", "#003399", "Everton"),
    "Fulham FC":                   ("FUL", "#000000", "Fulham"),
    "Hull City AFC":               ("HUL", "#F5A12D", "Hull City"),
    "Ipswich Town FC":             ("IPS", "#0044A9", "Ipswich"),
    "Leeds United FC":             ("LEE", "#C4A11B", "Leeds"),
    "Liverpool FC":                ("LIV", "#C8102E", "Liverpool"),
    "Manchester City FC":          ("MCI", "#2A7FB0", "Man City"),
    "Manchester United FC":        ("MUN", "#DA291C", "Man Utd"),
    "Newcastle United FC":         ("NEW", "#241F20", "Newcastle"),
    "Nottingham Forest FC":        ("NFO", "#DD0000", "Nott'm Forest"),
    "Sunderland AFC":              ("SUN", "#EB172B", "Sunderland"),
    "Tottenham Hotspur FC":        ("TOT", "#132257", "Spurs"),
}


def team_view(full_name):
    code, colour, short = TEAM_MAP.get(full_name, (full_name[:3].upper(), "#5C5C5C", full_name))
    badge_file = f"{code.lower()}.png"
    if not (BADGES_DIR / badge_file).is_file():
        badge_file = None
    return {"code": code, "colour": colour, "name": short, "badge_file": badge_file}


# code -> full DB name, for /team/<code> lookups
CODE_TO_NAME = {code: name for name, (code, colour, short) in TEAM_MAP.items()}


def roster_team_view(full_name):
    """Like team_view, but returns None for teams that aren't one of the
    current 20 (historical-only opponents e.g. relegated clubs) -- these
    have no team page and no badge, so callers know to render plain text
    instead of a badge+link."""
    if full_name not in TEAM_MAP:
        return None
    return team_view(full_name)


COMP_BADGES_DIR = Path(__file__).resolve().parent / "static" / "comp_badges"
COMP_NAMES = {"PL": "Premier League", "CL": "Champions League", "ELC": "Championship"}


def comp_view(code):
    badge_file = f"{code.lower()}.png"
    if not (COMP_BADGES_DIR / badge_file).is_file():
        badge_file = None
    return {"code": code, "name": COMP_NAMES.get(code, code), "badge_file": badge_file}

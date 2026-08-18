import os
import sys

import requests

BASE_URL = "https://api.football-data.org/v4"


def _token():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit(
            "FOOTBALL_DATA_TOKEN is not set. Export it or `source` your .env "
            "file first (see README.md)."
        )
    return token


def get(path, params=None):
    headers = {"X-Auth-Token": _token()}
    try:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=15)
    except requests.RequestException as e:
        sys.exit(f"Request to football-data.org failed: {e}")

    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        msg = "Rate limited by football-data.org (HTTP 429, free tier is 10 req/min)."
        if retry_after:
            msg += f" Retry after {retry_after} seconds."
        sys.exit(msg)

    if not resp.ok:
        sys.exit(f"football-data.org returned HTTP {resp.status_code}: {resp.text[:300]}")

    return resp.json()

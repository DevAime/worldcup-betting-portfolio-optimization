"""
Odds fetching for the match-level (h2h / totals) markets via The Odds API.

Design:
- fetch_odds() is wrapped in @st.cache_data(ttl=3600) so Streamlit reruns
  (button clicks, widget changes) do not re-hit the API more than once an
  hour on their own.
- A manual "Refresh odds now" button in app.py calls st.cache_data.clear()
  before rerunning, which is the only way to force an early re-fetch.
- Every successful response is also written to a local JSON snapshot with a
  timestamp. If the live call fails or returns a non-200, we transparently
  fall back to that snapshot so the app never crashes just because the API
  key ran out of quota or the network hiccuped.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

import config


def _read_secret_api_key() -> Optional[str]:
    """Read the odds API key from .streamlit/secrets.toml.

    Returns None (rather than raising) if it isn't configured, so the app
    can fall back to cached data gracefully instead of crashing on import.
    """
    try:
        return st.secrets["ODDS_API_KEY"]
    except Exception:
        return None


def _write_snapshot(payload: List[Dict[str, Any]]) -> None:
    """Persist the raw API response to disk with a timestamp wrapper."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    with open(config.ODDS_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)


def _read_snapshot() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load the last-known-good local snapshot, if any.

    Returns (data, fetched_at_utc). data is an empty list if no snapshot
    exists yet.
    """
    if not config.ODDS_SNAPSHOT_PATH.exists():
        return [], None
    try:
        with open(config.ODDS_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        return snapshot.get("data", []), snapshot.get("fetched_at_utc")
    except (json.JSONDecodeError, OSError):
        return [], None


def _call_odds_api(api_key: str) -> requests.Response:
    """Make the raw HTTP call to The Odds API for the World Cup sport key."""
    url = f"{config.ODDS_API_BASE_URL}/{config.ODDS_API_SPORT_KEY}/odds"
    params = {
        "apiKey": api_key,
        "regions": config.ODDS_API_REGIONS,
        "markets": config.ODDS_API_MARKETS,
        "oddsFormat": config.ODDS_API_ODDS_FORMAT,
        "dateFormat": "iso",
    }
    return requests.get(url, params=params, timeout=15)


@st.cache_data(ttl=config.CACHE_TTL_SECONDS)
def fetch_odds() -> Dict[str, Any]:
    """Fetch current match odds, cached for CACHE_TTL_SECONDS per Streamlit run.

    Returns a dict with:
        - "data": list of event odds dicts as returned by The Odds API
                  (each event's markets already filtered to VALID_H2H_MARKET_KEY
                  plus totals; h2h_lay entries are dropped).
        - "source": "live" or "cache_fallback"
        - "fetched_at_utc": ISO timestamp string of when this data was fetched
        - "error": Optional error message if the live call failed and we fell
                   back to the local snapshot.

    This function does not raise on API failure -- it always returns usable
    data (falling back to the local JSON snapshot, or an empty list if
    neither the live call nor a snapshot is available).
    """
    api_key = _read_secret_api_key()
    error: Optional[str] = None

    if api_key:
        try:
            response = _call_odds_api(api_key)
            if response.status_code == 200:
                raw_events = response.json()
                cleaned_events = _filter_valid_markets(raw_events)
                _write_snapshot(cleaned_events)
                return {
                    "data": cleaned_events,
                    "source": "live",
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                }
            else:
                error = f"Odds API returned status {response.status_code}: {response.text[:200]}"
        except requests.RequestException as exc:
            error = f"Odds API request failed: {exc}"
    else:
        error = "ODDS_API_KEY not found in .streamlit/secrets.toml"

    # Fall back to the last local snapshot.
    cached_data, cached_ts = _read_snapshot()
    return {
        "data": cached_data,
        "source": "cache_fallback",
        "fetched_at_utc": cached_ts,
        "error": error,
    }


def _filter_valid_markets(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop 'h2h_lay' market entries; keep only genuine back-price markets.

    'h2h_lay' represents the exchange lay/back-against side, not a price you
    can back an outcome at, so it must never be fed into devig() as if it
    were a normal back price.
    """
    cleaned: List[Dict[str, Any]] = []
    for event in raw_events:
        event_copy = dict(event)
        bookmakers = []
        for bookmaker in event.get("bookmakers", []):
            bookmaker_copy = dict(bookmaker)
            markets = [
                m for m in bookmaker.get("markets", [])
                if m.get("key") != "h2h_lay"
            ]
            bookmaker_copy["markets"] = markets
            bookmakers.append(bookmaker_copy)
        event_copy["bookmakers"] = bookmakers
        cleaned.append(event_copy)
    return cleaned


def force_refresh() -> None:
    """Clear the cached odds so the next fetch_odds() call hits the API again.

    Intended to be called only from the explicit 'Refresh odds now' button in
    the UI -- never automatically -- so extra API quota is only spent when
    the user asks for it.
    """
    fetch_odds.clear()

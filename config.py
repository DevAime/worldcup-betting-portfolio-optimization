"""
Central configuration for the World Cup Portfolio Kelly decision-support app.

Nothing in this file places bets or moves money. It only stores default
values, API settings, and lookup tables used by the rest of the app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

# ---------------------------------------------------------------------------
# The Odds API settings
# ---------------------------------------------------------------------------
ODDS_API_BASE_URL: str = "https://api.the-odds-api.com/v4/sports"
ODDS_API_SPORT_KEY: str = "soccer_fifa_world_cup"
ODDS_API_MARKETS: str = "h2h,totals"
ODDS_API_REGIONS: str = "eu,uk"
ODDS_API_ODDS_FORMAT: str = "decimal"

# Only this market key is a genuine back price. "h2h_lay" (exchange lay side)
# must never be treated as an outcome you can back at that price.
VALID_H2H_MARKET_KEY: str = "h2h"

# Cache the API response for one hour before allowing another automatic hit.
CACHE_TTL_SECONDS: int = 3600

# Local fallback snapshot (gitignored) used if the live API call fails.
CACHE_DIR: Path = Path("data/cache")
ODDS_SNAPSHOT_PATH: Path = CACHE_DIR / "odds_snapshot.json"

# ---------------------------------------------------------------------------
# Remaining fixtures (semifinal stage onward)
# ---------------------------------------------------------------------------
# "final" is included as a placeholder fixture. Its two participants are not
# known until the semifinals are decided, so the odds fetcher will try to
# match it by team names once available and otherwise leave it blank.
REMAINING_FIXTURES: List[Dict[str, str]] = [
    {"id": "sf1", "home": "France", "away": "Spain", "label": "France vs Spain (Semifinal)"},
    {"id": "sf2", "home": "England", "away": "Argentina", "label": "England vs Argentina (Semifinal)"},
    {"id": "final", "home": "TBD", "away": "TBD", "label": "Final"},
]

# ---------------------------------------------------------------------------
# Manual / futures markets (no reliable free odds API for these) sourced by
# the user from Polymarket and entered via the Tournament Futures tab. These
# are just starting defaults -- fully editable in the UI.
# ---------------------------------------------------------------------------
DEFAULT_NATION_TO_WIN_ODDS: Dict[str, float] = {
    "England": 4.22,
    "Argentina": 4.80,
    "Spain": 1.68,
}

DEFAULT_TOP_SCORER_ODDS: Dict[str, float] = {
    "Kane": 10.72,
    "Bellingham": 18.68,
    "Messi": 1.95,
    "Mbappe": 2.62
}

# Maps a top-scorer candidate to their nation. Used only to build the
# correlation clusters below (a player's Golden Boot chances are tied, in a
# loose way, to how far their team advances).
PLAYER_TEAM_MAP: Dict[str, str] = {
    "Mbappe": "France",
    "Kane": "England",
    "Bellingham": "England",
    "Messi": "Argentina",
}

# ---------------------------------------------------------------------------
# Correlation model knobs (see models.py for the actual heuristic).
# These are simplifications, not fitted parameters -- documented as such.
# ---------------------------------------------------------------------------
# Max correlation allowed between two bets that share the same team (e.g.
# "France to beat Spain" and "France to win the tournament").
MAX_TEAM_SHARED_CORRELATION: float = 0.75

# Correlation applied between a top-scorer bet and bets tied to that
# player's nation. Weaker link than team-vs-team, so scaled down.
PLAYER_NATION_CORRELATION_SCALE: float = 0.4

# ---------------------------------------------------------------------------
# Kelly sizing defaults
# ---------------------------------------------------------------------------
DEFAULT_FRACTIONAL_KELLY: float = 0.5
MIN_FRACTIONAL_KELLY: float = 0.1
MAX_FRACTIONAL_KELLY: float = 1.0

# Simple portfolio-level risk cap: if the raw (unfractioned) Kelly stakes sum
# to more than this fraction of bankroll, scale all stakes down proportionally
# before applying the fractional multiplier. This is a guardrail against the
# covariance heuristic understating risk, not a rigorous constraint.
MAX_TOTAL_RAW_KELLY_EXPOSURE: float = 1.0

DEFAULT_BANKROLL: float = 1000.0

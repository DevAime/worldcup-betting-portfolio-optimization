"""
Core quantitative logic for the portfolio-Kelly decision-support tool:

1. devig()              -- remove bookmaker margin from a set of decimal odds
2. Bet / build_bets()   -- normalize match + futures odds into a flat bet list
3. build_covariance()   -- heuristic correlation-aware covariance matrix
4. kelly_optimize()     -- multivariate fractional-Kelly stake sizing

None of this code places bets, moves money, or talks to a broker/exchange.
It only produces recommended stake fractions for the user to act on
manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

import config


# ---------------------------------------------------------------------------
# 1. De-vigging
# ---------------------------------------------------------------------------
def devig(odds_list: Sequence[float]) -> List[float]:
    """Remove bookmaker overround from a fully-covered set of decimal odds.

    Args:
        odds_list: Decimal odds for every outcome of one market from one
            bookmaker (e.g. [home_odds, draw_odds, away_odds] for a 3-way
            match market). The list must cover the whole outcome space for
            the overround math to be meaningful.

    Returns:
        A list of fair (de-vigged) probabilities, same order and length as
        odds_list, summing to 1.0.

    Raises:
        ValueError: if odds_list is empty or contains a non-positive odd.
    """
    if not odds_list:
        raise ValueError("odds_list must not be empty")
    if any(o <= 0 for o in odds_list):
        raise ValueError("all decimal odds must be positive")

    implied = [1.0 / o for o in odds_list]
    overround = sum(implied)
    return [p / overround for p in implied]


def consensus_fair_probabilities(
    per_bookmaker_odds: Sequence[Sequence[float]],
) -> List[float]:
    """Average de-vigged probabilities for one market across several bookmakers.

    Args:
        per_bookmaker_odds: a list where each element is the full set of
            decimal odds (covering all outcomes) quoted by one bookmaker for
            the same market.

    Returns:
        Consensus fair probability per outcome, averaged across bookmakers,
        same order as each bookmaker's odds list.

    Raises:
        ValueError: if per_bookmaker_odds is empty, or bookmakers disagree on
            the number of outcomes.
    """
    if not per_bookmaker_odds:
        raise ValueError("per_bookmaker_odds must not be empty")

    n_outcomes = len(per_bookmaker_odds[0])
    fair_by_bookmaker = []
    for odds_list in per_bookmaker_odds:
        if len(odds_list) != n_outcomes:
            raise ValueError("all bookmakers must quote the same number of outcomes")
        fair_by_bookmaker.append(devig(odds_list))

    fair_array = np.array(fair_by_bookmaker)  # shape (n_bookmakers, n_outcomes)
    return list(fair_array.mean(axis=0))


# ---------------------------------------------------------------------------
# 2. Bet representation
# ---------------------------------------------------------------------------
@dataclass
class Bet:
    """A single candidate bet in the portfolio.

    Attributes:
        bet_id: unique identifier, e.g. "match_sf1_france"
        label: human-readable description shown in the UI
        category: one of "match", "nation", "scorer"
        teams: underlying team(s) this bet's outcome depends on. Used only
            to build correlation clusters, e.g. ["France"].
        best_odds: best available decimal odds the user could actually bet at
        fair_prob: consensus de-vigged fair probability of this outcome
    """

    bet_id: str
    label: str
    category: str
    teams: List[str]
    best_odds: float
    fair_prob: float

    @property
    def market_implied_prob(self) -> float:
        """Raw implied probability of the best available odds (pre-devig)."""
        return 1.0 / self.best_odds

    @property
    def edge(self) -> float:
        """Fair probability minus the market-implied probability of the price
        actually available to bet at. Positive edge means the bettor believes
        the true probability is higher than what the offered price implies.
        """
        return self.fair_prob - self.market_implied_prob

    @property
    def b(self) -> float:
        """Net odds ('b' in Kelly notation): profit per unit staked on a win."""
        return self.best_odds - 1.0


def build_match_bets(
    fixture_id: str,
    fixture_label: str,
    team_odds: Dict[str, float],
    team_fair_probs: Dict[str, float],
) -> List[Bet]:
    """Build Bet objects for the two (or three, with draw) outcomes of a match.

    Args:
        fixture_id: short id, e.g. "sf1"
        fixture_label: display label, e.g. "France vs Spain (Semifinal)"
        team_odds: mapping of outcome name -> best decimal odds, e.g.
            {"France": 2.1, "Spain": 3.4, "Draw": 3.2}
        team_fair_probs: mapping of outcome name -> consensus fair probability,
            same keys as team_odds.

    Returns:
        List of Bet objects, one per outcome.
    """
    bets = []
    for outcome_name, odds in team_odds.items():
        bets.append(
            Bet(
                bet_id=f"match_{fixture_id}_{outcome_name.lower()}",
                label=f"{outcome_name} to win: {fixture_label}",
                category="match",
                teams=[outcome_name] if outcome_name != "Draw" else [],
                best_odds=odds,
                fair_prob=team_fair_probs[outcome_name],
            )
        )
    return bets


def build_futures_bets(
    nation_odds: Dict[str, float],
    scorer_odds: Dict[str, float],
) -> List[Bet]:
    """Build Bet objects for the manually-entered futures markets.

    Both the "nation to win" and "top scorer" markets are de-vigged as their
    own fully-covered outcome sets before being turned into Bet objects.

    Args:
        nation_odds: {team_name: decimal_odds} for tournament winner.
        scorer_odds: {player_name: decimal_odds} for Golden Boot.

    Returns:
        Combined list of Bet objects for both futures markets.
    """
    bets: List[Bet] = []

    nation_names = list(nation_odds.keys())
    nation_fair = devig([nation_odds[n] for n in nation_names])
    for name, fair_p in zip(nation_names, nation_fair):
        bets.append(
            Bet(
                bet_id=f"nation_{name.lower()}",
                label=f"{name} to win the tournament",
                category="nation",
                teams=[name],
                best_odds=nation_odds[name],
                fair_prob=fair_p,
            )
        )

    scorer_names = list(scorer_odds.keys())
    scorer_fair = devig([scorer_odds[n] for n in scorer_names])
    for name, fair_p in zip(scorer_names, scorer_fair):
        bets.append(
            Bet(
                bet_id=f"scorer_{name.lower()}",
                label=f"{name} to win the Golden Boot",
                category="scorer",
                teams=[config.PLAYER_TEAM_MAP.get(name, "")],
                best_odds=scorer_odds[name],
                fair_prob=fair_p,
            )
        )

    return bets


# ---------------------------------------------------------------------------
# 3. Correlation-aware covariance matrix
# ---------------------------------------------------------------------------
def _bet_variance(bet: Bet) -> float:
    """Variance of a single Bernoulli bet's per-unit-stake return.

    Return R = b with probability p (win), R = -1 with probability (1-p).
    Var(R) = p*(1-p)*(b+1)^2.
    """
    p = bet.fair_prob
    return p * (1 - p) * (bet.b + 1) ** 2


def build_covariance(bets: List[Bet]) -> np.ndarray:
    """Build a heuristic correlation-aware covariance matrix for a bet list.

    SIMPLIFICATION (documented, not a rigorous joint model): bets are grouped
    into clusters that share an underlying team. Any two bets whose `teams`
    lists overlap get an off-diagonal covariance proportional to the
    geometric mean of their individual win probabilities, scaled by a fixed
    correlation cap (config.MAX_TEAM_SHARED_CORRELATION). This captures the
    directionally-correct idea that, e.g., "France to beat Spain" and "France
    to win the tournament" move together, without attempting to model the
    exact conditional probability tree of the knockout bracket.

    Golden-boot bets are linked to their player's nation with a further-
    scaled-down correlation (config.PLAYER_NATION_CORRELATION_SCALE) since
    that link is even looser (a player can miss the Boot even if their team
    wins, and vice versa).

    Args:
        bets: list of Bet objects in the portfolio, in the order stakes will
            be optimized.

    Returns:
        An (n, n) numpy covariance matrix, symmetric, positive semi-definite
        in practice for the correlation values used here.
    """
    n = len(bets)
    cov = np.zeros((n, n))
    variances = [_bet_variance(b) for b in bets]

    for i in range(n):
        cov[i, i] = variances[i]

    for i in range(n):
        for j in range(i + 1, n):
            shared_teams = set(bets[i].teams) & set(bets[j].teams)
            shared_teams.discard("")
            if not shared_teams:
                continue

            # Base correlation heuristic: proportional to the geometric mean
            # of the two bets' win probabilities, capped at a fixed maximum.
            base_corr = config.MAX_TEAM_SHARED_CORRELATION * np.sqrt(
                bets[i].fair_prob * bets[j].fair_prob
            )
            base_corr = min(base_corr, config.MAX_TEAM_SHARED_CORRELATION)

            # If either leg is a Golden Boot bet, scale the link down further
            # since the team-to-player relationship is looser than a direct
            # team-to-team relationship.
            if bets[i].category == "scorer" or bets[j].category == "scorer":
                base_corr *= config.PLAYER_NATION_CORRELATION_SCALE

            cov_ij = base_corr * np.sqrt(variances[i] * variances[j])
            cov[i, j] = cov_ij
            cov[j, i] = cov_ij

    return cov


# ---------------------------------------------------------------------------
# 4. Portfolio Kelly optimizer
# ---------------------------------------------------------------------------
def kelly_optimize(
    bets: List[Bet],
    fractional_kelly: float = config.DEFAULT_FRACTIONAL_KELLY,
    ridge: float = 1e-6,
) -> pd.DataFrame:
    """Compute fractional-Kelly stake recommendations for a basket of bets.

    Uses the standard multivariate Kelly / mean-variance approximation:
    unconstrained optimal fractions f = Sigma^-1 @ mu, where mu_i is the
    expected return per unit stake of bet i (mu_i = p_i*b_i - (1-p_i)) and
    Sigma is the covariance matrix from build_covariance(). This is the
    same approximation that reduces to the familiar single-bet Kelly formula
    f* = (bp - q) / b when there is only one uncorrelated bet.

    A simple portfolio-level risk cap is then applied: if the raw (pre-
    fractional) positive stakes sum to more than
    config.MAX_TOTAL_RAW_KELLY_EXPOSURE, all stakes are scaled down
    proportionally before the fractional multiplier is applied. This guards
    against the covariance heuristic understating true risk; it is a
    guardrail, not a rigorous constraint.

    Args:
        bets: candidate bets.
        fractional_kelly: multiplier in [0.1, 1.0] applied to the raw Kelly
            fractions to reduce variance (user-controlled slider).
        ridge: small value added to the covariance diagonal for numerical
            stability when inverting.

    Returns:
        DataFrame with one row per bet, columns:
        bet_id, label, category, best_odds, fair_prob, market_implied_prob,
        edge, raw_kelly_fraction, recommended_stake_fraction, no_bet (bool)
    """
    if not bets:
        return pd.DataFrame(
            columns=[
                "bet_id", "label", "category", "best_odds", "fair_prob",
                "market_implied_prob", "edge", "raw_kelly_fraction",
                "recommended_stake_fraction", "no_bet",
            ]
        )

    n = len(bets)
    mu = np.array([b.fair_prob * b.b - (1 - b.fair_prob) for b in bets])
    sigma = build_covariance(bets) + np.eye(n) * ridge

    raw_fractions = np.linalg.solve(sigma, mu)
    # Bets with non-positive edge should never receive a positive stake,
    # regardless of what the covariance-adjusted solve suggests (correlation
    # adjustments can occasionally push a marginal bet's raw fraction above
    # zero even when its own edge is negative; we don't want to "bet" on
    # something with no isolated edge just because it correlates with a
    # good bet).
    edges = np.array([b.edge for b in bets])
    raw_fractions = np.where(edges > 0, raw_fractions, 0.0)
    raw_fractions = np.clip(raw_fractions, a_min=0.0, a_max=None)

    total_raw = raw_fractions.sum()
    if total_raw > config.MAX_TOTAL_RAW_KELLY_EXPOSURE:
        raw_fractions = raw_fractions * (config.MAX_TOTAL_RAW_KELLY_EXPOSURE / total_raw)

    recommended_fractions = raw_fractions * fractional_kelly

    rows = []
    for i, bet in enumerate(bets):
        rows.append(
            {
                "bet_id": bet.bet_id,
                "label": bet.label,
                "category": bet.category,
                "best_odds": bet.best_odds,
                "fair_prob": bet.fair_prob,
                "market_implied_prob": bet.market_implied_prob,
                "edge": bet.edge,
                "raw_kelly_fraction": raw_fractions[i],
                "recommended_stake_fraction": recommended_fractions[i],
                "no_bet": bet.edge <= 0,
            }
        )

    return pd.DataFrame(rows)


def add_stake_amounts(portfolio_df: pd.DataFrame, bankroll: float) -> pd.DataFrame:
    """Add currency-denominated stake columns given a bankroll.

    Args:
        portfolio_df: output of kelly_optimize().
        bankroll: total bankroll in whatever currency the user specifies.

    Returns:
        A copy of portfolio_df with a 'recommended_stake_amount' column
        (recommended_stake_fraction * bankroll) and percentage-formatted
        columns for display.
    """
    df = portfolio_df.copy()
    df["recommended_stake_amount"] = df["recommended_stake_fraction"] * bankroll
    df["recommended_stake_pct"] = df["recommended_stake_fraction"] * 100.0
    df["edge_pct"] = df["edge"] * 100.0
    return df

"""
World Cup 2026 Semifinal-Stage Portfolio Kelly -- Streamlit app.

IMPORTANT: This is a decision-support tool only. It never places bets or
holds money. It ingests odds, estimates fair probabilities, and outputs
stake-size *recommendations* for the user to act on manually, if they
choose to, at their own discretion and risk.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

import config
import models
import odds_fetcher
import ui_theme

st.set_page_config(page_title="World Cup Portfolio Kelly", layout="wide", page_icon="🏆")
st.markdown(ui_theme.inject_css(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers: turning raw Odds API events into fixture-level odds tables
# ---------------------------------------------------------------------------
def _match_event_to_fixture(events: List[Dict[str, Any]], fixture: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Find the raw API event that corresponds to a configured fixture.

    Matches loosely on team name substrings since sportsbook feeds don't
    always use identical naming conventions to our config.
    """
    home = fixture["home"].lower()
    away = fixture["away"].lower()
    if home == "tbd" or away == "tbd":
        return None
    for event in events:
        event_home = str(event.get("home_team", "")).lower()
        event_away = str(event.get("away_team", "")).lower()
        if (home in event_home or event_home in home) and (away in event_away or event_away in away):
            return event
        if (home in event_away or event_away in home) and (away in event_home or event_home in away):
            return event
    return None


def _extract_h2h_odds_table(event: Dict[str, Any]) -> pd.DataFrame:
    """Build a per-bookmaker h2h odds table for one event.

    Returns a DataFrame indexed by bookmaker title, columns = outcome names
    (team names / 'Draw'), values = decimal odds. Only the genuine h2h
    market is used (h2h_lay has already been filtered out upstream in
    odds_fetcher).
    """
    rows: Dict[str, Dict[str, float]] = {}
    for bookmaker in event.get("bookmakers", []):
        title = bookmaker.get("title", bookmaker.get("key", "unknown"))
        for market in bookmaker.get("markets", []):
            if market.get("key") != config.VALID_H2H_MARKET_KEY:
                continue
            outcome_prices = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            rows[title] = outcome_prices
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame.from_dict(rows, orient="index")


def _extract_totals_odds_table(event: Dict[str, Any]) -> pd.DataFrame:
    """Build a per-bookmaker totals (over/under) odds table for one event."""
    rows: List[Dict[str, Any]] = []
    for bookmaker in event.get("bookmakers", []):
        title = bookmaker.get("title", bookmaker.get("key", "unknown"))
        for market in bookmaker.get("markets", []):
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []):
                rows.append(
                    {
                        "bookmaker": title,
                        "outcome": outcome.get("name"),
                        "point": outcome.get("point"),
                        "price": outcome.get("price"),
                    }
                )
    return pd.DataFrame(rows)


def _consensus_fair_probs_for_event(h2h_table: pd.DataFrame) -> Dict[str, float]:
    """Devig each bookmaker row and average, returning {outcome: fair_prob}."""
    if h2h_table.empty:
        return {}
    outcome_names = list(h2h_table.columns)
    per_bookmaker_odds = h2h_table.dropna().values.tolist()
    if not per_bookmaker_odds:
        return {}
    fair = models.consensus_fair_probabilities(per_bookmaker_odds)
    return dict(zip(outcome_names, fair))


def _best_odds_for_event(h2h_table: pd.DataFrame) -> Dict[str, float]:
    """Best (highest) available decimal odds per outcome across bookmakers."""
    if h2h_table.empty:
        return {}
    return h2h_table.max(axis=0, skipna=True).to_dict()


# ---------------------------------------------------------------------------
# Session state init for futures forms (so edits persist across reruns)
# ---------------------------------------------------------------------------
if "nation_odds" not in st.session_state:
    st.session_state.nation_odds = dict(config.DEFAULT_NATION_TO_WIN_ODDS)
if "scorer_odds" not in st.session_state:
    st.session_state.scorer_odds = dict(config.DEFAULT_TOP_SCORER_ODDS)


st.title("🏆 World Cup 2026 -- Semifinal Stage Portfolio Kelly")
st.caption(
    "Decision-support only. This tool does not place bets or hold money. "
    "It estimates fair probabilities from odds and recommends stake sizes "
    "for you to act on manually, entirely at your own discretion and risk."
)

tab1, tab2, tab3 = st.tabs(["Match Odds", "Tournament Futures", "Portfolio"])

# Fetch once per script run; cached internally per config.CACHE_TTL_SECONDS.
odds_result = odds_fetcher.fetch_odds()
raw_events = odds_result["data"]

# ---------------------------------------------------------------------------
# TAB 1: Match Odds
# ---------------------------------------------------------------------------
with tab1:
    col_a, col_b = st.columns([3, 1])
    with col_a:
        if odds_result["source"] == "live":
            st.success(f"Live odds fetched at {odds_result['fetched_at_utc']} UTC")
        else:
            msg = f"Using cached snapshot from {odds_result['fetched_at_utc'] or 'unknown time'} UTC."
            if odds_result.get("error"):
                msg += f" (Live fetch issue: {odds_result['error']})"
            st.warning(msg)
    with col_b:
        if st.button("🔄 Refresh odds now"):
            odds_fetcher.force_refresh()
            st.rerun()

    st.divider()

    match_fair_probs: Dict[str, Dict[str, float]] = {}
    match_best_odds: Dict[str, Dict[str, float]] = {}

    for fixture in config.REMAINING_FIXTURES:
        event = _match_event_to_fixture(raw_events, fixture)
        if event is None:
            st.markdown(f"##### {fixture['label']}")
            st.info("No live match odds found for this fixture yet (may not be posted, or awaits prior results).")
            st.divider()
            continue

        h2h_table = _extract_h2h_odds_table(event)
        totals_table = _extract_totals_odds_table(event)

        if h2h_table.empty:
            st.markdown(f"##### {fixture['label']}")
            st.info("No h2h odds currently available for this fixture.")
        else:
            fair_probs = _consensus_fair_probs_for_event(h2h_table)
            best_odds = _best_odds_for_event(h2h_table)
            match_fair_probs[fixture["id"]] = fair_probs
            match_best_odds[fixture["id"]] = best_odds

            outcome_names = [n for n in fair_probs.keys() if n != "Draw"]
            team_a, team_b = (outcome_names + [None, None])[:2]
            has_draw = "Draw" in fair_probs

            st.markdown(
                ui_theme.scoreboard_tile(
                    fixture_label=fixture["label"],
                    team_a=team_a or "Team A",
                    team_a_odds=best_odds.get(team_a) if team_a else None,
                    team_a_prob=fair_probs.get(team_a) if team_a else None,
                    team_b=team_b or "Team B",
                    team_b_odds=best_odds.get(team_b) if team_b else None,
                    team_b_prob=fair_probs.get(team_b) if team_b else None,
                    draw_odds=best_odds.get("Draw") if has_draw else None,
                    draw_prob=fair_probs.get("Draw") if has_draw else None,
                ),
                unsafe_allow_html=True,
            )

            with st.expander("Full bookmaker-by-bookmaker odds"):
                st.markdown("**Moneyline (h2h) odds by bookmaker**")
                st.dataframe(h2h_table, use_container_width=True)

        if not totals_table.empty:
            with st.expander("Totals (over/under) odds by bookmaker"):
                st.dataframe(totals_table, use_container_width=True, hide_index=True)

        st.divider()

    # Stash for use in Tab 3 without re-fetching / re-parsing.
    st.session_state["_match_fair_probs"] = match_fair_probs
    st.session_state["_match_best_odds"] = match_best_odds


# ---------------------------------------------------------------------------
# TAB 2: Tournament Futures
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Nation to win the tournament")
    st.caption("Enter decimal odds sourced from Polymarket (or convert a stated probability to decimal odds yourself: decimal odds = 1 / probability).")

    with st.form("nation_odds_form"):
        nation_inputs = {}
        cols = st.columns(2)
        for i, (team, default_odds) in enumerate(st.session_state.nation_odds.items()):
            with cols[i % 2]:
                nation_inputs[team] = st.number_input(
                    f"{team} -- decimal odds",
                    min_value=1.01,
                    value=float(default_odds),
                    step=0.01,
                    key=f"nation_input_{team}",
                )
        nation_submitted = st.form_submit_button("Update nation odds")
        if nation_submitted:
            st.session_state.nation_odds = nation_inputs
            st.success("Nation-to-win odds updated.")

    nation_fair = models.devig(list(st.session_state.nation_odds.values()))
    nation_fair_df = pd.DataFrame(
        {
            "Team": list(st.session_state.nation_odds.keys()),
            "Decimal odds": list(st.session_state.nation_odds.values()),
            "Fair probability (de-vigged)": [f"{p:.1%}" for p in nation_fair],
        }
    )
    st.dataframe(nation_fair_df, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Top Scorer (Golden Boot)")
    with st.form("scorer_odds_form"):
        scorer_inputs = {}
        cols = st.columns(2)
        for i, (player, default_odds) in enumerate(st.session_state.scorer_odds.items()):
            with cols[i % 2]:
                scorer_inputs[player] = st.number_input(
                    f"{player} -- decimal odds",
                    min_value=1.01,
                    value=float(default_odds),
                    step=0.01,
                    key=f"scorer_input_{player}",
                )
        scorer_submitted = st.form_submit_button("Update top scorer odds")
        if scorer_submitted:
            st.session_state.scorer_odds = scorer_inputs
            st.success("Top scorer odds updated.")

    scorer_fair = models.devig(list(st.session_state.scorer_odds.values()))
    scorer_fair_df = pd.DataFrame(
        {
            "Player": list(st.session_state.scorer_odds.keys()),
            "Decimal odds": list(st.session_state.scorer_odds.values()),
            "Fair probability (de-vigged)": [f"{p:.1%}" for p in scorer_fair],
        }
    )
    st.dataframe(scorer_fair_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# TAB 3: Portfolio
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Portfolio settings")
    col1, col2 = st.columns(2)
    with col1:
        bankroll = st.number_input(
            "Bankroll",
            min_value=0.0,
            value=config.DEFAULT_BANKROLL,
            step=50.0,
        )
    with col2:
        fractional_kelly = st.slider(
            "Fractional Kelly multiplier",
            min_value=config.MIN_FRACTIONAL_KELLY,
            max_value=config.MAX_FRACTIONAL_KELLY,
            value=config.DEFAULT_FRACTIONAL_KELLY,
            step=0.05,
            help="Scales down the raw Kelly-optimal stakes to reduce variance. "
                 "0.5 = 'half Kelly', a common risk-reduction convention.",
        )

    st.divider()

    # --- Assemble the full bet list from Tab 1 + Tab 2 state ---
    bets: List[models.Bet] = []

    match_fair_probs = st.session_state.get("_match_fair_probs", {})
    match_best_odds = st.session_state.get("_match_best_odds", {})
    for fixture in config.REMAINING_FIXTURES:
        fid = fixture["id"]
        if fid in match_fair_probs and match_fair_probs[fid]:
            bets.extend(
                models.build_match_bets(
                    fixture_id=fid,
                    fixture_label=fixture["label"],
                    team_odds=match_best_odds[fid],
                    team_fair_probs=match_fair_probs[fid],
                )
            )

    bets.extend(
        models.build_futures_bets(
            nation_odds=st.session_state.nation_odds,
            scorer_odds=st.session_state.scorer_odds,
        )
    )

    if not bets:
        st.info("No bets available yet -- check Tab 1 for live match odds or Tab 2 for futures.")
    else:
        portfolio_df = models.kelly_optimize(bets, fractional_kelly=fractional_kelly)
        portfolio_df = models.add_stake_amounts(portfolio_df, bankroll=bankroll)
        portfolio_df = portfolio_df.sort_values("recommended_stake_fraction", ascending=False)

        st.markdown("##### Combined portfolio &mdash; every candidate bet with edge and recommended stake")
        st.markdown(ui_theme.portfolio_table_html(portfolio_df), unsafe_allow_html=True)

        st.divider()

        st.markdown("##### Stake allocation across the portfolio")
        chart_df = portfolio_df[~portfolio_df["no_bet"]]
        if chart_df.empty:
            st.info("No positive-edge bets to chart -- every candidate is currently a 'no bet'.")
        else:
            chart_df = chart_df.sort_values("recommended_stake_pct")
            fig = px.bar(
                chart_df,
                x="recommended_stake_pct",
                y="label",
                orientation="h",
                labels={"recommended_stake_pct": "Recommended stake (% of bankroll)", "label": "Bet"},
                text="recommended_stake_pct",
            )
            fig.update_traces(
                texttemplate="%{text:.2f}%",
                textposition="outside",
                textfont_color=ui_theme.TEXT_PRIMARY,
                marker_color=ui_theme.ACCENT_GOLD,
                marker_line_color=ui_theme.ACCENT_GOLD_DIM,
                marker_line_width=1,
            )
            fig.update_layout(
                height=max(300, 40 * len(chart_df)),
                template=ui_theme.PLOTLY_TEMPLATE,
                margin=dict(l=10, r=60, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("Methodology notes / simplifications"):
            st.markdown(
                """
- **De-vig**: implied probability = 1 / odds per outcome, normalized so a
  full market's probabilities sum to 1, then averaged across bookmakers.
- **Correlation adjustment**: bets that share an underlying team (e.g. a
  match outcome and that team's tournament-winner bet) are treated as
  positively correlated, with correlation proportional to the geometric
  mean of their win probabilities, capped at a fixed maximum. This is a
  documented heuristic, not a rigorous joint model of the knockout bracket.
- **Portfolio Kelly**: stakes are the mean-variance approximation to the
  multivariate Kelly criterion, f = Σ⁻¹μ, then scaled by the fractional
  Kelly slider and capped so raw (pre-fraction) stakes don't exceed 100%
  of bankroll in aggregate.
- Bets with non-positive edge are always forced to a zero recommended
  stake, regardless of what the correlation adjustment alone would imply.
                """
            )

st.divider()
st.caption(
    "This app is a decision-support tool, not a betting platform. It does not "
    "place wagers, transmit funds, or interact with any bookmaker or exchange "
    "account. All stake recommendations are estimates based on a simplified "
    "model and should be treated as informational only."
)

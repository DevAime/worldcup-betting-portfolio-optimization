"""
Visual theme for the World Cup Portfolio Kelly app: a dark "floodlit night
match" look.

Design tokens (see README for the rationale):
- Background reads like a pitch under floodlights at night, not a generic
  black. Odds and probabilities render in a monospace "scoreboard" face so
  the numbers -- the actual content of this tool -- carry the personality
  of the page, not the chrome around them.
- Gold is the signature accent (floodlight / scoreboard amber). Green and
  red are reserved *only* for signaling positive/negative edge, never used
  decoratively, so they stay meaningful.

This module only builds presentation (CSS + small HTML snippets consumed
with st.markdown(..., unsafe_allow_html=True)). It has no bearing on the
math in models.py.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def _flatten(html: str) -> str:
    """Strip leading whitespace from every line of an HTML snippet.

    Streamlit's st.markdown runs content through a standard Markdown parser
    before rendering. Markdown treats any line indented by 4+ spaces as a
    preformatted code block, so the nicely-indented multi-line f-strings
    used to build these components would otherwise render as literal text
    instead of HTML. Stripping per-line indentation avoids that entirely
    (harmless for HTML, since whitespace between tags isn't significant
    outside <pre>/<textarea>, neither of which is used here).
    """
    return "\n".join(line.strip() for line in html.strip().splitlines())

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG_BASE = "#0A1512"
BG_SURFACE = "#10201B"
BG_SURFACE_ALT = "#16281F"
BORDER = "#25392F"
TEXT_PRIMARY = "#EAF2ED"
TEXT_MUTED = "#8CA398"
ACCENT_GOLD = "#F5B700"
ACCENT_GOLD_DIM = "#7A5C05"
ACCENT_GREEN = "#33D17A"
ACCENT_RED = "#EF5B5B"
ACCENT_BLUE = "#4FC3F7"


def inject_css() -> str:
    """Return the global <style> block. Call once via st.markdown(..., unsafe_allow_html=True)."""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

.stApp {{
    background: radial-gradient(circle at 15% 0%, #10231C 0%, {BG_BASE} 55%) fixed;
}}

/* Headings use the condensed display face, wide tracking, uppercase --
   the "stadium signage" register. */
h1, h2, h3 {{
    font-family: 'Oswald', sans-serif !important;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: {TEXT_PRIMARY} !important;
}}

h1 {{
    border-bottom: 2px solid {ACCENT_GOLD_DIM};
    padding-bottom: 0.4rem;
}}

p, span, label, .stMarkdown, .stCaption {{
    color: {TEXT_PRIMARY};
}}

/* Caption / helper text stays muted */
.stCaption, [data-testid="stCaptionContainer"] {{
    color: {TEXT_MUTED} !important;
}}

/* Tabs styled like scoreboard channel selectors */
.stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
    border-bottom: 1px solid {BORDER};
}}
.stTabs [data-baseweb="tab"] {{
    background-color: {BG_SURFACE};
    border-radius: 6px 6px 0 0;
    color: {TEXT_MUTED};
    font-family: 'Oswald', sans-serif;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 8px 20px;
}}
.stTabs [aria-selected="true"] {{
    background-color: {BG_SURFACE_ALT} !important;
    color: {ACCENT_GOLD} !important;
    border-top: 2px solid {ACCENT_GOLD};
}}

/* Buttons: gold outline, fills gold on hover */
.stButton > button {{
    background-color: transparent;
    color: {ACCENT_GOLD};
    border: 1px solid {ACCENT_GOLD_DIM};
    border-radius: 6px;
    font-family: 'Oswald', sans-serif;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-size: 0.85rem;
    padding: 0.5rem 1.1rem;
    transition: all 0.15s ease;
}}
.stButton > button:hover {{
    background-color: {ACCENT_GOLD};
    color: {BG_BASE};
    border-color: {ACCENT_GOLD};
}}

/* Form submit buttons */
.stFormSubmitButton > button {{
    background-color: {ACCENT_GOLD_DIM};
    color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT_GOLD};
    border-radius: 6px;
    font-family: 'Oswald', sans-serif;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}}
.stFormSubmitButton > button:hover {{
    background-color: {ACCENT_GOLD};
    color: {BG_BASE};
}}

/* Cards: forms, expanders, dataframes all sit on a slightly raised surface */
div[data-testid="stForm"], .streamlit-expanderHeader, div[data-testid="stExpander"] {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

div[data-testid="stMetric"] {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-left: 3px solid {ACCENT_GOLD};
    border-radius: 8px;
    padding: 0.8rem 1rem;
}}
div[data-testid="stMetricValue"] {{
    font-family: 'JetBrains Mono', monospace;
    color: {ACCENT_GOLD};
}}

/* Number/text inputs and sliders */
.stNumberInput input, .stTextInput input {{
    font-family: 'JetBrains Mono', monospace;
    background-color: {BG_SURFACE_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
}}
.stSlider [data-baseweb="slider"] div {{
    background-color: {ACCENT_GOLD} !important;
}}

/* Native dataframes: dark surface, gold header, monospace cells */
[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    overflow: hidden;
}}
[data-testid="stDataFrame"] * {{
    font-family: 'JetBrains Mono', monospace !important;
}}

hr {{
    border-color: {BORDER} !important;
}}

/* Alert boxes recolored to fit the palette instead of default blue/orange */
div[data-testid="stAlertContentInfo"] {{
    color: {TEXT_PRIMARY};
}}
div[data-baseweb="notification"] {{
    background-color: {BG_SURFACE} !important;
    border: 1px solid {BORDER} !important;
}}
</style>
"""


def scoreboard_tile(
    fixture_label: str,
    team_a: str,
    team_a_odds: Optional[float],
    team_a_prob: Optional[float],
    team_b: str,
    team_b_odds: Optional[float],
    team_b_prob: Optional[float],
    draw_odds: Optional[float] = None,
    draw_prob: Optional[float] = None,
) -> str:
    """Build an HTML 'stadium scoreboard' tile summarizing one fixture.

    This is the page's signature element: fair probability and best odds
    for each side, set in a monospace scoreboard face against a dark tile,
    with a gold center divider (kickoff marker).
    """

    def _cell(name: str, odds: Optional[float], prob: Optional[float]) -> str:
        odds_txt = f"{odds:.2f}" if odds else "&mdash;"
        prob_txt = f"{prob*100:.1f}%" if prob is not None else "&mdash;"
        return f"""
        <div style="flex:1; text-align:center; padding: 0.6rem 0.4rem;">
            <div style="font-family:'Oswald',sans-serif; letter-spacing:0.06em; text-transform:uppercase;
                        font-size:0.8rem; color:{TEXT_MUTED}; margin-bottom:0.3rem;">{name}</div>
            <div style="font-family:'JetBrains Mono',monospace; font-size:1.9rem; font-weight:700; color:{ACCENT_GOLD};
                        line-height:1;">{prob_txt}</div>
            <div style="font-family:'JetBrains Mono',monospace; font-size:0.85rem; color:{TEXT_MUTED}; margin-top:0.2rem;">
                odds {odds_txt}</div>
        </div>
        """

    draw_html = ""
    if draw_odds is not None:
        draw_html = f"""
        <div style="flex:0 0 90px; text-align:center; padding: 0.6rem 0.2rem; border-left:1px solid {BORDER}; border-right:1px solid {BORDER};">
            <div style="font-family:'Oswald',sans-serif; letter-spacing:0.06em; text-transform:uppercase;
                        font-size:0.7rem; color:{TEXT_MUTED}; margin-bottom:0.3rem;">Draw</div>
            <div style="font-family:'JetBrains Mono',monospace; font-size:1.3rem; font-weight:700; color:{TEXT_PRIMARY};">
                {f'{draw_prob*100:.1f}%' if draw_prob is not None else '&mdash;'}</div>
            <div style="font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:{TEXT_MUTED};">
                odds {f'{draw_odds:.2f}' if draw_odds else '&mdash;'}</div>
        </div>
        """

    html = f"""
    <div style="background-color:{BG_SURFACE}; border:1px solid {BORDER}; border-radius:12px;
                margin-bottom:1.1rem; overflow:hidden;">
        <div style="background-color:{BG_SURFACE_ALT}; padding:0.5rem 1rem; border-bottom:1px solid {BORDER};
                    font-family:'Oswald',sans-serif; letter-spacing:0.05em; text-transform:uppercase;
                    font-size:0.85rem; color:{TEXT_MUTED};">
            {fixture_label}
        </div>
        <div style="display:flex; align-items:stretch;">
            {_cell(team_a, team_a_odds, team_a_prob)}
            {draw_html}
            {_cell(team_b, team_b_odds, team_b_prob)}
        </div>
    </div>
    """
    return _flatten(html)


def portfolio_table_html(df: pd.DataFrame) -> str:
    """Render the portfolio bet list as a custom dark HTML table.

    Gives per-row accent coloring (gold-green left border for bets worth
    taking, muted red for 'no bet') that native st.dataframe styling can't
    do per-cell, and keeps all numeric columns in the scoreboard mono face.

    Expects columns: label, best_odds, fair_prob, market_implied_prob,
    edge, recommended_stake_pct, recommended_stake_amount, no_bet.
    """
    header = f"""
    <tr style="background-color:{BG_SURFACE_ALT}; text-align:left;">
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Bet</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Best odds</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Fair prob</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Market prob</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Edge</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Stake %</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Stake amount</th>
        <th style="padding:10px 12px; font-family:'Oswald',sans-serif; letter-spacing:0.04em;
                   text-transform:uppercase; font-size:0.78rem; color:{TEXT_MUTED};">Status</th>
    </tr>
    """

    rows_html = []
    for _, row in df.iterrows():
        is_no_bet = bool(row["no_bet"])
        accent = ACCENT_RED if is_no_bet else ACCENT_GREEN
        edge_color = ACCENT_GREEN if row["edge"] > 0 else ACCENT_RED
        status_txt = "NO BET" if is_no_bet else "BET"
        status_bg = "rgba(239,91,91,0.12)" if is_no_bet else "rgba(51,209,122,0.12)"
        row_opacity = "0.55" if is_no_bet else "1"

        rows_html.append(f"""
        <tr style="border-bottom:1px solid {BORDER}; opacity:{row_opacity};">
            <td style="padding:10px 12px; border-left:3px solid {accent}; color:{TEXT_PRIMARY};
                       font-family:'Inter',sans-serif;">{row['label']}</td>
            <td style="padding:10px 12px; font-family:'JetBrains Mono',monospace; color:{TEXT_PRIMARY};">
                {row['best_odds']:.2f}</td>
            <td style="padding:10px 12px; font-family:'JetBrains Mono',monospace; color:{TEXT_PRIMARY};">
                {row['fair_prob']*100:.1f}%</td>
            <td style="padding:10px 12px; font-family:'JetBrains Mono',monospace; color:{TEXT_MUTED};">
                {row['market_implied_prob']*100:.1f}%</td>
            <td style="padding:10px 12px; font-family:'JetBrains Mono',monospace; color:{edge_color}; font-weight:700;">
                {row['edge']*100:+.2f}%</td>
            <td style="padding:10px 12px; font-family:'JetBrains Mono',monospace; color:{ACCENT_GOLD};">
                {row['recommended_stake_pct']:.2f}%</td>
            <td style="padding:10px 12px; font-family:'JetBrains Mono',monospace; color:{TEXT_PRIMARY};">
                {row['recommended_stake_amount']:,.2f}</td>
            <td style="padding:10px 12px;">
                <span style="background-color:{status_bg}; color:{accent}; padding:3px 10px; border-radius:12px;
                             font-family:'Oswald',sans-serif; font-size:0.72rem; letter-spacing:0.06em;">
                    {status_txt}
                </span>
            </td>
        </tr>
        """)

    html = f"""
    <div style="border:1px solid {BORDER}; border-radius:10px; overflow:hidden;">
        <table style="width:100%; border-collapse:collapse; background-color:{BG_SURFACE};">
            <thead>{header}</thead>
            <tbody>{''.join(rows_html)}</tbody>
        </table>
    </div>
    """
    return _flatten(html)


PLOTLY_TEMPLATE = {
    "layout": {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter, sans-serif", "color": TEXT_PRIMARY},
        "xaxis": {"gridcolor": BORDER, "zerolinecolor": BORDER},
        "yaxis": {"gridcolor": BORDER, "zerolinecolor": BORDER},
        "colorway": [ACCENT_GOLD, ACCENT_GREEN, ACCENT_BLUE, ACCENT_RED],
    }
}
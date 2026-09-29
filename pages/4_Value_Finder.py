"""Identify bets with positive expected value."""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.api.nhl_client import NHLClient
from footer import add_betting_oracle_footer

st.title("\U0001F4B0 Value Finder")

st.markdown("""
Find bets where the model's probability exceeds the implied odds.
A **positive edge** suggests potential value.
""")

# Initialize client
@st.cache_resource
def get_client():
    return NHLClient()

client = get_client()

# Date selector for value bets
from datetime import date
from src.models.expected_goals import (
    TeamMetrics,
    calculate_expected_goals,
    calculate_expected_goals_with_analytics,
    calculate_total_xg,
)
from src.models.win_probability import calculate_win_probability


def implied_prob(odds):
    """Convert American odds to implied probability (no vig removal)."""
    if odds is None:
        return None
    try:
        odds = float(odds)
    except (TypeError, ValueError):
        return None
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def kelly_fraction(model_prob, american_odds):
    """Kelly criterion stake fraction for a given model probability and American odds."""
    if model_prob is None or american_odds is None:
        return None
    try:
        odds = float(american_odds)
        p = float(model_prob)
    except (TypeError, ValueError):
        return None

    # Convert American odds to decimal payout multiplier (b = net odds received per 1 staked)
    if odds > 0:
        b = odds / 100
    elif odds < 0:
        b = 100 / abs(odds)
    else:
        return None

    q = 1 - p
    kelly = (p * b - q) / b
    return max(kelly, 0.0)


def normalize_abbrev(name):
    """Best-effort normalization for matching team names/abbreviations."""
    if not name:
        return ""
    return str(name).strip().upper()


selected_date = st.date_input("Select Date", value=date.today())
st.subheader(f"Value Bets for {selected_date:%Y-%m-%d}")

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    min_edge = st.slider("Minimum Edge %", 0, 20, 3)
with col2:
    bet_types = st.multiselect("Bet Types", ["Moneyline", "Puck Line", "Totals"], default=["Moneyline"])
with col3:
    confidence = st.selectbox("Model Confidence", ["All", "High", "Medium", "Low"])


def confidence_tier(prob):
    """Bucket a win probability into a confidence tier based on distance from 50%."""
    if prob is None:
        return "Low"
    distance = abs(prob - 0.5)
    if distance >= 0.15:
        return "High"
    if distance >= 0.07:
        return "Medium"
    return "Low"


# Get games for selected date and display model predictions
st.subheader("Model Predictions")
preds_df = pd.DataFrame()
preds_lookup = {}
try:
    date_str = selected_date.strftime("%Y-%m-%d")
    schedule = client.get_schedule(date_str)
    games_list = []
    for week in schedule.get("gameWeek", []):
        # Only include the block matching the selected date; the NHL
        # schedule endpoint returns a full week's worth of gameWeek
        # entries, not just the requested day.
        if week.get("date") != date_str:
            continue
        for game in week.get("games", []):
            if game.get("gameType") in [2, 3]:
                games_list.append(game)

    if games_list:
        # Try to use NHL team analytics when available.
        analytics_data = {}
        try:
            analytics_data = client.get_team_analytics(season="20252026")
        except Exception:
            analytics_data = {}

        preds = []
        for game in games_list:
            away_abbr = game.get("awayTeam", {}).get("abbrev")
            home_abbr = game.get("homeTeam", {}).get("abbrev")
            # fetch stats and compute predictions
            home_stats = client.get_team_summary(home_abbr)
            away_stats = client.get_team_summary(away_abbr)
            if home_stats and away_stats:
                home_tm = TeamMetrics.from_api_response(home_stats)
                away_tm = TeamMetrics.from_api_response(away_stats)

                home_analytics = analytics_data.get(home_abbr)
                away_analytics = analytics_data.get(away_abbr)
                if home_analytics and away_analytics:
                    home_xg, away_xg = calculate_expected_goals_with_analytics(
                        home_tm,
                        away_tm,
                        home_analytics=home_analytics,
                        away_analytics=away_analytics,
                        analytics_weight=0.5,
                    )
                    model_source = "Analytics blend"
                else:
                    home_xg, away_xg = calculate_expected_goals(home_tm, away_tm)
                    model_source = "Legacy"

                probs = calculate_win_probability(home_xg, away_xg)
                total_pred = calculate_total_xg(home_xg, away_xg)

                preds.append({
                    "Matchup": f"{away_abbr} @ {home_abbr}",
                    "AwayAbbr": away_abbr,
                    "HomeAbbr": home_abbr,
                    "Model": model_source,
                    "Home xG": home_xg,
                    "Away xG": away_xg,
                    "Home Win %": f"{probs.home_win:.1%}",
                    "Away Win %": f"{probs.away_win:.1%}",
                    "HomeWinProb": probs.home_win,
                    "AwayWinProb": probs.away_win,
                    "Total Pred": total_pred,
                })

                preds_lookup[(normalize_abbrev(away_abbr), normalize_abbrev(home_abbr))] = {
                    "home_win_prob": probs.home_win,
                    "away_win_prob": probs.away_win,
                    "total_pred": total_pred,
                    "model_source": model_source,
                }
        if preds:
            preds_df = pd.DataFrame(preds)
            display_cols = ["Matchup", "Model", "Home xG", "Away xG", "Home Win %", "Away Win %", "Total Pred"]
            st.caption("Model uses analytics-blended xG when NHL team analytics are available; otherwise it falls back to the legacy goals-based estimate.")
            st.dataframe(
                preds_df[display_cols],
                width='stretch',
                hide_index=True,
                column_config={
                    "Model": st.column_config.TextColumn("Model", width="small"),
                    "Matchup": st.column_config.TextColumn("Matchup", width="large"),
                    "Home xG": st.column_config.NumberColumn("Home xG", width="small", format="%.2f"),
                    "Away xG": st.column_config.NumberColumn("Away xG", width="small", format="%.2f"),
                    "Home Win %": st.column_config.TextColumn("Home Win %", width="small"),
                    "Away Win %": st.column_config.TextColumn("Away Win %", width="small"),
                    "Total Pred": st.column_config.NumberColumn("Total Pred", width="small", format="%.2f"),
                },
            )
        else:
            st.info("Unable to compute predictions for selected date.")
    else:
        st.info("No NHL games scheduled for that date.")
except Exception as e:
    st.error(f"Error loading model predictions: {e}")

# continue with odds section
st.subheader("Today's Betting Odds")

odds_list = []
try:
    odds_data = client.get_espn_odds(days_ahead=7)

    if odds_data:
        for game in odds_data:
            if game.get("odds"):
                provider = game["odds"][0]

                # Parse odds
                home_ml = provider.get("moneyline", {}).get("home")
                away_ml = provider.get("moneyline", {}).get("away")

                home_impl = implied_prob(home_ml)
                away_impl = implied_prob(away_ml)

                # Get spread info
                home_spread_line = provider.get("spread", {}).get("home", {}).get("line")
                home_spread_odds = provider.get("spread", {}).get("home", {}).get("odds")
                away_spread_odds = provider.get("spread", {}).get("away", {}).get("odds")

                # Get total info
                over_line = provider.get("total", {}).get("over", {}).get("line")
                over_odds = provider.get("total", {}).get("over", {}).get("odds")
                under_odds = provider.get("total", {}).get("under", {}).get("odds")

                odds_list.append({
                    "Game": game.get("name", ""),
                    "Home Team": game.get("home_team", ""),
                    "Away Team": game.get("away_team", ""),
                    "Home ML": home_ml if home_ml else "N/A",
                    "Away ML": away_ml if away_ml else "N/A",
                    "Home Impl%": f"{home_impl:.1%}" if home_impl else "N/A",
                    "Away Impl%": f"{away_impl:.1%}" if away_impl else "N/A",
                    "Spread": f"{home_spread_line}" if home_spread_line else "N/A",
                    "Total": f"{over_line}" if over_line else "N/A",
                    "Provider": provider.get("provider", "DraftKings"),
                    "_home_ml_raw": home_ml,
                    "_away_ml_raw": away_ml,
                    "_home_impl_raw": home_impl,
                    "_away_impl_raw": away_impl,
                    "_home_spread_line": home_spread_line,
                    "_home_spread_odds": home_spread_odds,
                    "_away_spread_odds": away_spread_odds,
                    "_over_line": over_line,
                    "_over_odds": over_odds,
                    "_under_odds": under_odds,
                })

        if odds_list:
            odds_df = pd.DataFrame(odds_list)

            st.dataframe(
                odds_df.drop(columns=[c for c in odds_df.columns if c.startswith("_")]),
                width='stretch',
                hide_index=True,
                column_config={
                    "Game": st.column_config.TextColumn("Matchup", width="large"),
                    "Home Team": st.column_config.TextColumn("Home", width="small"),
                    "Away Team": st.column_config.TextColumn("Away", width="small"),
                    "Home ML": st.column_config.TextColumn("Home ML", width="small"),
                    "Away ML": st.column_config.TextColumn("Away ML", width="small"),
                    "Home Impl%": st.column_config.TextColumn("Home Prob", width="small", help="Implied probability from odds"),
                    "Away Impl%": st.column_config.TextColumn("Away Prob", width="small", help="Implied probability from odds"),
                    "Spread": st.column_config.TextColumn("Spread", width="small"),
                    "Total": st.column_config.TextColumn("Total", width="small"),
                }
            )

            st.divider()
            st.subheader("How It Works")
            st.markdown("""
            **Value betting** occurs when your estimated probability of an outcome is higher than the implied probability from the odds.

            **Example:**
            - Odds: -150 (Implied: 60%)
            - Your Model: 65% win probability
            - **Edge:** +5% (65% - 60%)

            **Kelly Criterion** suggests bet sizing based on edge:
            - Kelly % = (Model Prob \u00d7 (Odds + 1) - 1) / Odds
            """)
        else:
            st.info("No odds data available.")
    else:
        st.info("Unable to fetch odds data.")

except Exception as e:
    st.error(f"Error loading odds: {e}")
    odds_list = []

# Real value bets section: join model predictions to market odds
st.divider()
st.subheader("Identified Value Bets")

value_rows = []

if odds_list and preds_lookup:
    for row in odds_list:
        home_abbr_key = normalize_abbrev(row.get("Home Team"))
        away_abbr_key = normalize_abbrev(row.get("Away Team"))
        pred = preds_lookup.get((away_abbr_key, home_abbr_key))

        # Fall back to fuzzy matching on the "Game" string if abbreviations don't line up
        if pred is None:
            for (a_key, h_key), p in preds_lookup.items():
                game_name = normalize_abbrev(row.get("Game"))
                if a_key and h_key and a_key in game_name and h_key in game_name:
                    pred = p
                    away_abbr_key, home_abbr_key = a_key, h_key
                    break

        if pred is None:
            continue

        matchup_label = f"{away_abbr_key} @ {home_abbr_key}"

        # Moneyline value: home side
        if "Moneyline" in bet_types:
            home_prob = pred["home_win_prob"]
            home_impl = row.get("_home_impl_raw")
            if home_prob is not None and home_impl is not None:
                edge = (home_prob - home_impl) * 100
                if edge >= min_edge and confidence_tier(home_prob) in (
                    ["High", "Medium", "Low"] if confidence == "All" else [confidence]
                ):
                    kelly = kelly_fraction(home_prob, row.get("_home_ml_raw"))
                    value_rows.append({
                        "Game": matchup_label,
                        "Bet": f"{home_abbr_key} ML",
                        "Odds": row.get("Home ML"),
                        "Model Prob": f"{home_prob:.1%}",
                        "Implied": f"{home_impl:.1%}",
                        "Edge": f"+{edge:.1f}%",
                        "Kelly": f"{kelly:.1%}" if kelly is not None else "N/A",
                    })

            # Moneyline value: away side
            away_prob = pred["away_win_prob"]
            away_impl = row.get("_away_impl_raw")
            if away_prob is not None and away_impl is not None:
                edge = (away_prob - away_impl) * 100
                if edge >= min_edge and confidence_tier(away_prob) in (
                    ["High", "Medium", "Low"] if confidence == "All" else [confidence]
                ):
                    kelly = kelly_fraction(away_prob, row.get("_away_ml_raw"))
                    value_rows.append({
                        "Game": matchup_label,
                        "Bet": f"{away_abbr_key} ML",
                        "Odds": row.get("Away ML"),
                        "Model Prob": f"{away_prob:.1%}",
                        "Implied": f"{away_impl:.1%}",
                        "Edge": f"+{edge:.1f}%",
                        "Kelly": f"{kelly:.1%}" if kelly is not None else "N/A",
                    })

        # Totals value: compare model's total goal prediction against the market line
        # using a simple heuristic (directional signal only, since a full over/under
        # probability model isn't implemented yet).
        if "Totals" in bet_types:
            total_pred = pred.get("total_pred")
            over_line = row.get("_over_line")
            over_odds = row.get("_over_odds")
            under_odds = row.get("_under_odds")
            if total_pred is not None and over_line is not None:
                try:
                    over_line_f = float(over_line)
                except (TypeError, ValueError):
                    over_line_f = None
                if over_line_f is not None:
                    diff = total_pred - over_line_f
                    proxy_edge = abs(diff) * 5  # heuristic scaling, in percentage points
                    if proxy_edge >= min_edge:
                        side = "Over" if diff > 0 else "Under"
                        side_odds = over_odds if side == "Over" else under_odds
                        value_rows.append({
                            "Game": matchup_label,
                            "Bet": f"{side} {over_line_f}",
                            "Odds": side_odds if side_odds is not None else "N/A",
                            "Model Prob": "N/A",
                            "Implied": "N/A",
                            "Edge": f"~{proxy_edge:.1f}%",
                            "Kelly": "N/A",
                        })

        # Puck line value: no dedicated spread-win-probability model exists yet, so we
        # surface the market line/odds without a computed edge rather than a fabricated one.
        if "Puck Line" in bet_types:
            home_spread_line = row.get("_home_spread_line")
            home_spread_odds = row.get("_home_spread_odds")
            if home_spread_line is not None and home_spread_odds is not None:
                value_rows.append({
                    "Game": matchup_label,
                    "Bet": f"{home_abbr_key} {home_spread_line}",
                    "Odds": home_spread_odds,
                    "Model Prob": "N/A",
                    "Implied": f"{implied_prob(home_spread_odds):.1%}" if implied_prob(home_spread_odds) else "N/A",
                    "Edge": "N/A (no spread model yet)",
                    "Kelly": "N/A",
                })

if value_rows:
    value_df = pd.DataFrame(value_rows).sort_values(
        by="Edge",
        key=lambda col: col.str.replace("[+~%]", "", regex=True).str.replace("N/A (no spread model yet)", "-999", regex=False).astype(float),
        ascending=False,
    )
    st.dataframe(value_df, width='stretch', hide_index=True)
    st.caption(
        "Moneyline edge = model win probability \u2212 implied probability from odds. "
        "Totals edge is a directional heuristic (model has no calibrated over/under probability yet). "
        "Puck line rows show market odds only until a spread-specific model is added."
    )
else:
    if not preds_lookup:
        st.info("No model predictions available for the selected date, so value bets can't be computed.")
    elif not odds_list:
        st.info("No odds data available for the selected date, so value bets can't be computed.")
    else:
        st.info("No bets meet the current filters. Try lowering the minimum edge or selecting more bet types.")

# Add footer
add_betting_oracle_footer()

"""Identify bets with positive expected value."""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.api.nhl_client import NHLClient
from footer import add_betting_oracle_footer
from src.models.expected_goals import (
    TeamMetrics,
    calculate_expected_goals,
    calculate_expected_goals_with_analytics,
    calculate_total_xg,
)
from src.models.win_probability import calculate_win_probability

st.title("💰 Value Finder")
st.markdown("""
Find bets where the model's probability exceeds the implied odds.
A **positive edge** suggests potential value.
""")

@st.cache_resource
def get_client():
    return NHLClient()

client = get_client()


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
    if odds > 0:
        b = odds / 100
    elif odds < 0:
        b = 100 / abs(odds)
    else:
        return None
    return max((p * b - (1 - p)) / b, 0.0)


def normalize_abbrev(name):
    """Normalize a team abbreviation without guessing from a game name."""
    return str(name).strip().upper() if name else ""


def matches_schedule_date(event_date, schedule_date, venue_timezone):
    """Compare an ESPN UTC start time with the NHL schedule's venue-local date."""
    if not event_date or not venue_timezone:
        return False
    try:
        start = datetime.fromisoformat(str(event_date).replace("Z", "+00:00"))
        if start.tzinfo is None:
            return False
        return start.astimezone(ZoneInfo(venue_timezone)).date().isoformat() == schedule_date
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return False


selected_date = st.date_input("Select Date", value=date.today())
st.subheader(f"Value Bets for {selected_date:%Y-%m-%d}")
col1, col2 = st.columns(2)
with col1:
    min_edge = st.slider("Minimum Edge %", 0, 20, 3)
with col2:
    confidence = st.selectbox("Model Confidence", ["All", "High", "Medium", "Low"])
st.caption("Identified Value Bets currently supports moneyline only. Puck lines and totals remain visible in the odds table but are not ranked as value bets.")


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


st.subheader("Model Predictions")
preds_lookup = {}
schedule_games = {}
try:
    date_str = selected_date.strftime("%Y-%m-%d")
    schedule = client.get_schedule(date_str)
    games_list = []
    for week in schedule.get("gameWeek", []):
        if week.get("date") != date_str:
            continue
        for game in week.get("games", []):
            if game.get("gameType") in [2, 3]:
                games_list.append(game)

    if games_list:
        analytics_data = {}
        try:
            analytics_data = client.get_team_analytics(season="20252026")
        except Exception:
            analytics_data = {}

        preds = []
        for game in games_list:
            away_abbr = game.get("awayTeam", {}).get("abbrev")
            home_abbr = game.get("homeTeam", {}).get("abbrev")
            away_key = normalize_abbrev(away_abbr)
            home_key = normalize_abbrev(home_abbr)
            if not away_key or not home_key:
                continue
            venue_timezone = game.get("venueTimezone")
            if venue_timezone:
                schedule_games[(away_key, home_key)] = venue_timezone
            home_stats = client.get_team_summary(home_abbr)
            away_stats = client.get_team_summary(away_abbr)
            if home_stats and away_stats:
                home_tm = TeamMetrics.from_api_response(home_stats)
                away_tm = TeamMetrics.from_api_response(away_stats)

                home_analytics = analytics_data.get(home_abbr)
                away_analytics = analytics_data.get(away_abbr)
                if home_analytics and away_analytics:
                    home_xg, away_xg = calculate_expected_goals_with_analytics(
                        home_tm, away_tm,
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
                    "Model": model_source,
                    "Home xG": home_xg,
                    "Away xG": away_xg,
                    "Home Win %": f"{probs.home_win:.1%}",
                    "Away Win %": f"{probs.away_win:.1%}",
                    "Total Pred": total_pred,
                })
                preds_lookup[(away_key, home_key)] = {
                    "home_win_prob": probs.home_win,
                    "away_win_prob": probs.away_win,
                }
        if preds:
            preds_df = pd.DataFrame(preds)
            st.caption("Model uses analytics-blended xG when NHL team analytics are available; otherwise it falls back to the legacy goals-based estimate.")
            st.dataframe(
                preds_df,
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

st.subheader("Today's Betting Odds")
odds_list = []
try:
    odds_data = client.get_espn_odds(days_ahead=7)
    if odds_data:
        for game in odds_data:
            if not game.get("odds"):
                continue
            away_key = normalize_abbrev(game.get("away_team"))
            home_key = normalize_abbrev(game.get("home_team"))
            venue_timezone = schedule_games.get((away_key, home_key))
            if not matches_schedule_date(game.get("date"), date_str, venue_timezone):
                continue
            provider = game["odds"][0]
            home_ml = provider.get("moneyline", {}).get("home")
            away_ml = provider.get("moneyline", {}).get("away")
            home_impl = implied_prob(home_ml)
            away_impl = implied_prob(away_ml)
            home_spread_line = provider.get("spread", {}).get("home", {}).get("line")
            over_line = provider.get("total", {}).get("over", {}).get("line")
            odds_list.append({
                "Game": game.get("name", ""),
                "Home Team": game.get("home_team", ""),
                "Away Team": game.get("away_team", ""),
                "Home ML": home_ml if home_ml else "N/A",
                "Away ML": away_ml if away_ml else "N/A",
                "Home Impl%": f"{home_impl:.1%}" if home_impl is not None else "N/A",
                "Away Impl%": f"{away_impl:.1%}" if away_impl is not None else "N/A",
                "Spread": f"{home_spread_line}" if home_spread_line is not None else "N/A",
                "Total": f"{over_line}" if over_line is not None else "N/A",
                "Provider": provider.get("provider", "DraftKings"),
                "_home_ml_raw": home_ml,
                "_away_ml_raw": away_ml,
                "_home_impl_raw": home_impl,
                "_away_impl_raw": away_impl,
            })
        if odds_list:
            odds_df = pd.DataFrame(odds_list)
            st.dataframe(
                odds_df.drop(columns=[c for c in odds_df.columns if c.startswith("_")]),
                width='stretch', hide_index=True,
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
                },
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
            - Kelly % = (Model Prob × (Decimal Odds - 1) - (1 - Model Prob)) / (Decimal Odds - 1)
            """)
        else:
            st.info("No ESPN odds match NHL games on the selected date with exact home/away team abbreviations and venue-local start date.")
    else:
        st.info("Unable to fetch odds data.")
except Exception as e:
    st.error(f"Error loading odds: {e}")
    odds_list = []

st.divider()
st.subheader("Identified Value Bets")
value_rows = []
if odds_list and preds_lookup:
    for row in odds_list:
        home_abbr_key = normalize_abbrev(row.get("Home Team"))
        away_abbr_key = normalize_abbrev(row.get("Away Team"))
        pred = preds_lookup.get((away_abbr_key, home_abbr_key))
        if pred is None:
            continue
        matchup_label = f"{away_abbr_key} @ {home_abbr_key}"
        for abbrev, model_prob, implied, odds in (
            (home_abbr_key, pred["home_win_prob"], row.get("_home_impl_raw"), row.get("_home_ml_raw")),
            (away_abbr_key, pred["away_win_prob"], row.get("_away_impl_raw"), row.get("_away_ml_raw")),
        ):
            if model_prob is None or implied is None:
                continue
            edge = (model_prob - implied) * 100
            if edge < min_edge or (confidence != "All" and confidence_tier(model_prob) != confidence):
                continue
            kelly = kelly_fraction(model_prob, odds)
            value_rows.append({
                "Game": matchup_label,
                "Bet": f"{abbrev} ML",
                "Odds": odds,
                "Model Prob": f"{model_prob:.1%}",
                "Implied": f"{implied:.1%}",
                "Edge": f"+{edge:.1f}%",
                "Kelly": f"{kelly:.1%}" if kelly is not None else "N/A",
                "_edge": edge,
            })
if value_rows:
    value_rows.sort(key=lambda row: row["_edge"], reverse=True)
    st.dataframe(pd.DataFrame(value_rows).drop(columns="_edge"), width='stretch', hide_index=True)
    st.caption("Moneyline edge = model win probability − implied probability from odds. Model estimates and Kelly sizing are not validated betting recommendations.")
else:
    if not preds_lookup:
        st.info("No model predictions available for the selected date, so value bets can't be computed.")
    elif not odds_list:
        st.info("No matching ESPN odds available for the selected date, so value bets can't be computed.")
    else:
        st.info("No moneyline bets meet the current filters. Try lowering the minimum edge.")

add_betting_oracle_footer()

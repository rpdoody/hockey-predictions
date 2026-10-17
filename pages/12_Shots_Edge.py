"""Shots on goal props: model probability against DraftKings and FanDuel lines."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.api.nhl_client import NHLClient
from src.utils.name_match import team_lookup
from src.utils.prop_odds import ODDS_PATH, QUOTA_PATH
from src.utils.season import to_eastern
from src.utils.shots_backtest import previous_season_id
from src.utils.shots_edges import build_edges, latest_lines, read_snapshot_rows
from src.utils.shots_projector import build_context, candidates_by_team, project_event_players
from footer import add_betting_oracle_footer


st.title("🎯 Shots on Goal Edge Finder")
st.warning(
    "Experimental. The projection matches last season's shot rates, recent ice time, home/away, rest and "
    "opponent shot volume, and it has **not** been shown to beat the sportsbook lines. It cannot see injuries, "
    "scratches, line changes or power-play assignments. Treat any large edge as a sign of missing information "
    "and paper trade first."
)


@st.cache_resource
def get_client():
    return NHLClient()


@st.cache_data(ttl=6 * 3600, show_spinner="Learning last season's patterns (the first load takes a minute)...")
def load_context():
    client = get_client()
    season = client.display_season()
    return build_context(client, season, previous_season_id(season))


@st.cache_data(ttl=3600, show_spinner=False)
def load_candidates():
    return candidates_by_team(get_client().get_skater_stats(limit=-1, sort='shots'))


@st.cache_data(ttl=1800, show_spinner="Projecting players...")
def load_projections(entries):
    client = get_client()
    keys = ('event_id', 'player', 'home_team', 'away_team', 'commence_time')
    return project_event_players(
        client, load_context(), load_candidates(), team_lookup(client.TEAM_NAMES), [dict(zip(keys, e)) for e in entries],
    )


def start_label(iso):
    start = to_eastern(iso)
    return start.strftime('%a %I:%M %p ET') if start else iso


def render():
    rows = read_snapshot_rows(ODDS_PATH)
    if not rows:
        st.info(
            "No saved lines yet. The 'Capture NHL shots props' GitHub workflow saves DraftKings and FanDuel "
            "shots lines to data_files/props/shots_odds.jsonl; pull the repo after it has run."
        )
        return
    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    lines = latest_lines(rows, now_iso)
    if not lines:
        st.info("No upcoming games have saved lines. Lines are captured on game days a few hours before puck drop.")
        return

    entries = tuple(sorted({(l['event_id'], l['player'], l['home_team'], l['away_team'], l['commence_time']) for l in lines}))
    projections = load_projections(entries)
    edges = build_edges(lines, projections)

    matched = sum(1 for v in projections.values() if v.get('mu') is not None)
    quota_path = Path(QUOTA_PATH)
    remaining = json.loads(quota_path.read_text()).get('remaining') if quota_path.exists() else None
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Saved lines", len(lines))
    col2.metric("Players projected", f"{matched} of {len(projections)}")
    col3.metric("Scored lines", len(edges))
    col4.metric("Odds API credits left", remaining if remaining is not None else "unknown")

    unmatched = [(k[1], v['reason']) for k, v in projections.items() if v.get('mu') is None]
    if unmatched:
        with st.expander(f"{len(unmatched)} players could not be projected"):
            st.dataframe(pd.DataFrame(sorted(set(unmatched)), columns=["Sportsbook name", "Reason"]), hide_index=True)

    if not edges:
        st.info("No lines could be scored yet.")
        return

    frame = pd.DataFrame(edges)
    books = sorted(frame['book'].unique())
    c1, c2, c3, c4 = st.columns(4)
    chosen_books = c1.multiselect("Books", books, default=books)
    game = c2.selectbox("Game", ["All games"] + sorted(frame['game'].unique()))
    min_ev = c3.slider("Minimum expected value", 0.0, 0.20, 0.0, 0.01, format="%.2f")
    min_games = c4.slider("Minimum games played", 0, 15, 3)
    frame = frame[frame['book'].isin(chosen_books) & (frame['best_ev'] >= min_ev) & (frame['games'].fillna(0) >= min_games)]
    if game != "All games":
        frame = frame[frame['game'] == game]
    frame = frame.sort_values('best_ev', ascending=False)

    if frame.empty:
        st.info("No lines match these filters.")
        return
    table = pd.DataFrame({
        "Start": frame['commence_time'].map(start_label),
        "Game": frame['game'],
        "Player": frame['player'],
        "Team": frame['team'],
        "Book": frame['book'],
        "Line": frame['line'],
        "Over": frame['over_price'],
        "Under": frame['under_price'],
        "Model mean": frame['model_mean'].round(2),
        "Model P(over)": frame['model_p_over'].map('{:.1%}'.format),
        "Market P(over)": frame['market_p_over'].map('{:.1%}'.format),
        "Best side": frame['best_side'],
        "Price": frame['best_price'],
        "Edge": frame['best_edge'].map('{:+.1%}'.format),
        "EV": frame['best_ev'].map('{:+.1%}'.format),
        "Games": frame['games'],
        "Days since last game": frame['days_since_last'],
    })
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(
        "Edge is the model's probability for the best side minus the sportsbook's probability with the margin removed. "
        "EV is expected profit per unit staked if the model is right. Both are only as good as the model."
    )
    with st.expander("How to read this page"):
        st.markdown(
            "- **Model mean** is expected shots, from a shrunk shots-per-minute rate times recent ice time, "
            "adjusted for home/away, rest and opponent shot volume.\n"
            "- **Edge and EV** compare the model with each book's line after removing the margin. "
            "A positive number only matters if the model is calibrated, which the backtests suggest but do not prove.\n"
            "- **Large edges** (above about 10%) usually mean something the model cannot see, such as a scratched "
            "player, a line change or a power-play role. Check lineups before trusting one.\n"
            "- **Days since last game** flags players who may be injured: a long gap means the projection may be stale."
        )


render()
add_betting_oracle_footer()

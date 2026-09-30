'''Model performance: daily picks, plus logged predictions scored against the market.'''
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from footer import add_betting_oracle_footer
from src.utils.performance import (
    day_summary, load_final_scores, load_pick_log, load_scorecard,
    picks_for_date, segment_rows, verdict,
)

st.title('📈 Performance Tracker')

st.subheader('Daily picks')
yesterday = (datetime.now(ZoneInfo('America/New_York')) - timedelta(days=1)).date()
chosen = st.date_input('Game date', value=yesterday)
rows = picks_for_date(load_pick_log(), load_final_scores(), chosen.isoformat())
st.write(day_summary(rows))
if rows:
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
st.caption(
    'The pick is the side the blended model favors, using the last prediction logged before '
    'the game started. Edge is the model probability minus the market probability with the '
    'margin removed. Win/loss is on the final score, so it works from the first game, but a '
    'few games say very little about model quality.'
)

st.divider()
st.subheader('Is the model beating the market?')
report = load_scorecard()
if report is None or not report.get('games_scored'):
    st.info(
        'No scored games yet. Every upcoming game is logged before it starts, and the '
        'scorer fills this section in once those games finish.'
    )
    if report is not None:
        st.caption('Games logged so far: {}, waiting on results: {}.'.format(
            report.get('games_logged', 0), report.get('games_pending', 0)))
else:
    st.caption('Last updated {}. Results come from the daily scorer.'.format(
        report.get('generated_at', 'unknown')))

    col1, col2, col3 = st.columns(3)
    col1.metric('Games logged before start', report['games_logged'])
    col2.metric('Scored', report['games_scored'])
    col3.metric('Waiting on results', report['games_pending'])

    st.write(verdict(report))
    st.dataframe(pd.DataFrame(segment_rows(report)), width='stretch', hide_index=True)

    st.caption(
        'Log loss and Brier score measure probability quality; lower is better, and the market '
        'column is the bookmaker price with the margin removed. Simulated bets are 1-unit flat '
        'stakes at the logged price on games where the blended model shows at least a 3% edge. '
        'Closing-line value is how far the market moved toward the pick by the last price before '
        'the start. Small samples are mostly noise: judge log loss and closing-line value first, '
        'and ROI only after several hundred bets.'
    )

add_betting_oracle_footer()

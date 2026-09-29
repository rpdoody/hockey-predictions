'''Model performance: logged predictions scored against the market and real results.'''
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from footer import add_betting_oracle_footer
from src.utils.performance import load_scorecard, segment_rows, verdict

st.title('📈 Performance Tracker')

report = load_scorecard()
if report is None or not report.get('games_scored'):
    st.info(
        'No scored games yet. Every upcoming game is logged before it starts, and the '
        'scorer fills this page in once those games finish. Check back tomorrow morning.'
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

    st.subheader('Is the model beating the market?')
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

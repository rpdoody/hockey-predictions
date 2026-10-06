'''Model performance: daily picks, running dollar total, and logged predictions scored against the market.'''
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from footer import add_betting_oracle_footer
from src.utils.performance import (
    STAKE, daily_summary, day_summary, ledger_totals, load_final_scores, load_pick_log,
    load_scorecard, money, pick_ledger, picks_for_date, segment_rows, verdict,
)

st.title('📈 Performance Tracker')

entries = load_pick_log()
scores = load_final_scores()

st.subheader('Daily picks')
yesterday = (datetime.now(ZoneInfo('America/New_York')) - timedelta(days=1)).date()
chosen = st.date_input('Game date', value=yesterday)
rows = picks_for_date(entries, scores, chosen.isoformat())
st.write(day_summary(rows))
if rows:
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
st.caption(
    'The pick is the side the blended model favors, using the last prediction logged before '
    'the game started. Odds are the moneyline logged for that side at the same time. Edge is the '
    'model probability minus the market probability with the margin removed. Win/loss is on the '
    'final score, so it works from the first game, but a few games say very little about model quality.'
)

st.divider()
st.subheader('Running total at ${:.0f} per pick'.format(STAKE))
ledger = pick_ledger(entries, scores)
if not ledger:
    st.info('No graded picks yet. This section fills in after the first scored games.')
else:
    totals = ledger_totals(ledger)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Record', '{}-{}'.format(totals['wins'], totals['losses']))
    col2.metric('Profit', money(totals['profit']))
    col3.metric('Staked', '${:,.0f}'.format(totals['staked']))
    col4.metric('ROI', 'n/a' if totals['roi'] is None else '{:+.1%}'.format(totals['roi']))

    daily = daily_summary(ledger)
    st.line_chart(pd.DataFrame(daily).set_index('Date')[['Running total']])
    table = pd.DataFrame(daily)
    table['Day P/L'] = table['Day P/L'].map(money)
    table['Running total'] = table['Running total'].map(money)
    st.dataframe(table.iloc[::-1], width='stretch', hide_index=True)

    note = (
        'A flat ${:.0f} on every predicted winner, at the moneyline logged before the game '
        'started, whether the pick was the favorite or the underdog. This is every pick, not only '
        'the edge-filtered simulated bets in the table below.'
    ).format(STAKE)
    if totals['unpriced']:
        note += ' {} graded pick(s) had no logged moneyline: they count in the record but not in the dollars.'.format(
            totals['unpriced'])
    st.caption(note)

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

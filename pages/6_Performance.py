'''Model performance: daily picks, running dollar total, and logged predictions scored against the market.'''
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from footer import add_betting_oracle_footer
from src.utils.odds_storage import get_game_odds_history
from src.utils.totals_puckline import grade_games, summarize
from src.utils.daily_goals import daily_goal_projection
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
st.subheader('Goals projected for the day')
goal_day = st.date_input('Projection date', value=datetime.now(ZoneInfo('America/New_York')).date(), key='goals_day')
day_goals = daily_goal_projection(entries, scores, goal_day.isoformat(), get_game_odds_history)
if not day_goals['games']:
    st.info('No projections have been logged for this date yet.')
else:
    goal_cols = st.columns(4)
    goal_cols[0].metric('Projected goals', '{:.1f}'.format(day_goals['projected']), help='Sum of the expected goals logged for every game on the date.')
    if day_goals['market_games']:
        goal_cols[1].metric('Market total', '{:.1f}'.format(day_goals['market']), help='Sum of the DraftKings total lines, for {} of {} games.'.format(day_goals['market_games'], len(day_goals['games'])))
        goal_cols[2].metric('Model minus market', '{:+.1f}'.format(day_goals['projected_where_market'] - day_goals['market']), help='Compares the same {} games on both sides.'.format(day_goals['market_games']))
    else:
        goal_cols[1].metric('Market total', 'n/a')
        goal_cols[2].metric('Model minus market', 'n/a')
    if day_goals['finals']:
        goal_cols[3].metric('Actual so far', str(day_goals['actual']), delta='{:+.1f} vs projected'.format(day_goals['actual'] - day_goals['projected_where_final']), delta_color='off', help='{} of {} games final; shootout goals not counted.'.format(day_goals['finals'], len(day_goals['games'])))
    else:
        goal_cols[3].metric('Actual so far', 'n/a')
    with st.expander('Game by game'):
        st.dataframe(pd.DataFrame([{
            'Game': g['game'], 'Basis': g['basis'], 'Projected': round(g['projected'], 2),
            'Market': 'n/a' if g['market'] is None else g['market'],
            'Actual': '' if g['actual'] is None else g['actual'],
        } for g in day_goals['games']]), width='stretch', hide_index=True)
    st.caption(
        'Projected goals use each game\'s last logged projection before the start (the early blend while teams have played '
        'under 20 games). These expected totals have not been validated, so read the gap to the market as a lean, not a forecast.'
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

st.divider()
st.subheader('Totals and puck lines')
market_rows = grade_games(entries, scores, get_game_odds_history)
market_table = summarize(market_rows)
waiting = sum(r['status'] == 'pending' for r in market_rows)
unclear = sum(r['status'] == 'ungradable' for r in market_rows)
if not market_table:
    st.info('No graded totals or puck lines yet. This fills in once games with saved odds have final scores.')
else:
    market_df = pd.DataFrame(market_table)
    market_df['Profit'] = market_df['Profit'].map(money)
    market_df['ROI'] = market_df['ROI'].map(lambda v: 'n/a' if v is None else format(v, '+.1%'))
    st.dataframe(
        market_df, width='stretch', hide_index=True,
        column_config={
            'Log loss: model': st.column_config.NumberColumn('Log loss: model', format='%.4f'),
            'Log loss: market': st.column_config.NumberColumn('Log loss: market', format='%.4f'),
        },
    )
    placed = [r for r in market_rows if r['bet_result']]
    if placed:
        with st.expander('Bets placed ({})'.format(len(placed))):
            st.dataframe(pd.DataFrame([{
                'Date': r['date'], 'Game': r['game'], 'Market': r['market'], 'Line': r['line'],
                'Line source': r['line_source'], 'Bet': r['bet_side'], 'Odds': format(r['bet_odds'], '+d'),
                'Edge': format(r['edge'], '+.1%'), 'Result': r['bet_result'].title(),
                'Profit': money(r['profit']),
            } for r in placed]), width='stretch', hide_index=True)
st.caption(
    'Expected goals come straight from the raw model, which has not been validated for totals or puck lines. '
    'Lower log loss is better; the model is only useful here if it beats the market column. '
    'Bets are simulated at ${:.0f} flat on the side with at least a 3% edge over the market with the margin removed, '
    'using DraftKings prices from the last odds snapshot at or before the pick was logged. '
    'Puck-line numbers saved before this tracking began are inferred (the moneyline favorite lays 1.5). '
    'Overtime goals count toward totals and shootout goals do not. '
    '{} games are waiting on results and {} could not be graded.'.format(STAKE, waiting, unclear)
)

add_betting_oracle_footer()

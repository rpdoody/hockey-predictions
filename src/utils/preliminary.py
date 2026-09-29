'''Preliminary model-vs-market rows for the browse pages, read from the pick log.'''
from typing import List

from src.utils.scoring import fair_home_prob, parse_dt


def _latest_total(history) -> object:
    '''Most recent non-null total line in an odds history, or None.'''
    for snap in reversed((history or {}).get('snapshots', [])):
        if snap.get('total') is not None:
            return snap['total']
    return None


def preliminary_rows(rows: list, game_date: str, history_for=None) -> List[dict]:
    '''Latest logged prediction for each game on game_date, ordered by start time.

    history_for(game_id) may return the odds history used for the market total.
    '''
    latest = {}
    for row in rows:
        game_id = row.get('espn_game_id')
        logged = parse_dt(row.get('logged_at'))
        if row.get('game_date') != game_date or not game_id or logged is None:
            continue
        if game_id not in latest or logged > latest[game_id][0]:
            latest[game_id] = (logged, row)

    result = []
    for game_id, (logged, row) in latest.items():
        away = row.get('away_team')
        home = row.get('home_team')
        market = fair_home_prob(row.get('home_ml'), row.get('away_ml'))
        used = row.get('home_win_prob_used')
        home_xg = row.get('home_xg')
        away_xg = row.get('away_xg')
        expected = None if home_xg is None or away_xg is None else home_xg + away_xg
        market_total = _latest_total(history_for(game_id)) if history_for else None
        result.append({
            'start_utc': row.get('start_utc') or '',
            'matchup': f'{away} @ {home}',
            'game_time': row.get('game_time') or '',
            'model_source': row.get('model_source') or '',
            'market_home': market,
            'model_raw_home': row.get('home_win_prob_raw'),
            'model_used_home': used,
            'gap': None if used is None or market is None else used - market,
            'expected_total': expected,
            'market_total': market_total,
            'total_gap': None if expected is None or market_total is None else expected - market_total,
            'logged_at': logged.strftime('%Y-%m-%d %H:%M UTC'),
        })
    return sorted(result, key=lambda item: item['start_utc'])


def _num(value, spec: str) -> str:
    return 'n/a' if value is None else format(value, spec)


def display_rows(rows: List[dict]) -> List[dict]:
    '''Format preliminary rows for st.dataframe.'''
    table = []
    for item in rows:
        gap = item['gap']
        table.append({
            'Matchup': item['matchup'],
            'Start': item['game_time'],
            'Market home win %': _num(item['market_home'], '.1%'),
            'Model home win % (raw)': _num(item['model_raw_home'], '.1%'),
            'Model home win % (blended)': _num(item['model_used_home'], '.1%'),
            'Gap vs market': 'n/a' if gap is None else f'{gap * 100:+.1f} pts',
            'Expected total': _num(item['expected_total'], '.2f'),
            'Market total': _num(item['market_total'], '.1f'),
            'Total gap': _num(item['total_gap'], '+.2f'),
            'Basis': item['model_source'],
        })
    return table

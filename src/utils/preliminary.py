'''Preliminary model-vs-market rows for the browse pages, read from the pick log.'''
from typing import List

from src.utils.scoring import fair_home_prob, parse_dt


def preliminary_rows(rows: list, game_date: str) -> List[dict]:
    '''Latest logged prediction for each game on game_date, ordered by start time.'''
    latest = {}
    for row in rows:
        game_id = row.get('espn_game_id')
        logged = parse_dt(row.get('logged_at'))
        if row.get('game_date') != game_date or not game_id or logged is None:
            continue
        if game_id not in latest or logged > latest[game_id][0]:
            latest[game_id] = (logged, row)

    result = []
    for logged, row in latest.values():
        away = row.get('away_team')
        home = row.get('home_team')
        market = fair_home_prob(row.get('home_ml'), row.get('away_ml'))
        used = row.get('home_win_prob_used')
        result.append({
            'start_utc': row.get('start_utc') or '',
            'matchup': f'{away} @ {home}',
            'game_time': row.get('game_time') or '',
            'model_source': row.get('model_source') or '',
            'market_home': market,
            'model_raw_home': row.get('home_win_prob_raw'),
            'model_used_home': used,
            'gap': None if used is None or market is None else used - market,
            'logged_at': logged.strftime('%Y-%m-%d %H:%M UTC'),
        })
    return sorted(result, key=lambda item: item['start_utc'])


def _pct(value) -> str:
    return 'n/a' if value is None else f'{value:.1%}'


def display_rows(rows: List[dict]) -> List[dict]:
    '''Format preliminary rows for st.dataframe.'''
    table = []
    for item in rows:
        gap = item['gap']
        table.append({
            'Matchup': item['matchup'],
            'Start': item['game_time'],
            'Market home win %': _pct(item['market_home']),
            'Model home win % (raw)': _pct(item['model_raw_home']),
            'Model home win % (blended)': _pct(item['model_used_home']),
            'Gap vs market': 'n/a' if gap is None else f'{gap * 100:+.1f} pts',
            'Basis': item['model_source'],
        })
    return table

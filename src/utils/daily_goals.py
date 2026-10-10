'''Projected, market and actual goals for one day of games.'''
from typing import Callable, Optional

from src.utils.performance import _latest_entries
from src.utils.totals_puckline import settled_totals


def market_total(history: Optional[dict]) -> Optional[float]:
    '''Latest total line saved for the game, or None.'''
    for snap in reversed((history or {}).get('snapshots', [])):
        if snap.get('total') is not None:
            return float(snap['total'])
    return None


def actual_goals(score: Optional[dict]) -> Optional[int]:
    '''Goals a sportsbook counts (a shootout goal does not count); None if unplayed or unclear.'''
    if score is None:
        return None
    totals = settled_totals(score)
    return next(iter(totals)) if len(totals) == 1 else None


def daily_goal_projection(entries: list, scores: dict, game_date: str, get_history: Optional[Callable] = None) -> dict:
    '''Projected, market and actual goals for the games on game_date.

    Each game uses its last logged projection from before the start. Market and actual sums only
    count the games that have a market total or a final score, and the projected sums for those
    same games are returned alongside so the comparison is like for like.
    '''
    games = []
    for away, home, entry in _latest_entries(entries, game_date):
        home_xg, away_xg = entry.get('home_xg'), entry.get('away_xg')
        if home_xg is None or away_xg is None:
            continue
        score = scores.get('{}|{}|{}'.format(game_date, home, away))
        history = get_history(str(entry.get('espn_game_id'))) if get_history else None
        games.append({
            'game': '{} @ {}'.format(away, home),
            'basis': entry.get('model_source') or '',
            'projected': home_xg + away_xg,
            'market': market_total(history),
            'actual': actual_goals(score),
            'final': score is not None,
        })
    with_market = [g for g in games if g['market'] is not None]
    finals = [g for g in games if g['actual'] is not None]
    return {
        'games': games,
        'projected': sum(g['projected'] for g in games),
        'market': sum(g['market'] for g in with_market),
        'market_games': len(with_market),
        'projected_where_market': sum(g['projected'] for g in with_market),
        'finals': len(finals),
        'actual': sum(g['actual'] for g in finals),
        'projected_where_final': sum(g['projected'] for g in finals),
    }

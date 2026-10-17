'''Diagnostics and tuning for the totals and puck-line model.'''
import math
from typing import Callable, List, Optional

from src.utils.performance import _latest_entries
from src.utils.totals_puckline import _log_loss, grade_games

MIN_SAMPLE = 30


def _decided(rows: List[dict], market: str) -> List[dict]:
    return [r for r in rows
            if r['market'] == market and r['status'] == 'graded' and r['outcome'] is not None]


def calibration_table(rows: List[dict], market: str, bins: int = 5) -> List[dict]:
    '''Model vs market vs actual rate for side A (Over / home), sorted into equal-size bins.'''
    items = sorted(_decided(rows, market), key=lambda r: r['model_p'])
    if not items:
        return []
    size = max(1, math.ceil(len(items) / bins))
    table = []
    for i in range(0, len(items), size):
        chunk = items[i:i + size]
        n = len(chunk)
        table.append({
            'bin': len(table) + 1, 'n': n,
            'model_p': sum(r['model_p'] for r in chunk) / n,
            'market_p': sum(r['market_p'] for r in chunk) / n,
            'actual': sum(r['outcome'] for r in chunk) / n,
        })
    return table


def blend_weight(rows: List[dict], market: str, step: float = 0.1) -> Optional[dict]:
    '''Weight w on the model (1-w on the market) that minimises log loss.'''
    items = _decided(rows, market)
    if len(items) < MIN_SAMPLE:
        return None
    results = []
    for k in range(int(round(1 / step)) + 1):
        w = k * step
        pairs = [(w * r['model_p'] + (1 - w) * r['market_p'], r['outcome']) for r in items]
        results.append((w, _log_loss(pairs)))
    best = min(results, key=lambda x: x[1])
    return {
        'market': market, 'n': len(items), 'best_weight': round(best[0], 2),
        'log_loss_best': best[1], 'log_loss_model': results[-1][1],
        'log_loss_market': results[0][1],
    }


def total_bias(entries: List[dict], scores: dict, rows: Optional[List[dict]] = None) -> Optional[dict]:
    '''Mean model total vs mean actual total (and mean market line when rows are given).'''
    pairs = []
    for game_date in sorted({e.get('game_date') for e in entries if e.get('game_date')}):
        for away, home, entry in _latest_entries(entries, game_date):
            score = scores.get('{}|{}|{}'.format(game_date, home, away))
            if score and entry.get('home_xg') is not None and entry.get('away_xg') is not None:
                pairs.append((entry['home_xg'] + entry['away_xg'],
                              score['home_goals'] + score['away_goals']))
    if not pairs:
        return None
    n = len(pairs)
    out = {'n': n, 'model_mean': sum(p[0] for p in pairs) / n,
           'actual_mean': sum(p[1] for p in pairs) / n}
    if rows:
        lines = [r['line'] for r in _decided(rows, 'Total')]
        out['market_line_mean'] = sum(lines) / len(lines) if lines else None
    return out


def tune_goal_scale(entries: List[dict], scores: dict, get_history: Callable, market: str,
                    scales=(0.90, 0.95, 1.0, 1.05, 1.10)) -> List[dict]:
    '''Log loss when both teams' expected goals are multiplied by a scale.'''
    results = []
    for s in scales:
        scaled = [{**e,
                   'home_xg': e['home_xg'] * s if e.get('home_xg') is not None else None,
                   'away_xg': e['away_xg'] * s if e.get('away_xg') is not None else None}
                  for e in entries]
        items = _decided(grade_games(scaled, scores, get_history), market)
        results.append({'scale': s, 'n': len(items),
                        'log_loss': _log_loss([(r['model_p'], r['outcome']) for r in items])})
    return results

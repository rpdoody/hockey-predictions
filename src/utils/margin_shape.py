'''Empty-net shape correction for puck-line margins.

Independent Poisson goals understate two-goal games, because a team leading by one late
often adds an empty-net goal. This moves a share q of regulation one-goal margins to two
goals. Totals are left alone: expected goals already include empty-net goals, so adding
one would count it twice.
'''
from typing import Callable, Dict, List, Optional

from src.utils.totals_puckline import MAX_GOALS, OT_SHARE, _pmf, model_distribution

TARGET_TWO_GOAL_SHARE = 0.568


def _split(home_xg: float, away_xg: float) -> Dict[str, float]:
    '''P(regulation margin is +-1) and P(final margin is 2+) before any correction.'''
    home_pmf, away_pmf = _pmf(home_xg), _pmf(away_xg)
    one = two_plus = 0.0
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            gap = abs(h - a)
            p = home_pmf[h] * away_pmf[a]
            if gap == 1:
                one += p
            elif gap >= 2:
                two_plus += p
    norm = sum(home_pmf[h] * away_pmf[a] for h in range(MAX_GOALS + 1) for a in range(MAX_GOALS + 1))
    return {'one': one / norm, 'two_plus': two_plus / norm}


def shaped_distribution(home_xg: float, away_xg: float, q: float, ot_share: float = OT_SHARE) -> dict:
    '''Same output shape as model_distribution; q moves one-goal margins to two goals.'''
    base = model_distribution(home_xg, away_xg, ot_share)
    if q <= 0:
        return base
    home_pmf, away_pmf = _pmf(home_xg), _pmf(away_xg)
    norm = sum(home_pmf[h] * away_pmf[a] for h in range(MAX_GOALS + 1) for a in range(MAX_GOALS + 1))
    margins = dict(base['margins'])
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            gap = h - a
            if abs(gap) != 1:
                continue
            moved = q * home_pmf[h] * away_pmf[a] / norm
            margins[gap] = margins.get(gap, 0.0) - moved
            margins[2 * gap] = margins.get(2 * gap, 0.0) + moved
    return {'totals': base['totals'], 'margins': margins}


def two_goal_share(entries: List[dict], q: float = 0.0) -> Optional[float]:
    '''Average modelled share of games with a final margin of two goals or more.'''
    values = []
    for e in entries:
        h, a = e.get('home_xg'), e.get('away_xg')
        if h is None or a is None or h + a <= 0:
            continue
        s = _split(h, a)
        values.append(s['two_plus'] + q * s['one'])
    return sum(values) / len(values) if values else None


def fit_q(entries: List[dict], target: float = TARGET_TWO_GOAL_SHARE) -> Optional[float]:
    '''Closed form: the two-goal share is linear in q, so solve it directly.'''
    values = []
    for e in entries:
        h, a = e.get('home_xg'), e.get('away_xg')
        if h is None or a is None or h + a <= 0:
            continue
        values.append(_split(h, a))
    if not values:
        return None
    base_two = sum(v['two_plus'] for v in values) / len(values)
    base_one = sum(v['one'] for v in values) / len(values)
    return min(max((target - base_two) / base_one, 0.0), 1.0) if base_one else None

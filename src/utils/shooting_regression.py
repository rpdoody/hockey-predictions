"""Shooting-luck flags: compare goals with what a typical player of the same type scores on the same shots."""
import math
from typing import Dict, List, Optional

ALPHA = 0.01
MIN_SHOTS = 15
PRIOR_SHOTS = 200
_EPS = 1e-4


def position_group(code: Optional[str]) -> str:
    """Defensemen shoot very differently from forwards, so they get their own baseline."""
    return 'D' if code == 'D' else 'F'


def position_baselines(skaters: List[dict]) -> Dict[str, float]:
    """League goals-per-shot for forwards ('F') and defensemen ('D'), pooled from the supplied skaters."""
    goals: Dict[str, float] = {}
    shots: Dict[str, float] = {}
    for p in skaters:
        group = position_group(p.get('position'))
        goals[group] = goals.get(group, 0) + (p.get('goals') or 0)
        shots[group] = shots.get(group, 0) + (p.get('shots') or 0)
    return {g: goals[g] / shots[g] for g in shots if shots[g] > 0}


def _log_pmf(k: int, n: int, p: float) -> float:
    return (
        math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
        + k * math.log(p) + (n - k) * math.log1p(-p)
    )


def binomial_tail(k: int, n: int, p: float, upper: bool = True) -> float:
    """P(X >= k) when upper, else P(X <= k), for X ~ Binomial(n, p)."""
    if not 0 < p < 1:
        raise ValueError('p must be strictly between 0 and 1')
    ks = range(max(k, 0), n + 1) if upper else range(0, min(k, n) + 1)
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in ks))


def regression_candidates(
    skaters: List[dict],
    min_shots: int = MIN_SHOTS,
    alpha: float = ALPHA,
    prior_shots: int = PRIOR_SHOTS,
) -> dict:
    """Players whose goals are rare by luck alone against their position baseline.

    Returns {'baselines': {...}, 'rows': [...]} with rows sorted by how unlikely the result is.
    'shrunk_pct' pulls the player's own rate toward the baseline using prior_shots as the weight,
    because shooting skill is real and a hot rate does not fully revert.
    """
    baselines = position_baselines(skaters)
    rows = []
    for p in skaters:
        goals, shots = p.get('goals') or 0, p.get('shots') or 0
        group = position_group(p.get('position'))
        base = baselines.get(group)
        if base is None or shots < min_shots:
            continue
        base = min(max(base, _EPS), 1 - _EPS)
        p_hot = binomial_tail(goals, shots, base, upper=True)
        p_cold = binomial_tail(goals, shots, base, upper=False)
        if p_hot <= alpha:
            signal, p_value = 'hot', p_hot
        elif p_cold <= alpha:
            signal, p_value = 'cold', p_cold
        else:
            continue
        rows.append({
            'name': p.get('name'), 'team': p.get('team'), 'position': p.get('position'),
            'games': p.get('games', 0), 'goals': goals, 'shots': shots,
            'shooting_pct': goals / shots, 'baseline_pct': base,
            'expected_goals': shots * base, 'p_value': p_value, 'signal': signal,
            'shrunk_pct': (goals + prior_shots * base) / (shots + prior_shots),
        })
    rows.sort(key=lambda r: r['p_value'])
    return {'baselines': baselines, 'rows': rows}

'''Market-anchored adjustment for totals and puck lines.

logit(p) = logit(market_p) + a + c * (logit(model_p) - logit(market_p))

c = 0 means trust the market, c = 1 means trust the model. a is a small bias term.
Fitted by ridge-penalised logistic regression and scored walk-forward by date.
'''
import math
import random
from typing import Dict, List, Optional

import numpy as np

EPS = 1e-6
MIN_TRAIN = 40
RIDGE = 1.0


def _logit(p: float) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _usable(rows: List[dict], market: str) -> List[dict]:
    items = [r for r in rows if r['market'] == market and r['status'] == 'graded' and r['outcome'] is not None]
    return sorted(items, key=lambda r: r['date'])


def _design(items: List[dict]):
    lm = np.array([_logit(r['market_p']) for r in items])
    ld = np.array([_logit(r['model_p']) for r in items]) - lm
    y = np.array([float(r['outcome']) for r in items])
    return lm, ld, y


def fit(items: List[dict], ridge: float = RIDGE) -> Dict[str, float]:
    '''Fit a and c with Newton steps; the ridge pulls both toward 0 (pure market).'''
    lm, ld, y = _design(items)
    x = np.column_stack([np.ones(len(y)), ld])
    beta = np.zeros(2)
    for _ in range(50):
        p = _sigmoid(lm + x @ beta)
        grad = x.T @ (p - y) + ridge * beta
        hess = (x * (p * (1 - p))[:, None]).T @ x + ridge * np.eye(2)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return {'a': float(beta[0]), 'c': float(beta[1])}


def adjust(market_p: float, model_p: float, params: Dict[str, float]) -> float:
    lm = _logit(market_p)
    z = lm + params['a'] + params['c'] * (_logit(model_p) - lm)
    return float(_sigmoid(z))


def _loss(p: float, y: float) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def walk_forward(rows: List[dict], market: str, min_train: int = MIN_TRAIN,
                 ridge: float = RIDGE) -> Optional[dict]:
    '''Out-of-sample: fit on all earlier dates, predict each later date.'''
    items = _usable(rows, market)
    dates = sorted({r['date'] for r in items})
    scored = []
    for d in dates:
        train = [r for r in items if r['date'] < d]
        if len(train) < min_train:
            continue
        params = fit(train, ridge)
        for r in (r for r in items if r['date'] == d):
            scored.append({
                'market': _loss(r['market_p'], r['outcome']),
                'model': _loss(r['model_p'], r['outcome']),
                'anchored': _loss(adjust(r['market_p'], r['model_p'], params), r['outcome']),
                'c': params['c'],
            })
    if not scored:
        return None
    n = len(scored)

    def mean(key):
        return sum(s[key] for s in scored) / n

    return {
        'market': market, 'n_scored': n, 'n_total': len(items),
        'log_loss_market': mean('market'), 'log_loss_model': mean('model'),
        'log_loss_anchored': mean('anchored'), 'latest_c': scored[-1]['c'],
        'gain_vs_market': mean('market') - mean('anchored'),
        '_diffs': [s['market'] - s['anchored'] for s in scored],
    }


def gain_interval(result: dict, draws: int = 2000, seed: int = 7) -> tuple:
    '''95% bootstrap interval for the per-game log-loss gain over the market.'''
    diffs = result['_diffs']
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(draws))
    return means[int(0.025 * draws)], means[int(0.975 * draws)]


def report(rows: List[dict], market: str) -> Optional[dict]:
    result = walk_forward(rows, market)
    if result is None:
        return None
    low, high = gain_interval(result)
    out = {k: v for k, v in result.items() if k != '_diffs'}
    out.update({'gain_low': low, 'gain_high': high, 'params_full': fit(_usable(rows, market))})
    return out

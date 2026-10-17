'''Standard error of the model-vs-market log loss gap, so the verdict can say what a gap is worth.'''
import math
import statistics
from typing import List, Optional


def log_loss_gaps(rows: list, scores: dict, select=None, lookup=None, fair=None) -> List[float]:
    '''Per-game log loss of the shrunk model minus the market's; positive when the model is worse.

    Uses the scorer's own game selection, result lookup and vig-free market probability.
    '''
    if select is None or lookup is None or fair is None:
        from src.utils import scoring
        select = select or scoring.select_records
        lookup = lookup or scoring.lookup_result
        fair = fair or scoring.fair_home_prob
    eps = 1e-6
    gaps = []
    for row in select(rows, 'last'):
        score = lookup(scores, row['game_date'], row['home_team'], row['away_team'])
        market, used = fair(row.get('home_ml'), row.get('away_ml')), row.get('home_win_prob_used')
        if score is None or market is None or used is None:
            continue
        home_won = score['home_goals'] > score['away_goals']

        def loss(p):
            p = min(max(p, eps), 1 - eps)
            return -math.log(p if home_won else 1 - p)

        gaps.append(loss(used) - loss(market))
    return gaps


def gap_summary(gaps: List[float]) -> Optional[dict]:
    '''n, mean, standard error and a 95% range for per-game gaps; None under two games.'''
    n = len(gaps)
    if n < 2:
        return None
    mean = sum(gaps) / n
    se = statistics.stdev(gaps) / math.sqrt(n)
    return {'n': n, 'mean': mean, 'se': se, 'low': mean - 1.96 * se, 'high': mean + 1.96 * se}

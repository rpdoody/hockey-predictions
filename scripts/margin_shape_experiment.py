'''Compare puck-line grading before and after the empty-net margin correction.

Run from the repo root: python scripts/margin_shape_experiment.py
The correction is swapped in for this run only; production grading is not changed.
'''
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.margin_shape import fit_q, shaped_distribution, two_goal_share
from src.utils.market_anchor import report
from src.utils.odds_storage import get_game_odds_history
from src.utils.performance import load_final_scores, load_pick_log
from src.utils.totals_puckline import grade_games

KEYS = ('log_loss_market', 'log_loss_model', 'log_loss_anchored', 'gain_vs_market', 'gain_low', 'gain_high')


def main():
    entries, scores = load_pick_log(), load_final_scores()
    q = fit_q(entries)
    print('q', round(q, 4), 'two-goal share', round(two_goal_share(entries), 4), '->', round(two_goal_share(entries, q), 4))

    before = grade_games(entries, scores, get_game_odds_history)
    with patch('src.utils.totals_puckline.model_distribution',
               lambda h, a, ot=0.6: shaped_distribution(h, a, q, ot)):
        after = grade_games(entries, scores, get_game_odds_history)

    for market in ('Puck line', 'Total'):
        for name, rows in (('before', before), ('after', after)):
            result = report(rows, market)
            if result is None:
                print(market, name, 'not enough games')
                continue
            print(market, name, result['n_scored'], {k: round(result[k], 4) for k in KEYS})


if __name__ == '__main__':
    main()

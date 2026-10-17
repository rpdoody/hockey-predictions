'''Does shrinking the home-away expected-goals gap toward zero improve puck-line log loss?

Run from the repo root: python scripts/spread_shrink_experiment.py
factor 1.0 is the current model, 0.0 gives both teams the same expected goals. The game total
is kept fixed. Totals are not affected, so only the puck line is scored. Grading is swapped
for this run only; production code is not changed.
'''
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.margin_shape import fit_q, shaped_distribution
from src.utils.odds_storage import get_game_odds_history
from src.utils.performance import load_final_scores, load_pick_log
from src.utils.totals_diagnostics import _decided
from src.utils.totals_puckline import _log_loss, grade_games

FACTORS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25)


def shrink(entries, factor):
    out = []
    for e in entries:
        h, a = e.get('home_xg'), e.get('away_xg')
        if h is None or a is None:
            out.append(e)
            continue
        total, gap = h + a, h - a
        out.append({**e, 'home_xg': (total + factor * gap) / 2, 'away_xg': (total - factor * gap) / 2})
    return out


def score(rows):
    items = _decided(rows, 'Puck line')
    if not items:
        return None
    return (len(items),
            _log_loss([(r['model_p'], r['outcome']) for r in items]),
            _log_loss([(r['market_p'], r['outcome']) for r in items]))


def main():
    entries, scores = load_pick_log(), load_final_scores()
    print('factor  games  model   market  model-market   (with empty-net fix)')
    for factor in FACTORS:
        scaled = shrink(entries, factor)
        plain = score(grade_games(scaled, scores, get_game_odds_history))
        q = fit_q(scaled)
        with patch('src.utils.totals_puckline.model_distribution',
                   lambda h, a, ot=0.6, q=q: shaped_distribution(h, a, q, ot)):
            fixed = score(grade_games(scaled, scores, get_game_odds_history))
        if plain is None or fixed is None:
            print(factor, 'not enough games')
            continue
        print('{:<7} {:<6} {:.4f}  {:.4f}  {:+.4f}        {:.4f}  ({:+.4f})'.format(
            factor, plain[0], plain[1], plain[2], plain[1] - plain[2],
            fixed[1], fixed[1] - fixed[2]))


if __name__ == '__main__':
    main()

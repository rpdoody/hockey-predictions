'''Stretch the home-away expected-goals gap further, and split the results by model stage.

Run from the repo root: python scripts/spread_stretch_experiment.py
factor 1.0 is the current model; above 1.0 widens the gap between the teams, the game total
stays fixed. Only the puck line is scored. Grading is swapped for this run only.
The best factor is picked on the same games it is scored on, so treat it as a hypothesis.
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

FACTORS = (1.0, 1.25, 1.5, 2.0, 3.0)


def stretch(entries, factor):
    out = []
    for e in entries:
        h, a = e.get('home_xg'), e.get('away_xg')
        if h is None or a is None:
            out.append(e)
            continue
        total, gap = h + a, h - a
        out.append({**e, 'home_xg': max((total + factor * gap) / 2, 0.2),
                    'away_xg': max((total - factor * gap) / 2, 0.2)})
    return out


def gap_by_stage(rows):
    items = _decided(rows, 'Puck line')
    out = {}
    for label in ['All games'] + sorted({r['stage'] for r in items}):
        part = items if label == 'All games' else [r for r in items if r['stage'] == label]
        if part:
            model = _log_loss([(r['model_p'], r['outcome']) for r in part])
            market = _log_loss([(r['market_p'], r['outcome']) for r in part])
            out[label] = (len(part), model - market)
    return out


def main():
    entries, scores = load_pick_log(), load_final_scores()
    table = {}
    for factor in FACTORS:
        scaled = stretch(entries, factor)
        plain = gap_by_stage(grade_games(scaled, scores, get_game_odds_history))
        q = fit_q(scaled)
        with patch('src.utils.totals_puckline.model_distribution',
                   lambda h, a, ot=0.6, q=q: shaped_distribution(h, a, q, ot)):
            fixed = gap_by_stage(grade_games(scaled, scores, get_game_odds_history))
        for label, (n, gap) in plain.items():
            table.setdefault(label, []).append((factor, n, gap, fixed.get(label, (n, float('nan')))[1]))
    print('model log loss minus market log loss (lower is better, 0 means level with the market)')
    for label, rows in table.items():
        print('\n{} ({} games)'.format(label, rows[0][1]))
        print('factor  plain    with empty-net fix')
        for factor, _, plain_gap, fixed_gap in rows:
            print('{:<7} {:+.4f}  {:+.4f}'.format(factor, plain_gap, fixed_gap))


if __name__ == '__main__':
    main()

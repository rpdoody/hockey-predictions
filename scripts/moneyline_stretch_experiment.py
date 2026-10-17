'''Does stretching the home-away expected-goals gap help the moneyline too?

Run from the repo root: python scripts/moneyline_stretch_experiment.py
factor 1.0 is the current expected goals; above 1.0 widens the gap, the game total stays fixed.
The raw Poisson win probability is recomputed from the stretched goals and scored against the
market's vig-free home probability (fair_home_prob) on every finished game that has both.
The best factor is picked on the same games it is scored on, so treat it as a hypothesis.
'''
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.models.win_probability import calculate_win_probability
from src.utils.performance import _latest_entries, _stage, load_final_scores, load_pick_log
from src.utils.totals_puckline import _log_loss

FACTORS = (0.75, 1.0, 1.25, 1.5, 2.0, 3.0)


def collect(entries, scores):
    '''One record per finished game: stage, xg pair, market probability, home result.'''
    records = []
    for game_date in sorted({e.get('game_date') for e in entries if e.get('game_date')}):
        for away, home, entry in _latest_entries(entries, game_date):
            score = scores.get('{}|{}|{}'.format(game_date, home, away))
            h, a, fair = entry.get('home_xg'), entry.get('away_xg'), entry.get('fair_home_prob')
            if score is None or h is None or a is None or fair is None:
                continue
            records.append({
                'stage': _stage(entry), 'home_xg': h, 'away_xg': a, 'market_p': fair,
                'home_won': int(score['home_goals'] > score['away_goals']),
                'logged_raw': entry.get('home_win_prob_raw'),
            })
    return records


def stretched_probability(record, factor):
    total, gap = record['home_xg'] + record['away_xg'], record['home_xg'] - record['away_xg']
    home = max((total + factor * gap) / 2, 0.2)
    away = max((total - factor * gap) / 2, 0.2)
    return calculate_win_probability(home, away).home_win


def gap_for(records, factor):
    model = _log_loss([(stretched_probability(r, factor), r['home_won']) for r in records])
    market = _log_loss([(r['market_p'], r['home_won']) for r in records])
    return model - market


def main():
    records = collect(load_pick_log(), load_final_scores())
    if not records:
        print('No finished games with a market price yet.')
        return
    checks = [abs(stretched_probability(r, 1.0) - r['logged_raw']) for r in records if r['logged_raw'] is not None]
    if checks:
        print('sanity: factor 1.0 vs logged raw probability, largest difference {:.4f} over {} games'.format(max(checks), len(checks)))
    print('model log loss minus market log loss (lower is better, 0 means level with the market)')
    groups = [('All games', records)]
    for stage in sorted({r['stage'] for r in records}):
        groups.append((stage, [r for r in records if r['stage'] == stage]))
    for label, part in groups:
        print('\n{} ({} games)'.format(label, len(part)))
        for factor in FACTORS:
            print('{:<5} {:+.4f}'.format(factor, gap_for(part, factor)))


if __name__ == '__main__':
    main()

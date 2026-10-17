'''Forward test of the stretched expected-goals gap (the gap_stretch fields in the pick log).

Run from the repo root: python scripts/forward_stretch_eval.py
Uses only games whose last pre-game log row carries the stretch fields, so the factor was fixed
before these games were played. Nothing is refitted. Log loss is scored against the market's
vig-free price; a negative gap means the model beat the market. Intervals are 95% paired
bootstrap ranges over games.
'''
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.odds_storage import get_game_odds_history
from src.utils.performance import _latest_entries, _stage, load_final_scores, load_pick_log
from src.utils.totals_puckline import grade_games

MIN_GAMES = 100
EPS = 1e-6
DRAWS = 2000


def loss(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def has_stretch(entry):
    return all(entry.get(k) is not None for k in ('home_xg_stretch', 'away_xg_stretch', 'home_win_prob_stretch_raw'))


def interval(diffs, seed=11):
    '''(mean, low, high) of per-game differences by bootstrap.'''
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(DRAWS))
    return sum(diffs) / n, means[int(0.025 * DRAWS)], means[int(0.975 * DRAWS)]


def moneyline_records(entries, scores):
    records = []
    for game_date in sorted({e.get('game_date') for e in entries if e.get('game_date')}):
        for away, home, entry in _latest_entries(entries, game_date):
            score = scores.get('{}|{}|{}'.format(game_date, home, away))
            if score is None or not has_stretch(entry):
                continue
            if entry.get('fair_home_prob') is None or entry.get('home_win_prob_raw') is None:
                continue
            y = int(score['home_goals'] > score['away_goals'])
            records.append({
                'stage': _stage(entry),
                'current': loss(entry['home_win_prob_raw'], y),
                'stretch': loss(entry['home_win_prob_stretch_raw'], y),
                'market': loss(entry['fair_home_prob'], y),
            })
    return records


def puck_line_records(entries, scores):
    own = [e for e in entries if has_stretch(e)]
    stretched = [{**e, 'home_xg': e['home_xg_stretch'], 'away_xg': e['away_xg_stretch']} for e in own]

    def losses(rows):
        return {
            (r['date'], r['game']): (r['stage'], loss(r['model_p'], r['outcome']), loss(r['market_p'], r['outcome']))
            for r in rows
            if r['market'] == 'Puck line' and r['status'] == 'graded' and r['outcome'] is not None
        }

    current = losses(grade_games(own, scores, get_game_odds_history))
    wide = losses(grade_games(stretched, scores, get_game_odds_history))
    return [
        {'stage': current[k][0], 'current': current[k][1], 'stretch': wide[k][1], 'market': current[k][2]}
        for k in current if k in wide
    ]


def describe(title, records):
    print('\n{}: {} games'.format(title, len(records)))
    if len(records) < 10:
        print('  too few games to say anything yet')
        return
    if len(records) < MIN_GAMES:
        print('  fewer than {} games: read these numbers as noise'.format(MIN_GAMES))
    for label, a, b in (
        ('stretched minus market', 'stretch', 'market'),
        ('current minus market  ', 'current', 'market'),
        ('stretched minus current', 'stretch', 'current'),
    ):
        mean, low, high = interval([r[a] - r[b] for r in records])
        print('  {}  {:+.4f}  (95% range {:+.4f} to {:+.4f})'.format(label, mean, low, high))
    mean, low, high = interval([r['stretch'] - r['current'] for r in records])
    if high < 0:
        print('  verdict: the stretch beat the current model by more than chance.')
    elif low > 0:
        print('  verdict: the stretch did worse than the current model by more than chance.')
    else:
        print('  verdict: no clear difference between the stretch and the current model yet.')


def main():
    entries, scores = load_pick_log(), load_final_scores()
    print('Rows with stretch fields: {} of {}'.format(sum(has_stretch(e) for e in entries), len(entries)))
    money = moneyline_records(entries, scores)
    describe('Moneyline, all games', money)
    for stage in sorted({r['stage'] for r in money}):
        describe('Moneyline, ' + stage, [r for r in money if r['stage'] == stage])
    describe('Puck line, all games', puck_line_records(entries, scores))
    print('\nLower log loss is better. Puck lines here use the current grading without the empty-net fix.')


if __name__ == '__main__':
    main()

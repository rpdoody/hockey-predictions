'''Print log loss by blend weight k across past seasons, split by how far into the season each game is.

Usage: python scripts/tune_season_blend.py [--exclude 2020-21] [--home-advantage 0.05]
'''
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.blend_tuning import (
    K_GRID, by_bucket, log_loss, regular_season_games, replay, season_rates, total_error,
)

HISTORY = ROOT / 'data_files' / 'historical'


def load_games(season: str) -> list:
    path = HISTORY / season / 'games.json'
    return regular_season_games(json.loads(path.read_text())) if path.exists() else []


def collect(exclude: set, home_advantage) -> dict:
    seasons = sorted(p.name for p in HISTORY.iterdir() if re.fullmatch(r'\d{4}-\d{2}', p.name))
    results = {k: [] for k in K_GRID}
    used = []
    for prior, current in zip(seasons, seasons[1:]):
        if current in exclude:
            continue
        prior_games, games = load_games(prior), load_games(current)
        if not prior_games or not games:
            continue
        prior_rates, league = season_rates(prior_games)
        for k in K_GRID:
            results[k].extend(replay(games, prior_rates, league, k, home_advantage))
        used.append(current)
    print('Seasons replayed: ' + ', '.join(used))
    return results


def label(k: float) -> str:
    return 'prior only' if k >= 1e8 else 'current only' if k == 0 else 'k={:g}'.format(k)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exclude', nargs='*', default=['2020-21'],
                        help='seasons to skip (the 2020-21 default was a 56-game, realigned season)')
    parser.add_argument('--home-advantage', type=float, default=None)
    args = parser.parse_args()

    results = collect(set(args.exclude), args.home_advantage)
    grouped = {k: by_bucket(rows) for k, rows in results.items()}
    names = list(grouped[K_GRID[0]])
    print('\nLog loss of the home win probability (lower is better):')
    print('{:<10}{:>8}'.format('Games in', 'Games') + ''.join('{:>13}'.format(label(k)) for k in K_GRID))
    for name in names:
        losses = {k: log_loss(grouped[k][name]) for k in K_GRID}
        valid = {k: v for k, v in losses.items() if v is not None}
        best = min(valid, key=valid.get) if valid else None
        cells = ''.join(
            '{:>13}'.format('n/a' if losses[k] is None else '{:.4f}{}'.format(losses[k], '*' if k == best else ' '))
            for k in K_GRID
        )
        print('{:<10}{:>8}'.format(name, len(grouped[K_GRID[0]][name])) + cells)
    print('\n* = best k in that row.')
    print('\nMean absolute error of the expected total (goals):')
    for k in K_GRID:
        print('  {:<13}{:.3f}'.format(label(k), total_error(results[k])))
    return 0


if __name__ == '__main__':
    sys.exit(main())

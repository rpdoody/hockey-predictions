"""Test extra shots-projection inputs (home/away, back-to-back, opponent) on real NHL game logs. Spends no Odds API credits."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.api.nhl_client import NHLClient  # noqa: E402
from src.utils.shots_backtest import build_players, previous_season_id  # noqa: E402
from src.utils.shots_factors import format_experiment, opponent_factors, pooled_multipliers, run_factor_experiment  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--players', type=int, default=300, help="how many of last season's top shooters to test")
    parser.add_argument('--season', default=None, help='season id such as 20262027 (default: the display season)')
    args = parser.parse_args(argv)

    client = NHLClient()
    season = args.season or client.display_season()
    prior = previous_season_id(season)
    print(f'Testing extra inputs on {season} games, learning multipliers from {prior}...')
    players, skipped = build_players(client, season, prior, limit=args.players)
    print(f'{len(players)} players loaded, {skipped} skipped')
    if not players:
        print('No game logs loaded; nothing to test')
        return 1
    team_rows = client.get_team_stats(prior).get('data', [])
    opponents = opponent_factors(team_rows, client.ID_TO_TEAM_MAP)
    report = run_factor_experiment(players, pooled_multipliers(players), opponents)
    print(format_experiment(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())

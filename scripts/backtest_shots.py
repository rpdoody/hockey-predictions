"""Backtest the shots projection on real NHL game logs. Needs no odds data and spends no Odds API credits."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.api.nhl_client import NHLClient  # noqa: E402
from src.utils.shots_backtest import build_players, format_report, previous_season_id, run_backtest  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--players', type=int, default=300, help="how many of last season's top shooters to test")
    parser.add_argument('--season', default=None, help='season id such as 20262027 (default: the display season)')
    args = parser.parse_args(argv)

    client = NHLClient()
    season = args.season or client.display_season()
    prior = previous_season_id(season)
    print(f'Backtesting {season} games using {prior} as the prior season...')
    players, skipped = build_players(client, season, prior, limit=args.players)
    print(f'{len(players)} players loaded, {skipped} skipped')
    if not players:
        print('No game logs loaded; nothing to test')
        return 1
    print(format_report(run_backtest(players)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

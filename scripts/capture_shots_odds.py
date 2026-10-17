"""Capture DraftKings and FanDuel shots-on-goal prop lines for games starting soon."""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.prop_odds import DEFAULT_RESERVE, capture  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='open', help="snapshot label, e.g. 'open' or 'close'")
    parser.add_argument('--from-hours', type=float, default=0.0, help='only games starting at least this many hours from now')
    parser.add_argument('--to-hours', type=float, default=8.0, help='only games starting within this many hours')
    parser.add_argument('--max-events', type=int, default=20, help='most games to pull in one run')
    parser.add_argument('--reserve', type=int, default=DEFAULT_RESERVE, help='credits that must always remain')
    parser.add_argument('--dry-run', action='store_true', help='list the games that would be pulled; costs no credits')
    args = parser.parse_args(argv)

    api_key = os.environ.get('ODDS_API_KEY')
    if not api_key:
        print('ODDS_API_KEY is not set')
        return 2
    summary = capture(
        api_key, datetime.now(timezone.utc), from_hours=args.from_hours, to_hours=args.to_hours,
        label=args.label, max_events=args.max_events, reserve=args.reserve, dry_run=args.dry_run,
    )
    for key, value in summary.items():
        print(f'{key}: {value}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

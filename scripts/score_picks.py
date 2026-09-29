'''Score logged picks against final results and write data_files/results/scorecard.json.'''
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.api.nhl_client import NHLClient
from src.utils.odds_storage import get_game_odds_history
from src.utils.pick_log import read_pick_log
from src.utils.scoring import (
    format_report, lookup_result, parse_dt, parse_schedule, score, select_records,
)

LOG_DIR = ROOT / 'data_files' / 'pick_log'
RESULTS_DIR = ROOT / 'data_files' / 'results'
SCORES_PATH = RESULTS_DIR / 'final_scores.json'
SCORECARD_PATH = RESULTS_DIR / 'scorecard.json'


def _finished_by_now(record: dict) -> bool:
    start = parse_dt(record.get('start_utc'))
    return start is not None and start + timedelta(hours=4) < datetime.now(timezone.utc)


def refresh_results(records: list, results: dict, client: NHLClient) -> None:
    '''Fetch schedules for dates that still lack final scores.'''
    visited = set()
    while True:
        missing = sorted({
            r['game_date'] for r in records
            if r.get('game_date') not in visited
            and _finished_by_now(r)
            and lookup_result(results, r['game_date'], r['home_team'], r['away_team']) is None
        })
        if not missing:
            return
        day = missing[0]
        visited.add(day)
        try:
            payload = client._fetch_sync(
                f'{client.BASE_WEB_API}/schedule/{day}', ttl=timedelta(0)
            )
        except Exception as exc:
            print(f'Could not fetch schedule for {day}: {exc}')
            continue
        results.update(parse_schedule(payload))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--which', choices=['first', 'last'], default='last',
                        help='score the first or last pre-game prediction for each game')
    parser.add_argument('--min-edge', type=float, default=0.03,
                        help='minimum edge for a simulated bet (matches the generator)')
    parser.add_argument('--offline', action='store_true',
                        help='use stored final scores only, no network')
    args = parser.parse_args()

    os.chdir(ROOT)
    rows = read_pick_log(LOG_DIR)
    if not rows:
        print('No picks logged yet; nothing to score.')
        return 0

    results = json.loads(SCORES_PATH.read_text()) if SCORES_PATH.exists() else {}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        refresh_results(select_records(rows, args.which), results, NHLClient())
        SCORES_PATH.write_text(json.dumps(results, indent=2, sort_keys=True))

    report = score(rows, results, get_game_odds_history, args.min_edge, args.which)
    report['generated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    SCORECARD_PATH.write_text(json.dumps(report, indent=2))
    print(format_report(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())

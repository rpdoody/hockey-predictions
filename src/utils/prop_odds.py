"""The Odds API client for NHL player shots-on-goal props from DraftKings and FanDuel.

Credit use (per the API docs): the events call is free and reports the credits remaining;
a single-event odds call costs one credit per market returned, and up to 10 bookmakers
count as one region. One market and two bookmakers is therefore 1 credit per game, and a
response with no data costs nothing.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

import httpx

BASE_URL = 'https://api.the-odds-api.com/v4'
SPORT = 'icehockey_nhl'
SHOTS_MARKET = 'player_shots_on_goal'
BOOKMAKERS = ('draftkings', 'fanduel')
ODDS_PATH = Path('data_files/props/shots_odds.jsonl')
QUOTA_PATH = Path('data_files/props/odds_api_quota.json')
DEFAULT_RESERVE = 25


def _get_json(http_get: Callable, url: str, params: dict):
    response = http_get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json(), response.headers


def fetch_events(api_key: str, http_get: Callable = httpx.get):
    """Upcoming NHL events. Free, and the headers report the credits remaining."""
    return _get_json(http_get, f'{BASE_URL}/sports/{SPORT}/events', {'apiKey': api_key, 'dateFormat': 'iso'})


def fetch_event_shots(api_key: str, event_id: str, http_get: Callable = httpx.get):
    """Shots-on-goal lines for one event from the configured bookmakers."""
    params = {
        'apiKey': api_key, 'bookmakers': ','.join(BOOKMAKERS), 'markets': SHOTS_MARKET,
        'oddsFormat': 'american', 'dateFormat': 'iso',
    }
    return _get_json(http_get, f'{BASE_URL}/sports/{SPORT}/events/{event_id}/odds', params)


def parse_shot_lines(event: dict, snapshot_ts: str, label: str) -> List[dict]:
    """One row per book, player and line, with the over and under prices side by side."""
    rows = []
    for book in event.get('bookmakers', []):
        if book.get('key') not in BOOKMAKERS:
            continue
        for market in book.get('markets', []):
            if market.get('key') != SHOTS_MARKET:
                continue
            lines: dict = {}
            for outcome in market.get('outcomes', []):
                player, point = outcome.get('description'), outcome.get('point')
                side = (outcome.get('name') or '').lower()
                if not player or point is None or side not in ('over', 'under'):
                    continue
                lines.setdefault((player, point), {})[side] = outcome.get('price')
            for (player, point), sides in sorted(lines.items()):
                rows.append({
                    'snapshot_ts': snapshot_ts, 'label': label, 'event_id': event.get('id'),
                    'commence_time': event.get('commence_time'), 'home_team': event.get('home_team'),
                    'away_team': event.get('away_team'), 'book': book.get('key'), 'player': player,
                    'line': point, 'over_price': sides.get('over'), 'under_price': sides.get('under'),
                    'market_last_update': market.get('last_update'),
                })
    return rows


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def events_in_window(events: List[dict], now: datetime, from_hours: float, to_hours: float) -> List[dict]:
    """Events starting between from_hours and to_hours from now, soonest first."""
    start, end = now + timedelta(hours=from_hours), now + timedelta(hours=to_hours)
    window = [e for e in events if e.get('commence_time') and start <= _parse_time(e['commence_time']) <= end]
    return sorted(window, key=lambda e: e['commence_time'])


def captured_keys(path: Path) -> Set[Tuple[str, str]]:
    """(event_id, label) pairs that already have saved lines, so a game is never pulled twice."""
    path = Path(path)
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            keys.add((row['event_id'], row['label']))
    return keys


def append_rows(path: Path, rows: List[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        for row in rows:
            handle.write(json.dumps(row) + '\n')


def _int(value) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def save_quota(path: Path, headers, now: datetime) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'remaining': _int(headers.get('x-requests-remaining')),
        'used': _int(headers.get('x-requests-used')),
        'last_call_cost': _int(headers.get('x-requests-last')),
        'updated_at': now.isoformat(),
    }, indent=2))


def capture(
    api_key: str,
    now: datetime,
    from_hours: float = 0.0,
    to_hours: float = 8.0,
    label: str = 'open',
    max_events: int = 20,
    reserve: int = DEFAULT_RESERVE,
    odds_path: Path = ODDS_PATH,
    quota_path: Path = QUOTA_PATH,
    http_get: Callable = httpx.get,
    dry_run: bool = False,
) -> dict:
    """Save shots lines for games starting soon, never dipping below the credit reserve."""
    events, headers = fetch_events(api_key, http_get)
    remaining = _int(headers.get('x-requests-remaining'))
    save_quota(quota_path, headers, now)

    wanted = events_in_window(events, now, from_hours, to_hours)
    done = captured_keys(odds_path)
    pending = [e for e in wanted if (e['id'], label) not in done]
    todo = pending[:max_events]
    summary = {
        'events_listed': len(events), 'in_window': len(wanted),
        'already_captured': len(wanted) - len(pending), 'over_max_events': len(pending) - len(todo),
        'captured': 0, 'no_lines_yet': 0, 'credits_used': 0, 'credits_remaining': remaining, 'stopped': None,
    }
    if dry_run:
        summary['would_fetch'] = [f"{e['away_team']} at {e['home_team']}" for e in todo]
        return summary

    for event in todo:
        if remaining is not None and remaining - 1 < reserve:
            summary['stopped'] = f'credit reserve of {reserve} reached'
            break
        try:
            data, headers = fetch_event_shots(api_key, event['id'], http_get)
        except httpx.HTTPError as exc:
            summary['stopped'] = f'request failed: {exc}'
            break
        cost = _int(headers.get('x-requests-last'))
        summary['credits_used'] += cost if cost is not None else 0
        remaining = _int(headers.get('x-requests-remaining'))
        summary['credits_remaining'] = remaining
        save_quota(quota_path, headers, now)
        rows = parse_shot_lines(data, now.isoformat(), label)
        if rows:
            append_rows(odds_path, rows)
            summary['captured'] += 1
        else:
            summary['no_lines_yet'] += 1
    return summary

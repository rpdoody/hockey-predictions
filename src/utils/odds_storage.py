'''Store and retrieve historical odds.'''
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ODDS_DIR = Path('data_files/odds')

_PRICE_FIELDS = (
    'home_ml', 'away_ml', 'total', 'over_odds', 'under_odds', 'home_pl_odds', 'away_pl_odds'
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save_odds_snapshot(
    game_id: str,
    home_team: str,
    away_team: str,
    home_ml: int,
    away_ml: int,
    total: Optional[float] = None,
    over_odds: Optional[int] = None,
    under_odds: Optional[int] = None,
    home_pl_odds: Optional[int] = None,
    away_pl_odds: Optional[int] = None,
    start_time: Optional[str] = None,
    provider: Optional[str] = None,
) -> bool:
    '''Append an odds snapshot; markets that are not offered are stored as null.

    Returns False (and writes nothing) when the prices match the last snapshot.
    '''
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = ODDS_DIR / f'{game_id}.json'

    if file_path.exists():
        data = json.loads(file_path.read_text())
    else:
        data = {
            'game_id': game_id,
            'home_team': home_team,
            'away_team': away_team,
            'start_time': start_time,
            'snapshots': [],
        }
    if start_time and not data.get('start_time'):
        data['start_time'] = start_time

    snapshot = {
        'timestamp': _utc_now(),
        'provider': provider,
        'home_ml': home_ml,
        'away_ml': away_ml,
        'total': total,
        'over_odds': over_odds,
        'under_odds': under_odds,
        'home_pl_odds': home_pl_odds,
        'away_pl_odds': away_pl_odds,
    }
    if data['snapshots']:
        last = data['snapshots'][-1]
        if all(last.get(key) == snapshot[key] for key in _PRICE_FIELDS):
            return False
    data['snapshots'].append(snapshot)

    file_path.write_text(json.dumps(data, indent=2))
    return True


def get_game_odds_history(game_id: str) -> Optional[dict]:
    '''Get all odds snapshots for a game.'''
    file_path = ODDS_DIR / f'{game_id}.json'
    if file_path.exists():
        return json.loads(file_path.read_text())
    return None


def _first_last(snapshots: List[dict], key: str):
    values = [s[key] for s in snapshots if s.get(key) is not None]
    return (values[0], values[-1]) if values else (None, None)


def get_todays_movements() -> List[dict]:
    '''Get line movements for tracked games.'''
    movements = []

    for odds_file in ODDS_DIR.glob('*.json'):
        data = json.loads(odds_file.read_text())
        snapshots = data.get('snapshots', [])

        if len(snapshots) < 2:
            continue

        ml_open, ml_now = _first_last(snapshots, 'home_ml')
        total_open, total_now = _first_last(snapshots, 'total')
        ml_move = ml_now - ml_open if ml_open is not None else 0
        total_move = total_now - total_open if total_open is not None else 0.0

        if abs(ml_move) >= 10 or abs(total_move) >= 0.5:
            movements.append({
                'game_id': data['game_id'],
                'matchup': f"{data['away_team']} @ {data['home_team']}",
                'ml_move': ml_move,
                'total_move': total_move,
                'opening_ml': ml_open,
                'current_ml': ml_now,
                'opening_total': total_open,
                'current_total': total_now,
                'num_snapshots': len(snapshots),
            })

    return movements


def get_all_odds_files() -> List[Dict[str, any]]:
    '''Get metadata for all tracked odds files.'''
    files = []

    if not ODDS_DIR.exists():
        return files

    for odds_file in ODDS_DIR.glob('*.json'):
        data = json.loads(odds_file.read_text())
        snapshots = data.get('snapshots', [])

        if snapshots:
            files.append({
                'game_id': data.get('game_id'),
                'matchup': f"{data.get('away_team')} @ {data.get('home_team')}",
                'num_snapshots': len(snapshots),
                'first_snapshot': snapshots[0]['timestamp'][:19],
                'last_snapshot': snapshots[-1]['timestamp'][:19],
            })

    return files

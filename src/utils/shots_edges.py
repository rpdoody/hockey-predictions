"""Join saved sportsbook shots lines to model projections and score each side."""
import json
from pathlib import Path
from typing import Dict, List, Optional

from src.utils.shots_model import devig_two_way, expected_value, prob_over
from src.utils.shots_projector import DEFAULT_DISPERSION


def read_snapshot_rows(path: Path) -> List[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest_lines(rows: List[dict], now_iso: str, exclude_labels=('test',)) -> List[dict]:
    """The newest saved line for each book, player and line value, for games that have not started."""
    latest: Dict[tuple, dict] = {}
    for row in rows:
        if row.get('label') in exclude_labels or (row.get('commence_time') or '') <= now_iso:
            continue
        key = (row['event_id'], row['book'], row['player'], row['line'])
        if key not in latest or row['snapshot_ts'] > latest[key]['snapshot_ts']:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r['commence_time'], r['player'], r['book']))


def build_edges(lines: List[dict], projections: dict, dispersion: float = DEFAULT_DISPERSION) -> List[dict]:
    """Model probability against each book's vig-free line, for both sides. Skips lines it cannot score."""
    edges = []
    for line in lines:
        projection = projections.get((line['event_id'], line['player']))
        over_price, under_price, point = line.get('over_price'), line.get('under_price'), line.get('line')
        if not projection or projection.get('mu') is None or over_price is None or under_price is None or point is None:
            continue
        if float(point) == int(point):
            continue  # a whole-number line can push, which this model does not price
        fair = devig_two_way(over_price, under_price)
        p_over = prob_over(projection['mu'], dispersion, point)
        sides = {
            'Over': {'p': p_over, 'fair': fair['p_over'], 'price': over_price},
            'Under': {'p': 1.0 - p_over, 'fair': fair['p_under'], 'price': under_price},
        }
        for name, side in sides.items():
            side['ev'] = expected_value(side['p'], side['price'])
            side['edge'] = side['p'] - side['fair']
        best = max(sides, key=lambda s: sides[s]['ev'])
        edges.append({
            'event_id': line['event_id'], 'game': f"{line['away_team']} at {line['home_team']}",
            'commence_time': line['commence_time'], 'book': line['book'], 'player': line['player'],
            'team': projection.get('team'), 'position': projection.get('position'), 'line': point,
            'over_price': over_price, 'under_price': under_price, 'model_mean': projection['mu'],
            'model_p_over': p_over, 'market_p_over': fair['p_over'], 'overround': fair['overround'],
            'ev_over': sides['Over']['ev'], 'ev_under': sides['Under']['ev'],
            'best_side': best, 'best_price': sides[best]['price'], 'best_ev': sides[best]['ev'],
            'best_edge': sides[best]['edge'], 'games': projection.get('games'),
            'days_since_last': projection.get('days_since_last'),
            'snapshot_ts': line['snapshot_ts'], 'label': line['label'],
        })
    return edges

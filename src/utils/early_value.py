"""Early-season value-bet predictions for the Value Finder page, taken from the pick log."""
from typing import Callable, Dict, Iterable, Tuple

EARLY_VALUE_MIN_EDGE_PCT = 5.0
EARLY_BASIS = 'Early blend'


def early_blend_predictions(
    rows: Iterable[dict], game_date: str, normalize: Callable = lambda value: value,
) -> Dict[Tuple[str, str], dict]:
    """{(away, home): prediction} from the latest logged early-blend entry for each game on game_date.

    The probability is the logged one, already shrunk toward the market. Games that were
    projected from last season alone are left out, so they can never become value bets.
    """
    latest = {}
    for row in rows:
        if row.get('game_date') != game_date:
            continue
        if not str(row.get('model_source') or '').startswith(EARLY_BASIS):
            continue
        if row.get('home_win_prob_used') is None:
            continue
        key = (normalize(row.get('away_team')), normalize(row.get('home_team')))
        if key not in latest or str(row.get('logged_at') or '') > str(latest[key].get('logged_at') or ''):
            latest[key] = row
    return {
        key: {
            'home_win_prob': row['home_win_prob_used'],
            'away_win_prob': 1 - row['home_win_prob_used'],
            'basis': EARLY_BASIS,
            'min_edge': EARLY_VALUE_MIN_EDGE_PCT,
        }
        for key, row in latest.items()
    }

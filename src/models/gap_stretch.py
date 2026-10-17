'''Forward test of a wider home-away expected-goals gap.

Logged next to the normal projection and never used for picks or recommendations. Backtests on
the first games of the season found the averaged expected-goals formula halves the gap between
teams; a factor near 2 matched the market best on the puck line and moneyline, but that factor
was picked on the same games it was scored on. Logging it lets new games test it without refitting.
'''
from typing import Dict, Tuple

from src.models.win_probability import calculate_win_probability

GAP_STRETCH = 2.0
MIN_XG = 0.2


def stretch_xg(home_xg: float, away_xg: float, factor: float = GAP_STRETCH) -> Tuple[float, float]:
    '''Widen the home-away gap by factor while keeping the game total fixed.'''
    total, gap = home_xg + away_xg, home_xg - away_xg
    return max((total + factor * gap) / 2, MIN_XG), max((total - factor * gap) / 2, MIN_XG)


def stretched_fields(home_xg: float, away_xg: float, factor: float = GAP_STRETCH) -> Dict[str, float]:
    '''Extra pick-log fields: the stretched expected goals and the raw win probability they give.'''
    home, away = stretch_xg(home_xg, away_xg, factor)
    probs = calculate_win_probability(home, away)
    return {
        'gap_stretch': factor,
        'home_xg_stretch': round(home, 3),
        'away_xg_stretch': round(away, 3),
        'home_win_prob_stretch_raw': round(probs.home_win, 4),
    }

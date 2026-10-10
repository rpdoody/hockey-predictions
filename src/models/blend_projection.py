'''Blended projection for the pick log: last season's team stats plus this season's, by games played.'''
from typing import Optional

from src.models.expected_goals import TeamMetrics, calculate_expected_goals
from src.models.season_blend import K_GOALS, blend_team_metrics, current_weight
from src.models.win_probability import calculate_win_probability

BLEND_FIELDS = (
    'home_xg_blend', 'away_xg_blend', 'home_win_prob_blend_raw',
    'home_blend_weight', 'away_blend_weight',
)


def _metrics_for(stats: Optional[dict], abbrev: str) -> Optional[TeamMetrics]:
    '''TeamMetrics when the stats row really belongs to this team, otherwise None.'''
    if not stats or stats.get('team') != abbrev:
        return None
    try:
        return TeamMetrics.from_api_response(stats)
    except Exception:
        return None


def _team_side(abbrev: str, current: Optional[dict], prior: Optional[dict], k_goals: float):
    '''(blended metrics, this-season weight), or None when the team has no usable stats.'''
    prior_tm = _metrics_for(prior, abbrev)
    current_tm = _metrics_for(current, abbrev)
    games = (current or {}).get('games_played') or 0
    if current_tm is not None and games <= 0:
        current_tm = None
    if current_tm is None and prior_tm is None:
        return None
    blended = blend_team_metrics(current_tm, prior_tm, games, k_goals=k_goals)
    if current_tm is None:
        weight = 0.0
    elif prior_tm is None:
        weight = 1.0
    else:
        weight = current_weight(games, k_goals)
    return blended, weight


def blend_projection(
    home_abbr: str, away_abbr: str,
    home_current: Optional[dict], away_current: Optional[dict],
    home_prior: Optional[dict], away_prior: Optional[dict],
    k_goals: float = K_GOALS,
) -> dict:
    '''Expected goals and raw home win probability from blended team stats.

    Every BLEND_FIELDS key is always present; the values are None when a team has no stats.
    '''
    empty = {name: None for name in BLEND_FIELDS}
    home = _team_side(home_abbr, home_current, home_prior, k_goals)
    away = _team_side(away_abbr, away_current, away_prior, k_goals)
    if home is None or away is None:
        return empty
    try:
        home_xg, away_xg = calculate_expected_goals(home[0], away[0])
        home_win = calculate_win_probability(home_xg, away_xg).home_win
    except Exception:
        return empty
    return {
        'home_xg_blend': home_xg,
        'away_xg_blend': away_xg,
        'home_win_prob_blend_raw': round(home_win, 4),
        'home_blend_weight': round(home[1], 3),
        'away_blend_weight': round(away[1], 3),
    }

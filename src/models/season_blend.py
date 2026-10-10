'''Blend this season's team ratings with last season's, weighted by games played.

The current-season weight is n / (n + k): zero before the first game, one half
when n equals k. K_GOALS = 20 was the best overall weight when replaying the 2021-22
to 2025-26 seasons; the shot and special-teams weights are untuned guesses and do not
affect expected goals. Goals take longer to settle than shots, and special teams longest.
'''
from typing import Optional

from src.models.expected_goals import TeamMetrics

K_GOALS = 20.0
K_SHOTS = 20.0
K_SPECIAL_TEAMS = 60.0


def current_weight(games_played, k: float) -> float:
    '''Share of the blend given to this season: n / (n + k).'''
    games = max(float(games_played or 0), 0.0)
    if k <= 0:
        return 1.0 if games > 0 else 0.0
    return games / (games + k)


def blend_value(current: float, prior: float, weight: float) -> float:
    return weight * current + (1 - weight) * prior


def blend_team_metrics(
    current: Optional[TeamMetrics],
    prior: Optional[TeamMetrics],
    games_played,
    k_goals: float = K_GOALS,
    k_shots: float = K_SHOTS,
    k_special: float = K_SPECIAL_TEAMS,
) -> Optional[TeamMetrics]:
    '''Team metrics blended by games played; falls back to whichever side exists.'''
    if current is None or prior is None:
        return current if prior is None else prior
    w_goals = current_weight(games_played, k_goals)
    w_shots = current_weight(games_played, k_shots)
    w_special = current_weight(games_played, k_special)
    return TeamMetrics(
        team=current.team or prior.team,
        goals_for_pg=round(blend_value(current.goals_for_pg, prior.goals_for_pg, w_goals), 4),
        goals_against_pg=round(blend_value(current.goals_against_pg, prior.goals_against_pg, w_goals), 4),
        shots_for_pg=round(blend_value(current.shots_for_pg, prior.shots_for_pg, w_shots), 4),
        shots_against_pg=round(blend_value(current.shots_against_pg, prior.shots_against_pg, w_shots), 4),
        pp_pct=round(blend_value(current.pp_pct, prior.pp_pct, w_special), 4),
        pk_pct=round(blend_value(current.pk_pct, prior.pk_pct, w_special), 4),
    )

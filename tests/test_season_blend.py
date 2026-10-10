import pytest

from src.models.expected_goals import TeamMetrics
from src.models.season_blend import blend_team_metrics, current_weight


def _team(goals_for, goals_against, shots=30.0, pp=20.0):
    return TeamMetrics('TOR', goals_for, goals_against, shots, shots, pp, 80.0)


def test_weight_grows_with_games_played():
    assert current_weight(0, 30) == 0
    assert current_weight(None, 30) == 0
    assert current_weight(30, 30) == pytest.approx(0.5)
    assert current_weight(3, 20) == pytest.approx(3 / 23)
    assert current_weight(10, 30) < current_weight(20, 30) < current_weight(60, 30)


def test_no_games_means_last_season_only():
    blended = blend_team_metrics(_team(5.0, 4.0), _team(3.0, 2.5), 0)
    assert (blended.goals_for_pg, blended.goals_against_pg) == (3.0, 2.5)


def test_many_games_approach_this_season():
    blended = blend_team_metrics(_team(5.0, 4.0), _team(3.0, 2.5), 10000)
    assert blended.goals_for_pg == pytest.approx(5.0, abs=0.02)


def test_goals_shots_and_special_teams_use_their_own_weights():
    current = _team(4.0, 3.0, shots=34.0, pp=30.0)
    prior = _team(3.0, 3.0, shots=30.0, pp=20.0)
    blended = blend_team_metrics(current, prior, 20, k_goals=30, k_shots=20, k_special=60)
    assert blended.goals_for_pg == pytest.approx(3.0 + 1.0 * 0.4)
    assert blended.shots_for_pg == pytest.approx(30.0 + 4.0 * 0.5)
    assert blended.pp_pct == pytest.approx(20.0 + 10.0 * 0.25)


def test_missing_side_falls_back_to_the_other():
    team = _team(3.0, 2.5)
    assert blend_team_metrics(team, None, 5) is team
    assert blend_team_metrics(None, team, 5) is team
    assert blend_team_metrics(None, None, 5) is None

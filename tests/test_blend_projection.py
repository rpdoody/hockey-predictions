import pytest

from src.models.blend_projection import BLEND_FIELDS, blend_projection
from src.models.expected_goals import TeamMetrics, calculate_expected_goals


def _stats(team, goals_for, goals_against, games=0):
    return {
        'team': team, 'games_played': games, 'goals_for_pg': goals_for, 'goals_against_pg': goals_against,
        'shots_for_pg': 30, 'shots_against_pg': 30, 'pp_pct': 20, 'pk_pct': 80,
    }


PRIOR_HOME, PRIOR_AWAY = _stats('H', 3.0, 3.0, 82), _stats('A', 3.0, 3.0, 82)


def test_no_games_this_season_equals_last_season_only():
    result = blend_projection('H', 'A', _stats('H', 5.0, 2.0, 0), _stats('A', 1.0, 4.0, 0), PRIOR_HOME, PRIOR_AWAY)
    expected = calculate_expected_goals(TeamMetrics.from_api_response(PRIOR_HOME), TeamMetrics.from_api_response(PRIOR_AWAY))
    assert (result['home_xg_blend'], result['away_xg_blend']) == expected
    assert result['home_blend_weight'] == 0 and result['away_blend_weight'] == 0


def test_games_played_move_the_projection_toward_this_season():
    current_home, current_away = _stats('H', 5.0, 2.0, 20), _stats('A', 1.0, 4.0, 20)
    result = blend_projection('H', 'A', current_home, current_away, PRIOR_HOME, PRIOR_AWAY, k_goals=20)
    prior_only = blend_projection('H', 'A', None, None, PRIOR_HOME, PRIOR_AWAY)
    assert result['home_blend_weight'] == pytest.approx(0.5)
    assert result['home_xg_blend'] > prior_only['home_xg_blend']
    assert result['home_win_prob_blend_raw'] > prior_only['home_win_prob_blend_raw']


def test_stats_for_the_wrong_team_are_ignored():
    result = blend_projection('H', 'A', _stats('X', 5.0, 2.0, 20), _stats('A', 3.0, 3.0, 20), PRIOR_HOME, PRIOR_AWAY)
    assert result['home_blend_weight'] == 0
    assert result['away_blend_weight'] == pytest.approx(0.5)


def test_team_without_a_prior_season_uses_this_season_alone():
    result = blend_projection('H', 'A', _stats('H', 4.0, 3.0, 10), _stats('A', 3.0, 3.0, 10), {}, PRIOR_AWAY)
    assert result['home_blend_weight'] == 1.0
    assert result['home_xg_blend'] is not None


def test_missing_stats_give_empty_fields():
    result = blend_projection('H', 'A', None, None, {}, PRIOR_AWAY)
    assert set(result) == set(BLEND_FIELDS)
    assert all(value is None for value in result.values())

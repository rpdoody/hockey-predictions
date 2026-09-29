"""Regression tests for the home-ice advantage built into expected goals."""
from src.models.expected_goals import (
    DEFAULT_HOME_ADVANTAGE,
    TeamMetrics,
    calculate_expected_goals,
    calculate_expected_goals_with_analytics,
)
from src.models.win_probability import calculate_win_probability


def _average_team(name):
    return TeamMetrics(name, 3.0, 3.0, 30, 30, 20, 80)


def test_two_average_teams_get_a_realistic_home_win_probability():
    home_xg, away_xg = calculate_expected_goals(_average_team("H"), _average_team("A"))
    probs = calculate_win_probability(home_xg, away_xg)
    assert 0.51 <= probs.home_win <= 0.56


def test_average_teams_do_not_inflate_total_goals():
    home_xg, away_xg = calculate_expected_goals(_average_team("H"), _average_team("A"))
    assert abs((home_xg + away_xg) - 6.0) <= 0.15


def test_default_home_advantage_is_in_a_plausible_range():
    assert 0.02 <= DEFAULT_HOME_ADVANTAGE <= 0.08


def test_analytics_variant_without_analytics_matches_legacy():
    home, away = _average_team("H"), _average_team("A")
    assert calculate_expected_goals_with_analytics(home, away) == calculate_expected_goals(home, away)

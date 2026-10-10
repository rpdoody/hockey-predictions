import pytest

from src.utils.daily_goals import actual_goals, daily_goal_projection, market_total


def _entry(game_id, home, away, home_xg, away_xg, start='2026-10-10T17:00Z', source='Early blend (x)'):
    return {
        'espn_game_id': game_id, 'game_date': '2026-10-10', 'home_team': home, 'away_team': away,
        'start_utc': start, 'logged_at': '2026-10-10T12:00:00+00:00',
        'home_xg': home_xg, 'away_xg': away_xg, 'model_source': source,
    }


HISTORY = {'1': {'snapshots': [{'total': 5.5}, {'total': None}, {'total': 6.0}]}}


def test_market_total_is_the_latest_saved_line():
    assert market_total(HISTORY['1']) == 6.0
    assert market_total({'snapshots': [{'total': None}]}) is None
    assert market_total(None) is None


def test_shootout_goals_do_not_count_and_unclear_results_are_none():
    assert actual_goals({'home_goals': 3, 'away_goals': 2, 'period_type': 'SO'}) == 4
    assert actual_goals({'home_goals': 3, 'away_goals': 2, 'period_type': 'OT'}) == 5
    assert actual_goals({'home_goals': 5, 'away_goals': 1}) == 6
    assert actual_goals({'home_goals': 3, 'away_goals': 2}) is None
    assert actual_goals(None) is None


def test_day_sums_compare_like_with_like():
    entries = [_entry('1', 'BOS', 'PHI', 3.1, 2.9), _entry('2', 'TOR', 'MTL', 3.3, 3.2, start='2026-10-10T23:00Z')]
    scores = {'2026-10-10|BOS|PHI': {'home_goals': 3, 'away_goals': 2, 'period_type': 'SO'}}
    day = daily_goal_projection(entries, scores, '2026-10-10', lambda game_id: HISTORY.get(game_id))
    assert day['projected'] == pytest.approx(12.5)
    assert (day['market'], day['market_games'], day['projected_where_market']) == (6.0, 1, pytest.approx(6.0))
    assert (day['finals'], day['actual'], day['projected_where_final']) == (1, 4, pytest.approx(6.0))
    assert [g['game'] for g in day['games']] == ['PHI @ BOS', 'MTL @ TOR']
    assert day['games'][1]['final'] is False and day['games'][1]['actual'] is None


def test_games_without_a_projection_and_empty_days_are_handled():
    entries = [_entry('1', 'BOS', 'PHI', None, None)]
    day = daily_goal_projection(entries, {}, '2026-10-10')
    assert day['games'] == [] and day['projected'] == 0 and day['actual'] == 0
    assert daily_goal_projection([], {}, '2026-10-10')['finals'] == 0

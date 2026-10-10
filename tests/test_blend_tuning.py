import pytest

from src.models.blend_tuning import by_bucket, log_loss, regular_season_games, replay, season_rates


def _game(game_id, date, home, away, home_score, away_score, state='OFF'):
    return {
        'game_id': game_id, 'date': date, 'home_team': home, 'away_team': away,
        'home_score': home_score, 'away_score': away_score, 'game_state': state,
    }


def test_only_finished_regular_season_games_are_kept_in_date_order():
    games = [
        _game(2025020002, '2025-10-09', 'A', 'B', 2, 1),
        _game(2025030001, '2025-10-08', 'A', 'B', 2, 1),
        _game(2025020003, '2025-10-10', 'A', 'B', None, None),
        _game(2025020004, '2025-10-11', 'A', 'B', 2, 1, state='FUT'),
        _game(2025020001, '2025-10-07', 'A', 'B', 3, 2),
    ]
    kept = regular_season_games(games)
    assert [g['game_id'] for g in kept] == [2025020001, 2025020002]


def test_a_game_listed_several_times_is_counted_once():
    games = [_game(2025020001, '2025-10-07', 'A', 'B', 3, 2) for _ in range(7)]
    games.append(_game(2025020002, '2025-10-08', 'B', 'A', 1, 0))
    kept = regular_season_games(games)
    assert [g['game_id'] for g in kept] == [2025020001, 2025020002]
    rates, _ = season_rates(kept)
    assert rates['A'] == (1.5, 1.5)


def test_season_rates_and_league_average():
    games = [_game(1, '2025-10-07', 'A', 'B', 4, 1), _game(2, '2025-10-08', 'B', 'A', 2, 3)]
    rates, league = season_rates(games)
    assert rates['A'] == (3.5, 1.5)
    assert rates['B'] == (1.5, 3.5)
    assert league == (2.5, 2.5)


def _repeat_games(count):
    return [_game(i, '2025-10-{:02d}'.format(i + 1), 'H', 'A', 6, 0) for i in range(count)]


def test_prior_only_gives_the_same_forecast_every_time():
    rows = replay(_repeat_games(4), {'H': (3.0, 3.0), 'A': (3.0, 3.0)}, (3.0, 3.0), 1e9)
    assert max(r['p_home'] for r in rows) - min(r['p_home'] for r in rows) < 1e-6


def test_current_only_reacts_after_the_first_game():
    rows = replay(_repeat_games(4), {'H': (3.0, 3.0), 'A': (3.0, 3.0)}, (3.0, 3.0), 0)
    assert rows[0]['games_played'] == 0
    assert rows[1]['p_home'] > rows[0]['p_home']


def test_a_team_without_a_prior_season_uses_the_league_average():
    rows = replay(_repeat_games(1), {}, (3.0, 3.0), 30)
    assert len(rows) == 1 and 0.5 < rows[0]['p_home'] < 0.6


def test_log_loss_and_buckets():
    rows = [
        {'games_played': 0, 'p_home': 0.5, 'home_won': True, 'xg_total': 6.0, 'goals': 5},
        {'games_played': 25, 'p_home': 0.5, 'home_won': False, 'xg_total': 6.0, 'goals': 7},
    ]
    assert log_loss(rows) == pytest.approx(0.6931, abs=1e-3)
    groups = by_bucket(rows)
    assert len(groups['0-9']) == 1 and len(groups['20-39']) == 1 and len(groups['All games']) == 2

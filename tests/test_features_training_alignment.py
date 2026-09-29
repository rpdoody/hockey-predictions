"""Regression tests for feature/target alignment in prepare_training_data."""
import json

from src.models.features import NHLFeatureEngineer


def _game(game_id, day, home, away, home_score, away_score, home_won):
    return {
        "game_id": game_id,
        "date": f"2024-10-{day:02d}",
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "home_won": home_won,
    }


def _engineer(tmp_path, rows):
    season_dir = tmp_path / "2024-25"
    season_dir.mkdir()
    (season_dir / "games.json").write_text(json.dumps(rows))
    engineer = NHLFeatureEngineer()
    engineer.historical_data_path = tmp_path
    return engineer


def _rows():
    rows = []
    for i, day in enumerate([1, 3, 5, 7, 9, 11]):
        home, away = ("BUF", "NJD") if i % 2 == 0 else ("NJD", "BUF")
        rows.append(_game(2024020001 + i, day, home, away, 3, 2, True))
    rows.append(_game(2024020007, 13, "BUF", "NJD", None, None, None))
    rows.append(_game(2024020008, 15, "NJD", "BUF", 4, 1, None))
    rows.append(_game(2024020009, 17, "BUF", "NJD", 3, 2, True))
    return rows


def test_unresolved_games_do_not_desync_features_and_targets(tmp_path):
    engineer = _engineer(tmp_path, _rows())
    X, y = engineer.prepare_training_data(["2024-25"], min_games=1)
    assert len(X) == len(y) == 6
    assert set(y) == {1}


def test_feature_errors_skip_the_game_without_desync(tmp_path):
    engineer = _engineer(tmp_path, _rows())
    original = engineer.create_game_features
    calls = {"n": 0}

    def flaky(game, games_df, home_stats, away_stats):
        calls["n"] += 1
        if calls["n"] == 3:
            raise ValueError("boom")
        return original(game, games_df, home_stats, away_stats)

    engineer.create_game_features = flaky
    X, y = engineer.prepare_training_data(["2024-25"], min_games=1)
    assert len(X) == 5
    assert len(y) == 5

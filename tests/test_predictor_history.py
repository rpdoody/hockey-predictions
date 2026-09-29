"""Tests for how the predictor builds history and season stats."""
import json

import pytest

from src.models.features import NHLFeatureEngineer
from src.models.ml_predictor import NHLPredictor


def _game(game_id, day, home, away, home_score, away_score):
    finished = home_score is not None
    return {
        "game_id": game_id,
        "date": f"2025-10-{day:02d}",
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "home_won": (home_score > away_score) if finished else None,
    }


def _predictor(tmp_path, seasons):
    for season, rows in seasons.items():
        season_dir = tmp_path / season
        season_dir.mkdir()
        (season_dir / "games.json").write_text(json.dumps(rows))
    predictor = object.__new__(NHLPredictor)
    predictor.feature_engineer = NHLFeatureEngineer()
    predictor.feature_engineer.historical_data_path = tmp_path
    return predictor


def test_history_uses_the_latest_seasons_and_ignores_test_runs(tmp_path):
    predictor = _predictor(tmp_path, {
        "2022-23": [], "2023-24": [], "2024-25": [], "2025-26": [],
    })
    (tmp_path / "test_run").mkdir()
    (tmp_path / "test_run" / "test_games.json").write_text("[]")
    assert predictor._history_seasons() == ["2023-24", "2024-25", "2025-26"]
    assert predictor._history_seasons(count=2) == ["2024-25", "2025-26"]


def test_history_drops_unfinished_games(tmp_path):
    predictor = _predictor(tmp_path, {"2025-26": [
        _game(1, 1, "BUF", "NJD", 3, 2),
        _game(2, 3, "NJD", "BUF", 4, 1),
        _game(3, 5, "BUF", "NJD", None, None),
    ]})
    history = predictor._load_history()
    assert list(history["game_id"]) == [1, 2]


def test_point_in_time_stats_use_only_earlier_games(tmp_path):
    predictor = _predictor(tmp_path, {"2025-26": [
        _game(1, 1, "BUF", "NJD", 3, 2),
        _game(2, 3, "NJD", "BUF", 4, 1),
        _game(3, 5, "BUF", "NJD", 2, 1),
        _game(4, 7, "NJD", "BUF", 5, 0),
    ]})
    history = predictor._load_history()
    home_stats, away_stats = predictor._point_in_time_stats(history, "BUF", "NJD", "2025-10-06")
    assert home_stats["games_played"] == 3
    assert away_stats["games_played"] == 3
    assert home_stats["goals_for_pg"] == pytest.approx(2.0)
    assert home_stats["win_pct"] == pytest.approx(2 / 3)
    assert away_stats["goals_for_pg"] == pytest.approx(7 / 3)

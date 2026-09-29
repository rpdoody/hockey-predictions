"""Tests for historical game loading in the feature engineer."""
import json

import pandas as pd

from src.models.features import NHLFeatureEngineer


def _row(game_id, stamped_date, home="BUF", away="NJD"):
    return {
        "game_id": game_id,
        "date": stamped_date,
        "start_time": "2024-10-04T17:00:00Z",
        "home_team": home,
        "away_team": away,
        "home_score": 1,
        "away_score": 4,
        "home_won": False,
    }


def test_duplicate_game_rows_keep_latest_stamped_date(tmp_path):
    season_dir = tmp_path / "2024-25"
    season_dir.mkdir()
    rows = [
        _row(2024020001, "2024-10-01"),
        _row(2024020001, "2024-10-04"),
        _row(2024020001, "2024-10-02"),
        _row(2024020002, "2024-10-05", home="NJD", away="BUF"),
    ]
    (season_dir / "games.json").write_text(json.dumps(rows))

    engineer = NHLFeatureEngineer()
    engineer.historical_data_path = tmp_path
    games = engineer.load_historical_games(["2024-25"])

    assert len(games) == 2
    assert games["game_id"].is_unique
    kept = games.set_index("game_id")["date"]
    assert kept[2024020001] == pd.Timestamp("2024-10-04")
    assert kept[2024020002] == pd.Timestamp("2024-10-05")
    assert games["date"].is_monotonic_increasing

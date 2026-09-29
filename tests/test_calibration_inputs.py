"""Tests for the team stats and history used by calibration checks."""
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.models.features import NHLFeatureEngineer
from src.models.ml_predictor import NHLPredictor
from src.models.training import NHLModelTrainer

TEAM_FILE = "api.nhle.com_stats_rest_en_team_summary_cayenneExp=seasonId=20252026.json"


class _FakeScaler:
    def transform(self, X):
        return X


class _FakeModel:
    def predict_proba(self, X):
        return np.array([[0.4, 0.6]] * len(X))

    def predict(self, X):
        return np.ones(len(X), dtype=int)


def _row(game_id, day, home, away, home_score, away_score):
    return {
        "game_id": game_id,
        "date": day,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "home_won": home_score > away_score,
    }


def _season_rows(count):
    start = date(2025, 10, 1)
    rows = []
    for i in range(count):
        home, away = ("BUF", "NJD") if i % 2 == 0 else ("NJD", "BUF")
        rows.append(_row(2025020000 + i, (start + timedelta(days=i)).isoformat(), home, away, 3, 2))
    return rows


def test_load_team_stats_reads_fractions_and_real_field_names(tmp_path):
    record = {
        "teamFullName": "Washington Capitals",
        "gamesPlayed": 82,
        "wins": 43,
        "pointPct": 0.57926,
        "goalsForPerGame": 3.18292,
        "goalsAgainstPerGame": 2.90243,
        "powerPlayPct": 0.178423,
        "penaltyKillPct": 0.800797,
    }
    (tmp_path / TEAM_FILE).write_text(json.dumps({"data": [record]}))
    engineer = NHLFeatureEngineer()
    engineer.cache_path = tmp_path
    stats = engineer.load_team_stats()["WSH"]
    assert stats["pp_pct"] == pytest.approx(0.178423)
    assert stats["pk_pct"] == pytest.approx(0.800797)
    assert stats["win_pct"] == pytest.approx(43 / 82)
    assert stats["point_pct"] == pytest.approx(0.57926)
    assert stats["goals_for_pg"] == pytest.approx(3.18292)


def test_load_team_stats_accepts_percent_style_values(tmp_path):
    record = {
        "teamFullName": "Toronto Maple Leafs",
        "gamesPlayed": 82,
        "wins": 40,
        "powerPlayPct": 17.8,
        "penaltyKillPct": 80.1,
    }
    (tmp_path / TEAM_FILE).write_text(json.dumps({"data": [record]}))
    engineer = NHLFeatureEngineer()
    engineer.cache_path = tmp_path
    stats = engineer.load_team_stats()["TOR"]
    assert stats["pp_pct"] == pytest.approx(0.178)
    assert stats["pk_pct"] == pytest.approx(0.801)


def test_calibration_uses_point_in_time_stats(tmp_path):
    history = pd.DataFrame([
        _row(1, "2025-10-01", "BUF", "NJD", 3, 2),
        _row(2, "2025-10-03", "NJD", "BUF", 4, 1),
        _row(3, "2025-10-05", "BUF", "NJD", 2, 1),
        _row(4, "2025-10-06", "BUF", "NJD", 3, 1),
    ])
    validation = history.tail(1)

    trainer = NHLModelTrainer(model_dir=str(tmp_path / "models"))
    trainer.scaler = _FakeScaler()

    def no_snapshot(*args, **kwargs):
        raise AssertionError("calibration must not use the season snapshot")

    trainer.feature_engineer.load_team_stats = no_snapshot

    seen = []
    original = trainer.predict_game

    def spy(model_data, features):
        seen.append(features)
        return original(model_data, features)

    trainer.predict_game = spy

    model_data = {"model": _FakeModel(), "feature_columns": ["home_win_pct", "away_win_pct"]}
    result = trainer.validate_model_calibration(model_data, validation, history_games=history)

    assert result["n_games_validated"] == 1
    assert seen[0]["home_win_pct"] == pytest.approx(2 / 3)
    assert seen[0]["away_win_pct"] == pytest.approx(1 / 3)


def test_validate_predictions_passes_history_to_the_trainer(tmp_path):
    season_dir = tmp_path / "2025-26"
    season_dir.mkdir()
    (season_dir / "games.json").write_text(json.dumps(_season_rows(60)))

    class _SpyTrainer:
        def validate_model_calibration(self, model_data, validation_df, history_games=None):
            self.validation_df = validation_df
            self.history = history_games
            return {"ok": True}

    predictor = object.__new__(NHLPredictor)
    predictor.feature_engineer = NHLFeatureEngineer()
    predictor.feature_engineer.historical_data_path = tmp_path
    predictor.trainer = _SpyTrainer()
    predictor.model_data = {"model": object()}

    assert predictor.validate_predictions() == {"ok": True}
    assert len(predictor.trainer.validation_df) == 50
    assert len(predictor.trainer.history) == 60
    assert predictor.trainer.validation_df["game_id"].iloc[-1] == predictor.trainer.history["game_id"].iloc[-1]

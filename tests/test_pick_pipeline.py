"""Tests for the season helpers, the pick log and the recommendations script."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util

_module_path = ROOT / "scripts" / "generate_recommendations.py"
_spec = importlib.util.spec_from_file_location("generate_recommendations", _module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load generate_recommendations from {_module_path}")

gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

from src.utils.pick_log import append_pick_log, read_pick_log
from src.utils.season import current_season_id, current_season_name, to_eastern


def _espn_game(game_id, home, away, status="Scheduled", start="2026-10-08T23:00Z"):
    return {
        "game_id": game_id,
        "date": start,
        "status": status,
        "home_team": home,
        "away_team": away,
        "odds": [{
            "provider": "DraftKings",
            "moneyline": {"home": "-150", "away": "+130"},
        }],
    }


def _stats(team, goals_for, goals_against, games=30):
    return {
        "team": team,
        "games_played": games,
        "goals_for_pg": goals_for,
        "goals_against_pg": goals_against,
        "shots_for_pg": 30.0,
        "shots_against_pg": 30.0,
        "pp_pct": 0.2,
        "pk_pct": 0.8,
    }


class _FakeClient:
    GAMES = [
        _espn_game("1", "TOR", "MTL"),
        _espn_game("2", "BOS", "NYR", status="Final"),
        _espn_game("3", "UTA", "SEA"),
        _espn_game("4", "EDM", "CGY"),
        _espn_game("5", "VAN", "WPG"),
    ]
    STATS = {
        "TOR": _stats("TOR", 3.4, 2.8),
        "MTL": _stats("MTL", 2.9, 3.3),
        "UTA": _stats("ARI", 3.0, 3.0, games=82),
        "SEA": _stats("SEA", 3.0, 3.0),
        "EDM": _stats("EDM", 3.3, 3.0, games=5),
        "CGY": _stats("CGY", 2.9, 3.1),
    }

    def __init__(self, cache_ttl_minutes=60):
        pass

    def get_espn_odds(self, days_ahead=7):
        return self.GAMES

    def get_team_analytics(self, season=None):
        return {}

    def get_team_summary(self, abbrev, season=None):
        return self.STATS.get(abbrev)


def test_season_rolls_over_on_august_first():
    assert current_season_id(date(2026, 7, 31)) == "20252026"
    assert current_season_id(date(2026, 8, 1)) == "20262027"
    assert current_season_id(date(2027, 1, 15)) == "20262027"
    assert current_season_name(date(2026, 9, 29)) == "2026-27"


def test_evening_games_keep_their_eastern_date():
    start = to_eastern("2026-10-01T02:00Z")
    assert start.date().isoformat() == "2026-09-30"
    assert start.strftime("%-I:%M %p") == "10:00 PM"
    assert to_eastern("not a date") is None


def test_pick_log_is_append_only(tmp_path):
    assert append_pick_log([], tmp_path) is None
    first = append_pick_log([{"game": 1}], tmp_path)
    second = append_pick_log([{"game": 2}, {"game": 3}], tmp_path)
    assert first == second
    rows = read_pick_log(tmp_path)
    assert [row["game"] for row in rows] == [1, 2, 3]
    assert all("logged_at" in row for row in rows)


def test_shrinking_moves_the_model_toward_the_market():
    fair = gen.fair_home_probability(0.6, 0.4348)
    assert fair == pytest.approx(0.6 / 1.0348)
    assert gen.shrink_toward_market(0.70, 0.55, keep=0.5) == pytest.approx(0.625)
    assert gen.shrink_toward_market(0.70, None) == 0.70
    assert gen.fair_home_probability(None, 0.5) is None


def test_stats_rows_must_belong_to_the_team_and_have_enough_games():
    assert gen._has_enough_games({"team": "TOR", "games_played": 25}, "TOR")
    assert not gen._has_enough_games({"team": "TOR", "games_played": 5}, "TOR")
    assert not gen._has_enough_games({"team": "ARI", "games_played": 82}, "UTA")
    assert not gen._has_enough_games({}, "TOR")


def test_main_logs_every_upcoming_game_and_uses_the_early_blend_under_20_games(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "NHLClient", _FakeClient)
    monkeypatch.setattr(gen, "OUT_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(gen, "LOG_DIR", tmp_path / "pick_log")

    gen.main()
    gen.main()

    rows = read_pick_log(tmp_path / "pick_log")
    # Games 1, 3 and 4 are logged on both runs; the Final game (2) and the
    # game with no stats at all (5) are not.
    assert len(rows) == 6
    assert {r["espn_game_id"] for r in rows} == {"1", "3", "4"}

    row = rows[0]
    assert (row["home_team"], row["away_team"]) == ("TOR", "MTL")
    assert row["prior_only"] is False
    assert row["home_games_played"] == 30
    assert row["game_date"] == "2026-10-08"
    assert row["game_time"] == "7:00 PM ET"
    low, high = sorted([row["home_win_prob_raw"], row["fair_home_prob"]])
    assert low <= row["home_win_prob_used"] <= high

    # Game 3: the UTA stats row is labelled ARI, so it cannot be used and the game stays last-season only.
    last_season = [r for r in rows if r["espn_game_id"] == "3"]
    assert all(r["prior_only"] is True for r in last_season)
    assert all(r["model_source"].startswith("Prior season") for r in last_season)

    # Game 4: EDM has played 5 games and CGY 30, so the projection blends last season with this one.
    early = [r for r in rows if r["espn_game_id"] == "4"]
    assert all(r["prior_only"] is False for r in early)
    assert all(r["model_source"].startswith("Early blend") for r in early)
    assert early[0]["home_games_played"] == 5 and early[0]["away_games_played"] == 30
    assert early[0]["home_blend_weight"] == pytest.approx(0.2)
    assert early[0]["home_xg"] == early[0]["home_xg_blend"]
    assert early[0]["home_xg_prior"] is not None

    recommendations = json.loads((tmp_path / "recommendations.json").read_text())
    assert isinstance(recommendations, list)
    for rec in recommendations:
        if rec["matchup"] == "MTL @ TOR":
            continue
        assert rec["matchup"] == "CGY @ EDM"
        assert rec["notes"].startswith("Early blend") and rec["edge"] >= gen.EARLY_MIN_EDGE


def test_main_with_no_games_writes_an_empty_file_and_no_log(tmp_path, monkeypatch):
    class _EmptyClient(_FakeClient):
        GAMES = []

    monkeypatch.setattr(gen, "NHLClient", _EmptyClient)
    monkeypatch.setattr(gen, "OUT_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(gen, "LOG_DIR", tmp_path / "pick_log")

    gen.main()

    assert json.loads((tmp_path / "recommendations.json").read_text()) == []
    assert read_pick_log(tmp_path / "pick_log") == []


def _even_game(game_id, home, away):
    game = _espn_game(game_id, home, away)
    game["odds"] = [{"provider": "DraftKings", "moneyline": {"home": "-110", "away": "-110"}}]
    return game


class _EdgeClient(_FakeClient):
    GAMES = [_even_game("10", "AAA", "BBB"), _even_game("11", "CCC", "DDD"), _even_game("12", "EEE", "FFF")]
    STATS = {
        "AAA": _stats("AAA", 3.0, 3.0, games=5), "BBB": _stats("BBB", 3.0, 3.0, games=5),
        "CCC": _stats("CCC", 3.0, 3.0, games=30), "DDD": _stats("DDD", 3.0, 3.0, games=30),
        "EEE": _stats("EEE", 3.0, 3.0, games=0), "FFF": _stats("FFF", 3.0, 3.0, games=5),
    }


def test_early_games_need_a_bigger_edge_than_established_ones(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(gen, "NHLClient", _EdgeClient)
    monkeypatch.setattr(gen, "OUT_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(gen, "LOG_DIR", tmp_path / "pick_log")
    monkeypatch.setattr(
        gen, "calculate_win_probability",
        lambda home_xg, away_xg: SimpleNamespace(home_win=0.62, away_win=0.38),
    )

    gen.main()

    rows = {r["home_team"]: r for r in read_pick_log(tmp_path / "pick_log")}
    assert rows["AAA"]["prior_only"] is False and rows["AAA"]["model_source"].startswith("Early blend")
    assert rows["CCC"]["prior_only"] is False and rows["CCC"]["model_source"] == "Legacy"
    # EEE has not played this season, so it falls back to last season alone and is never recommended.
    assert rows["EEE"]["prior_only"] is True and rows["EEE"]["model_source"].startswith("Prior season")

    # The same 3.6% edge is recommended at 30 games but not at 5.
    recommendations = json.loads((tmp_path / "recommendations.json").read_text())
    assert [rec["matchup"] for rec in recommendations] == ["DDD @ CCC"]
    assert gen.MIN_EDGE <= recommendations[0]["edge"] < gen.EARLY_MIN_EDGE

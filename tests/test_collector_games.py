"""Tests for how the collector builds and de-duplicates game rows."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_gathering import DataGatherer


def _game(game_id, state="OFF", home=3, away=2, last_period="REG", schedule_state="OK"):
    home_team = {"abbrev": "BUF"}
    away_team = {"abbrev": "NJD"}
    if home is not None:
        home_team["score"] = home
        away_team["score"] = away
    return {
        "id": game_id,
        "gameType": 2,
        "startTimeUTC": "2024-10-02T23:00:00Z",
        "gameState": state,
        "gameScheduleState": schedule_state,
        "venue": {"default": "KeyBank Center"},
        "homeTeam": home_team,
        "awayTeam": away_team,
        "gameOutcome": {"lastPeriodType": last_period},
    }


def _week(next_start, days):
    return {
        "nextStartDate": next_start,
        "gameWeek": [{"date": day, "games": games} for day, games in days.items()],
    }


def test_games_use_their_own_date_and_period_type():
    schedule = _week("2024-10-08", {
        "2024-10-02": [_game(1, last_period="OT")],
        "2024-10-05": [_game(2)],
    })
    rows = {r["game_id"]: r for r in DataGatherer._games_from_schedule(schedule, "2024-25")}
    assert rows[1]["date"] == "2024-10-02"
    assert rows[2]["date"] == "2024-10-05"
    assert rows[1]["went_to_ot"] is True
    assert rows[2]["went_to_ot"] is False
    assert rows[2]["home_won"] is True


def test_unfinished_games_have_no_derived_fields():
    schedule = _week("2024-10-08", {"2024-10-02": [_game(3, state="LIVE", home=1, away=0)]})
    row = DataGatherer._games_from_schedule(schedule, "2024-25")[0]
    assert "home_won" not in row
    assert "went_to_ot" not in row


def test_upsert_never_replaces_a_final_row_with_an_unfinished_one():
    games = {}
    DataGatherer._upsert_game(games, {"game_id": 1, "date": "2024-10-02", "game_state": "OFF"})
    DataGatherer._upsert_game(games, {"game_id": 1, "date": "2024-10-02", "game_state": "FUT"})
    assert games[1]["game_state"] == "OFF"


def test_unfinished_past_games_are_detected_unless_postponed():
    unfinished = _week("2024-10-08", {"2024-10-02": [_game(4, state="FUT", home=None)]})
    postponed = _week("2024-10-08", {"2024-10-02": [_game(5, state="FUT", home=None, schedule_state="PPD")]})
    finished = _week("2024-10-08", {"2024-10-02": [_game(6)]})
    assert DataGatherer._has_unfinished_past_games(unfinished)
    assert not DataGatherer._has_unfinished_past_games(postponed)
    assert not DataGatherer._has_unfinished_past_games(finished)


def test_stale_cached_week_is_refetched(tmp_path):
    stale = _week("2024-10-08", {"2024-10-02": [_game(1, state="FUT", home=None)]})
    fresh = _week("2024-10-08", {"2024-10-02": [_game(1)]})
    calls = []

    def fake_fetch(url, cache_key=None, refresh=False):
        calls.append(refresh)
        return fresh if refresh else stale

    gatherer = object.__new__(DataGatherer)
    gatherer._fetch = fake_fetch
    gatherer._get_season_dates = lambda season_name: (date(2024, 10, 1), date(2024, 10, 7))
    gatherer._gather_season_games("2024-25", "20242025", tmp_path)

    saved = json.loads((tmp_path / "games.json").read_text())
    assert calls == [False, True]
    assert saved[0]["game_state"] == "OFF"
    assert saved[0]["home_won"] is True


def test_season_gather_collapses_legacy_duplicates_and_is_repeatable(tmp_path):
    windows = {
        "2024-10-01": _week("2024-10-08", {
            "2024-10-02": [_game(1, last_period="OT")],
            "2024-10-05": [_game(2)],
        }),
        "2024-10-08": _week("2024-10-15", {"2024-10-09": [_game(3)]}),
    }
    legacy = [
        {"game_id": 1, "date": "2024-09-26", "game_state": "OFF", "home_score": 3, "away_score": 2},
        {"game_id": 1, "date": "2024-09-27", "game_state": "OFF", "home_score": 3, "away_score": 2},
    ]
    (tmp_path / "games.json").write_text(json.dumps(legacy))

    calls = []

    def fake_fetch(url, cache_key=None, refresh=False):
        day = url.rsplit("/", 1)[-1]
        calls.append(day)
        return windows.get(day, {})

    gatherer = object.__new__(DataGatherer)
    gatherer._fetch = fake_fetch
    gatherer._get_season_dates = lambda season_name: (date(2024, 10, 1), date(2024, 10, 14))

    gatherer._gather_season_games("2024-25", "20242025", tmp_path)
    saved = json.loads((tmp_path / "games.json").read_text())
    assert [g["game_id"] for g in saved] == [1, 2, 3]
    assert [g["date"] for g in saved] == ["2024-10-02", "2024-10-05", "2024-10-09"]
    assert calls == ["2024-10-01", "2024-10-08"]

    gatherer._gather_season_games("2024-25", "20242025", tmp_path)
    again = json.loads((tmp_path / "games.json").read_text())
    assert again == saved

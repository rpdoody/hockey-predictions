from datetime import date

from src.utils.rest_days import rest_fields, schedule_dates, team_game_dates


def _schedule(*days, game_type=2):
    return {"games": [{"gameDate": d, "gameType": game_type} for d in days]}


def test_schedule_dates_are_sorted_and_skip_preseason():
    data = {"games": [
        {"gameDate": "2026-11-05", "gameType": 2},
        {"gameDate": "2026-10-01", "gameType": 1},
        {"gameDate": "2026-11-03", "gameType": 2},
        {"gameDate": "2026-11-03", "gameType": 2},
        {"gameDate": "not a date", "gameType": 2},
    ]}
    assert schedule_dates(data) == [date(2026, 11, 3), date(2026, 11, 5)]


def test_schedule_dates_tolerate_bad_input():
    assert schedule_dates(None) == []
    assert schedule_dates({}) == []
    assert schedule_dates({"games": "nope"}) == []


def test_back_to_back_has_one_day_of_rest():
    dates = schedule_dates(_schedule("2026-11-09", "2026-11-10"))
    fields = rest_fields("2026-11-10", dates, "home")
    assert fields["home_rest_days"] == 1
    assert fields["home_back_to_back"] is True


def test_long_rest_is_not_back_to_back():
    dates = schedule_dates(_schedule("2026-11-01", "2026-11-06"))
    fields = rest_fields("2026-11-06", dates, "away")
    assert fields["away_rest_days"] == 5
    assert fields["away_back_to_back"] is False


def test_games_last_7_counts_only_earlier_games_in_window():
    dates = schedule_dates(_schedule("2026-11-01", "2026-11-04", "2026-11-06", "2026-11-08", "2026-11-12"))
    fields = rest_fields("2026-11-08", dates, "home")
    assert fields["home_games_last_7"] == 3
    assert fields["home_rest_days"] == 2


def test_first_game_of_the_season_has_no_rest_value():
    dates = schedule_dates(_schedule("2026-10-08", "2026-10-10"))
    fields = rest_fields("2026-10-08", dates, "home")
    assert fields["home_rest_days"] is None
    assert fields["home_back_to_back"] is None
    assert fields["home_games_last_7"] == 0


def test_missing_schedule_or_bad_date_gives_all_none():
    for fields in (rest_fields("2026-11-08", [], "home"), rest_fields("bad", [date(2026, 11, 1)], "home")):
        assert set(fields.values()) == {None}


def test_team_game_dates_survive_client_errors_and_cache():
    class Boom:
        calls = 0

        def get_team_schedule(self, team, season=None):
            Boom.calls += 1
            raise ConnectionError("down")

    cache = {}
    assert team_game_dates(Boom(), "TOR", "20262027", cache) == []
    assert team_game_dates(Boom(), "TOR", "20262027", cache) == []
    assert Boom.calls == 1

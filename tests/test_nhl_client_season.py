"""Tests for how NHLClient picks its default season."""
import pytest

from src.api.nhl_client import NHLClient


def _client(monkeypatch, tmp_path, rows):
    monkeypatch.setattr(NHLClient, "CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.api.nhl_client.current_season_id", lambda: "20262027")
    client = NHLClient()
    urls = []

    def fake_fetch(url, ttl=None):
        urls.append(url)
        return {"data": rows}

    client._fetch_sync = fake_fetch
    return client, urls


def test_display_season_is_the_current_season_once_it_has_games(monkeypatch, tmp_path):
    client, urls = _client(monkeypatch, tmp_path, [{"teamId": 10, "gamesPlayed": 3}])
    assert client.display_season() == "20262027"
    assert "seasonId=20262027" in urls[0]


@pytest.mark.parametrize("rows", [[], [{"teamId": 10, "gamesPlayed": 0}]])
def test_display_season_falls_back_to_the_previous_season_without_games(monkeypatch, tmp_path, rows):
    client, _ = _client(monkeypatch, tmp_path, rows)
    assert client.display_season() == "20252026"


def test_display_season_is_remembered(monkeypatch, tmp_path):
    client, urls = _client(monkeypatch, tmp_path, [{"teamId": 10, "gamesPlayed": 3}])
    client.display_season()
    client.display_season()
    assert len(urls) == 1


def test_stats_methods_default_to_the_display_season(monkeypatch, tmp_path):
    client, urls = _client(monkeypatch, tmp_path, [{"teamId": 10, "gamesPlayed": 3}])
    client.get_team_stats()
    assert "seasonId=20262027" in urls[-1]


def test_explicit_seasons_are_left_alone(monkeypatch, tmp_path):
    client, urls = _client(monkeypatch, tmp_path, [])
    client.get_team_stats(season="20232024")
    assert len(urls) == 1
    assert "seasonId=20232024" in urls[0]

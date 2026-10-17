import pytest

from src.api.nhl_client import NHLClient


def _client_with_urls():
    client = NHLClient()
    urls = []
    client._fetch_sync = lambda url, ttl=None: urls.append(url) or {"data": []}
    return client, urls


def test_skater_stats_sort_by_the_requested_stat():
    client, urls = _client_with_urls()
    client.get_skater_stats(season="20262027", limit=5, sort="shots")
    assert "sort=shots&direction=DESC" in urls[0] and "limit=5" in urls[0]


def test_skater_stats_still_default_to_points():
    client, urls = _client_with_urls()
    client.get_skater_stats(season="20262027")
    assert "sort=points&direction=DESC" in urls[0]


def test_goalie_stats_sort_by_saves_and_default_to_wins():
    client, urls = _client_with_urls()
    client.get_goalie_stats(season="20262027", sort="saves")
    client.get_goalie_stats(season="20262027")
    assert "sort=saves&direction=DESC" in urls[0] and "sort=wins&direction=DESC" in urls[1]


def test_unsupported_sorts_are_rejected_before_any_request():
    client, urls = _client_with_urls()
    with pytest.raises(ValueError):
        client.get_skater_stats(season="20262027", sort="points&limit=9")
    with pytest.raises(ValueError):
        client.get_goalie_stats(season="20262027", sort="bogus")
    assert urls == []

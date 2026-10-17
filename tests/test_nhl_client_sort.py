import pytest

from urllib.parse import quote

from src.api.nhl_client import NHLClient


def _sort(prop):
    return "sort=" + quote('[{"property":"%s","direction":"DESC"}]' % prop)


def _client_with_urls():
    client = NHLClient()
    urls = []
    client._fetch_sync = lambda url, ttl=None: urls.append(url) or {"data": []}
    return client, urls


def test_skater_stats_sort_by_the_requested_stat():
    client, urls = _client_with_urls()
    client.get_skater_stats(season="20262027", limit=5, sort="shots")
    assert _sort("shots") in urls[0] and "limit=5" in urls[0]


def test_skater_stats_still_default_to_points():
    client, urls = _client_with_urls()
    client.get_skater_stats(season="20262027")
    assert _sort("points") in urls[0]


def test_goalie_stats_sort_by_saves_and_default_to_wins():
    client, urls = _client_with_urls()
    client.get_goalie_stats(season="20262027", sort="saves")
    client.get_goalie_stats(season="20262027")
    assert _sort("saves") in urls[0] and _sort("wins") in urls[1]


def test_unsupported_sorts_are_rejected_before_any_request():
    client, urls = _client_with_urls()
    with pytest.raises(ValueError):
        client.get_skater_stats(season="20262027", sort="points&limit=9")
    with pytest.raises(ValueError):
        client.get_goalie_stats(season="20262027", sort="bogus")
    assert urls == []


def test_plain_direction_sorting_is_never_used():
    client, urls = _client_with_urls()
    client.get_skater_stats(season="20262027")
    client.get_goalie_stats(season="20262027")
    client.get_skater_analytics(season="20262027")
    client.get_goalie_analytics(season="20262027")
    assert len(urls) == 4 and all("direction=DESC" not in url for url in urls)


def test_urls_that_differ_only_in_limit_get_different_cache_files():
    client = NHLClient()
    base = (
        "https://api.nhle.com/stats/rest/en/skater/summary?limit={}&cayenneExp=seasonId=20262027&sort="
        + NHLClient._sort_param("goals")
    )
    assert client._get_cache_path(base.format(50)) != client._get_cache_path(base.format(1000))

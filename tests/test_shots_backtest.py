import random
from datetime import timedelta

import pytest

from src.utils.shots_backtest import (
    DEFAULT_SETTING, build_players, format_report, load_game_rows, position_baselines, previous_season_id, run_backtest,
)


def _log(rng, games, rate, minutes, start_month):
    rows = []
    for g in range(games):
        m = max(8.0, rng.gauss(minutes, 1.5))
        mean = rate * m
        rows.append({
            'gameDate': f'2026-{start_month + g // 28:02d}-{g % 28 + 1:02d}',
            'shots': max(0, int(round(rng.gauss(mean, mean ** 0.5)))),
            'toi': f'{int(m)}:{int((m % 1) * 60):02d}', 'opponentAbbrev': 'BOS', 'homeRoadFlag': 'H' if g % 2 else 'R',
        })
    return rows


class FakeClient:
    def __init__(self, n=40, fail_ids=()):
        rng = random.Random(3)
        self.fail_ids = set(fail_ids)
        self.logs = {}
        self.skaters = []
        for pid in range(n):
            rate, minutes = rng.uniform(0.06, 0.2), rng.uniform(14, 22)
            self.logs[(pid, '20252026')] = _log(rng, 70, rate, minutes, 1)
            self.logs[(pid, '20262027')] = _log(rng, 0 if pid == n - 1 else 15, rate, minutes, 10)
            self.skaters.append({'player_id': pid, 'name': f'P{pid}', 'position': 'D' if pid % 3 == 0 else 'C',
                                 'games': 70, 'shots': 200 - pid, 'toi_pg': minutes * 60})
        self.urls = []

    def get_skater_stats(self, season=None, limit=100, sort='points'):
        assert season == '20252026' and sort == 'shots'
        return self.skaters if limit < 0 else self.skaters[:limit]

    def _fetch_sync(self, url, ttl=None):
        self.urls.append((url, ttl))
        pid = int(url.split('/player/')[1].split('/')[0])
        if pid in self.fail_ids:
            raise ConnectionError('boom')
        season = url.split('game-log/')[1].split('/')[0]
        return {'gameLog': list(reversed(self.logs[(pid, season)]))}


def test_previous_season_id():
    assert previous_season_id('20262027') == '20252026'


def test_position_baselines_use_shots_per_minute_by_group():
    skaters = [
        {'position': 'C', 'games': 10, 'shots': 30, 'toi_pg': 1200},
        {'position': 'D', 'games': 10, 'shots': 10, 'toi_pg': 1200},
        {'position': 'C', 'games': 0, 'shots': 99, 'toi_pg': 1200},
    ]
    result = position_baselines(skaters)
    assert result['F'] == pytest.approx(30 / 200) and result['D'] == pytest.approx(10 / 200)


def test_load_game_rows_uses_the_documented_game_log_url_and_ttl():
    client = FakeClient(n=2)
    rows = load_game_rows(client, 0, '20262027', timedelta(hours=6))
    assert len(rows) == 15 and rows[0]['date'] <= rows[-1]['date']
    url, ttl = client.urls[0]
    assert url == 'https://api-web.nhle.com/v1/player/0/game-log/20262027/2' and ttl == timedelta(hours=6)


def test_build_players_skips_failures_and_players_without_current_games():
    client = FakeClient(n=10, fail_ids=[2])
    players, skipped = build_players(client, '20262027', '20252026', limit=10, pause=0)
    assert len(players) == 8 and skipped == 2
    assert all(p['baseline_rate'] and p['prior_rows'] and p['rows'] for p in players)


def test_backtest_picks_settings_early_and_scores_on_later_games_only():
    client = FakeClient(n=40)
    players, _ = build_players(client, '20262027', '20252026', limit=40, pause=0)
    report = run_backtest(players, prior_grid=(100, 600), shrink_grid=(0, 500))
    assert report['players'] == 39
    assert report['best'] in report['selection'] and DEFAULT_SETTING in report['selection']
    sizes = {name: e['n'] for name, e in report['comparison'].items()}
    assert len(set(sizes.values())) == 1 and sizes['model (best setting)'] == report['holdout_games'] > 0
    assert report['gap_vs_last_season']['n'] == report['holdout_games']
    assert report['gap_vs_default']['n'] == report['holdout_games']
    text = format_report(report)
    assert 'holdout' in text and 'paired' in text and 'best setting' in text and 'line 2.5' in text


def test_backtest_default_comparison_is_identical_when_the_best_setting_is_the_default():
    client = FakeClient(n=20)
    players, _ = build_players(client, '20262027', '20252026', limit=20, pause=0)
    report = run_backtest(players, prior_grid=(300,), shrink_grid=(0,))
    assert report['best'] == DEFAULT_SETTING
    assert report['gap_vs_default']['mean'] == pytest.approx(0.0)

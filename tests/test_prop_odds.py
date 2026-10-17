import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.utils import prop_odds
from src.utils.prop_odds import (
    append_rows, capture, captured_keys, events_in_window, parse_shot_lines,
)

NOW = datetime(2026, 10, 17, 19, 0, tzinfo=timezone.utc)


def _event(event_id, hours_ahead, home='BOS', away='PHI'):
    start = NOW.timestamp() + hours_ahead * 3600
    return {
        'id': event_id, 'home_team': home, 'away_team': away,
        'commence_time': datetime.fromtimestamp(start, timezone.utc).isoformat().replace('+00:00', 'Z'),
    }


def _outcomes(player, point, over, under):
    return [
        {'name': 'Over', 'description': player, 'price': over, 'point': point},
        {'name': 'Under', 'description': player, 'price': under, 'point': point},
    ]


def _odds_payload(event, with_lines=True):
    books = []
    if with_lines:
        books = [
            {'key': 'draftkings', 'markets': [{'key': 'player_shots_on_goal', 'last_update': 't1',
                'outcomes': _outcomes('Brad Marchand', 3.5, -120, 100) + _outcomes('Sean Couturier', 2.5, 110, -135)}]},
            {'key': 'fanduel', 'markets': [{'key': 'player_shots_on_goal', 'last_update': 't2',
                'outcomes': _outcomes('Brad Marchand', 3.5, -115, -105)}]},
            {'key': 'betmgm', 'markets': [{'key': 'player_shots_on_goal', 'outcomes': _outcomes('Ignored Guy', 1.5, 100, -120)}]},
            {'key': 'draftkings', 'markets': [{'key': 'player_points', 'outcomes': _outcomes('Not Shots', 0.5, 100, -120)}]},
        ]
    return dict(event, bookmakers=books)


class FakeApi:
    def __init__(self, events, remaining=100, with_lines=True, cost=1):
        self.events, self.remaining, self.with_lines, self.cost = events, remaining, with_lines, cost
        self.paid_calls = 0

    def __call__(self, url, params=None, timeout=None):
        if url.endswith('/events'):
            return SimpleNamespace(json=lambda: self.events, headers={'x-requests-remaining': str(self.remaining)},
                                   raise_for_status=lambda: None)
        event_id = url.split('/events/')[1].split('/')[0]
        event = next(e for e in self.events if e['id'] == event_id)
        assert params['bookmakers'] == 'draftkings,fanduel' and params['markets'] == 'player_shots_on_goal'
        self.paid_calls += 1
        self.remaining -= self.cost
        headers = {'x-requests-remaining': str(self.remaining), 'x-requests-last': str(self.cost)}
        return SimpleNamespace(json=lambda: _odds_payload(event, self.with_lines), headers=headers,
                               raise_for_status=lambda: None)


def test_parse_keeps_only_shots_from_our_books_with_both_sides():
    rows = parse_shot_lines(_odds_payload(_event('e1', 3)), 'ts', 'open')
    assert {(r['book'], r['player']) for r in rows} == {
        ('draftkings', 'Brad Marchand'), ('draftkings', 'Sean Couturier'), ('fanduel', 'Brad Marchand')}
    dk = next(r for r in rows if r['book'] == 'draftkings' and r['player'] == 'Brad Marchand')
    assert (dk['line'], dk['over_price'], dk['under_price'], dk['label']) == (3.5, -120, 100, 'open')
    assert dk['market_last_update'] == 't1'


def test_parse_handles_a_missing_side_and_empty_events():
    event = {'id': 'e1', 'bookmakers': [{'key': 'fanduel', 'markets': [{'key': 'player_shots_on_goal', 'outcomes': [
        {'name': 'Over', 'description': 'A Player', 'price': -110, 'point': 2.5}]}]}]}
    rows = parse_shot_lines(event, 'ts', 'open')
    assert rows[0]['over_price'] == -110 and rows[0]['under_price'] is None
    assert parse_shot_lines({'id': 'e2', 'bookmakers': []}, 'ts', 'open') == []


def test_window_keeps_games_in_range_soonest_first():
    events = [_event('late', 9), _event('soon', 2), _event('mid', 5), _event('started', -1)]
    assert [e['id'] for e in events_in_window(events, NOW, 0, 8)] == ['soon', 'mid']
    assert [e['id'] for e in events_in_window(events, NOW, 3, 10)] == ['mid', 'late']


def test_capture_saves_rows_counts_credits_and_never_repeats_a_game(tmp_path):
    odds, quota = tmp_path / 'odds.jsonl', tmp_path / 'quota.json'
    api = FakeApi([_event('e1', 2), _event('e2', 4), _event('e3', 20)])
    first = capture('k', NOW, 0, 8, 'open', odds_path=odds, quota_path=quota, http_get=api)
    assert (first['in_window'], first['captured'], first['credits_used'], first['credits_remaining']) == (2, 2, 2, 98)
    assert captured_keys(odds) == {('e1', 'open'), ('e2', 'open')}
    assert json.loads(quota.read_text())['remaining'] == 98
    second = capture('k', NOW, 0, 8, 'open', odds_path=odds, quota_path=quota, http_get=api)
    assert second['already_captured'] == 2 and second['captured'] == 0 and api.paid_calls == 2
    closing = capture('k', NOW, 0, 8, 'close', odds_path=odds, quota_path=quota, http_get=api)
    assert closing['captured'] == 2 and api.paid_calls == 4


def test_capture_stops_at_the_credit_reserve(tmp_path):
    api = FakeApi([_event(f'e{i}', 1 + i * 0.1) for i in range(6)], remaining=27)
    result = capture('k', NOW, 0, 8, 'open', reserve=25, odds_path=tmp_path / 'o.jsonl',
                     quota_path=tmp_path / 'q.json', http_get=api)
    assert api.paid_calls == 2 and result['captured'] == 2
    assert result['stopped'] == 'credit reserve of 25 reached'


def test_games_without_lines_yet_are_not_marked_captured(tmp_path):
    odds = tmp_path / 'o.jsonl'
    api = FakeApi([_event('e1', 2)], with_lines=False, cost=0)
    result = capture('k', NOW, 0, 8, 'open', odds_path=odds, quota_path=tmp_path / 'q.json', http_get=api)
    assert result['no_lines_yet'] == 1 and result['captured'] == 0 and result['credits_used'] == 0
    assert captured_keys(odds) == set()


def test_max_events_caps_one_run_and_dry_run_spends_nothing(tmp_path):
    api = FakeApi([_event(f'e{i}', 1 + i * 0.1) for i in range(5)])
    kw = dict(odds_path=tmp_path / 'o.jsonl', quota_path=tmp_path / 'q.json', http_get=api)
    dry = capture('k', NOW, 0, 8, 'open', max_events=3, dry_run=True, **kw)
    assert len(dry['would_fetch']) == 3 and dry['over_max_events'] == 2 and api.paid_calls == 0
    live = capture('k', NOW, 0, 8, 'open', max_events=3, **kw)
    assert live['captured'] == 3 and api.paid_calls == 3


def test_append_and_read_back_jsonl(tmp_path):
    path = tmp_path / 'deep' / 'rows.jsonl'
    append_rows(path, [{'event_id': 'a', 'label': 'open'}])
    append_rows(path, [{'event_id': 'b', 'label': 'close'}])
    assert captured_keys(path) == {('a', 'open'), ('b', 'close')}

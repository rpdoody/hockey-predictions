'''Tests for ESPN odds parsing and odds snapshot storage.'''
import json

import pytest

from auto_capture_odds import build_snapshot, select_provider
from src.utils import odds_storage
from src.utils.odds_parse import parse_line, parse_price, to_nhl_abbrev


def _game():
    return {
        'game_id': '401',
        'date': '2026-09-29T23:00Z',
        'home_team': 'LA',
        'away_team': 'NJ',
        'odds': [{
            'provider': 'DraftKings',
            'moneyline': {'home': '-150', 'away': '+130'},
            'spread': {
                'home': {'line': '-1.5', 'odds': '+180'},
                'away': {'line': '+1.5', 'odds': '-220'},
            },
            'total': {
                'over': {'line': 'o6.5', 'odds': '-115'},
                'under': {'line': 'u6.5', 'odds': '-105'},
            },
        }],
    }


@pytest.mark.parametrize('raw, expected', [
    ('o6.5', 6.5), ('u5.5', 5.5), ('-1.5', -1.5), (6.5, 6.5), (6, 6.0),
    ('', None), ('abc', None), (None, None),
])
def test_parse_line(raw, expected):
    assert parse_line(raw) == expected


@pytest.mark.parametrize('raw, expected', [
    ('-110', -110), ('+150', 150), (150, 150), (-120.0, -120), ('EVEN', 100),
    ('', None), ('abc', None), (None, None), (0, None),
])
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


@pytest.mark.parametrize('raw, expected', [
    ('LA', 'LAK'), ('NJ', 'NJD'), ('SJ', 'SJS'), ('TB', 'TBL'), ('UTAH', 'UTA'),
    ('TOR', 'TOR'), (None, None),
])
def test_to_nhl_abbrev(raw, expected):
    assert to_nhl_abbrev(raw) == expected


def test_build_snapshot_parses_espn_strings():
    snap = build_snapshot(_game())
    assert snap['home_team'] == 'LAK'
    assert snap['away_team'] == 'NJD'
    assert (snap['home_ml'], snap['away_ml']) == (-150, 130)
    assert snap['total'] == 6.5
    assert (snap['over_odds'], snap['under_odds']) == (-115, -105)
    assert (snap['home_pl_odds'], snap['away_pl_odds']) == (180, -220)
    assert snap['start_time'] == '2026-09-29T23:00Z'
    assert snap['provider'] == 'DraftKings'


def test_missing_markets_are_null_not_defaults():
    game = _game()
    del game['odds'][0]['total']
    del game['odds'][0]['spread']
    snap = build_snapshot(game)
    assert snap['total'] is None
    assert snap['over_odds'] is None and snap['under_odds'] is None
    assert snap['home_pl_odds'] is None and snap['away_pl_odds'] is None


def test_no_moneyline_or_no_odds_gives_none():
    game = _game()
    game['odds'][0]['moneyline'] = {'home': None, 'away': None}
    assert build_snapshot(game) is None
    game['odds'] = []
    assert build_snapshot(game) is None


def test_select_provider_prefers_draftkings():
    picked = select_provider([{'provider': 'Other'}, {'provider': 'DraftKings'}])
    assert picked['provider'] == 'DraftKings'
    assert select_provider([]) is None


def _save(**kwargs):
    args = dict(
        game_id='1', home_team='TOR', away_team='MTL', home_ml=-150, away_ml=130,
        total=None, over_odds=None, under_odds=None,
    )
    args.update(kwargs)
    return odds_storage.save_odds_snapshot(**args)


def test_storage_skips_unchanged_stores_nulls_and_utc(monkeypatch, tmp_path):
    monkeypatch.setattr(odds_storage, 'ODDS_DIR', tmp_path)
    assert _save() is True
    assert _save() is False
    assert _save(home_ml=-160) is True
    data = json.loads((tmp_path / '1.json').read_text())
    assert len(data['snapshots']) == 2
    first = data['snapshots'][0]
    assert first['total'] is None and first['home_pl_odds'] is None
    assert first['timestamp'].endswith('+00:00')


def test_movements_tolerate_missing_totals(monkeypatch, tmp_path):
    monkeypatch.setattr(odds_storage, 'ODDS_DIR', tmp_path)
    _save()
    _save(home_ml=-175)
    moves = odds_storage.get_todays_movements()
    assert len(moves) == 1
    assert moves[0]['ml_move'] == -25
    assert moves[0]['total_move'] == 0.0

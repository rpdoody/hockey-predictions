'''Tests for preliminary model-vs-market rows.'''
import pytest

from src.utils.preliminary import display_rows, preliminary_rows


def _row(game_id, logged_at, used, start='2026-10-08T23:00Z', date='2026-10-08', **extra):
    row = {
        'espn_game_id': game_id, 'game_date': date, 'logged_at': logged_at,
        'start_utc': start, 'game_time': '7:00 PM ET',
        'home_team': 'TOR', 'away_team': 'MTL',
        'home_ml': '-110', 'away_ml': '-110',
        'home_win_prob_raw': 0.6, 'home_win_prob_used': used,
        'model_source': 'Prior season (20252026)',
    }
    row.update(extra)
    return row


def test_uses_latest_record_per_game_on_the_date():
    rows = [
        _row('A', '2026-10-07T07:00:00+00:00', 0.55),
        _row('A', '2026-10-08T07:00:00+00:00', 0.53),
        _row('B', '2026-10-08T07:00:00+00:00', 0.50, date='2026-10-09'),
    ]
    out = preliminary_rows(rows, '2026-10-08')
    assert len(out) == 1
    assert out[0]['model_used_home'] == 0.53
    assert out[0]['market_home'] == pytest.approx(0.5)
    assert out[0]['gap'] == pytest.approx(0.03)


def test_rows_are_ordered_by_start_time():
    rows = [
        _row('LATE', '2026-10-08T07:00:00+00:00', 0.5, start='2026-10-09T02:00Z', away_team='VAN'),
        _row('EARLY', '2026-10-08T07:00:00+00:00', 0.5, start='2026-10-08T23:00Z'),
    ]
    out = preliminary_rows(rows, '2026-10-08')
    assert [r['matchup'] for r in out] == ['MTL @ TOR', 'VAN @ TOR']


def test_display_rows_format_and_handle_missing_odds():
    rows = [
        _row('A', '2026-10-08T07:00:00+00:00', 0.53),
        _row('B', '2026-10-08T07:00:00+00:00', 0.53, home_ml=None, away_ml=None),
    ]
    table = display_rows(preliminary_rows(rows, '2026-10-08'))
    assert table[0]['Model home win % (blended)'] == '53.0%'
    assert table[0]['Gap vs market'] == '+3.0 pts'
    assert table[1]['Market home win %'] == 'n/a'
    assert table[1]['Gap vs market'] == 'n/a'

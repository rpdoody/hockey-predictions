'''Tests for pick scoring.'''
import pytest

from src.utils import scoring
from src.utils.scoring import (
    american_to_prob, bet_profit, closing_prices, fair_home_prob, format_report,
    lookup_result, parse_schedule, score, select_records,
)


def test_prices_and_profit():
    assert american_to_prob('-150') == pytest.approx(0.6)
    assert american_to_prob('+150') == pytest.approx(0.4)
    assert american_to_prob(None) is None
    assert fair_home_prob(-110, -110) == pytest.approx(0.5)
    assert bet_profit('+150', True) == pytest.approx(1.5)
    assert bet_profit('-150', True) == pytest.approx(100 / 150)
    assert bet_profit('-150', False) == -1.0


def test_parse_schedule_keeps_only_finished_games():
    payload = {'gameWeek': [{'date': '2026-10-08', 'games': [
        {'gameState': 'OFF', 'homeTeam': {'abbrev': 'TOR', 'score': 4}, 'awayTeam': {'abbrev': 'MTL', 'score': 2}},
        {'gameState': 'FINAL', 'homeTeam': {'abbrev': 'BOS', 'score': 1}, 'awayTeam': {'abbrev': 'NYR', 'score': 3}},
        {'gameState': 'FUT', 'homeTeam': {'abbrev': 'EDM'}, 'awayTeam': {'abbrev': 'VAN'}},
        {'gameState': 'LIVE', 'homeTeam': {'abbrev': 'DAL', 'score': 1}, 'awayTeam': {'abbrev': 'STL', 'score': 0}},
    ]}]}
    results = parse_schedule(payload)
    assert results == {
        '2026-10-08|TOR|MTL': {'home_goals': 4, 'away_goals': 2},
        '2026-10-08|BOS|NYR': {'home_goals': 1, 'away_goals': 3},
    }


def test_lookup_result_tolerates_one_day_offset():
    results = {'2026-10-09|TOR|MTL': {'home_goals': 1, 'away_goals': 0}}
    assert lookup_result(results, '2026-10-08', 'TOR', 'MTL') is not None
    assert lookup_result(results, '2026-10-07', 'TOR', 'MTL') is None
    assert lookup_result(results, '2026-10-08', 'MTL', 'TOR') is None


def _row(logged_at, **extra):
    row = {
        'espn_game_id': 'X', 'start_utc': '2026-10-08T23:00Z',
        'logged_at': logged_at,
    }
    row.update(extra)
    return row


def test_select_records_uses_pre_game_records_only():
    rows = [
        _row('2026-10-07T12:00:00+00:00', tag='early'),
        _row('2026-10-08T12:00:00+00:00', tag='late'),
        _row('2026-10-08T23:30:00+00:00', tag='after start'),
    ]
    assert select_records(rows, 'last')[0]['tag'] == 'late'
    assert select_records(rows, 'first')[0]['tag'] == 'early'
    assert select_records([rows[2]]) == []


def test_closing_prices_uses_last_snapshot_before_start():
    history = {'snapshots': [
        {'timestamp': '2026-10-08T10:00:00+00:00', 'home_ml': -110, 'away_ml': -110},
        {'timestamp': '2026-10-08T20:00:00+00:00', 'home_ml': -130, 'away_ml': 110},
        {'timestamp': '2026-10-08T23:10:00+00:00', 'home_ml': -500, 'away_ml': 400},
    ]}
    assert closing_prices(history, '2026-10-08T23:00Z') == (-130, 110)
    assert closing_prices(None, '2026-10-08T23:00Z') is None


def _log(game_id, date, home, away, home_ml, away_ml, raw, used):
    return {
        'espn_game_id': game_id, 'game_date': date,
        'start_utc': date + 'T23:00Z', 'logged_at': date + 'T12:00:00+00:00',
        'home_team': home, 'away_team': away,
        'home_games_played': 5, 'away_games_played': 5,
        'home_win_prob_raw': raw, 'home_win_prob_used': used,
        'home_ml': home_ml, 'away_ml': away_ml,
    }


def test_score_end_to_end():
    rows = [
        _log('A', '2026-10-08', 'TOR', 'MTL', '-110', '-110', 0.62, 0.60),
        _log('B', '2026-10-08', 'BOS', 'NYR', '-200', '+170', 0.52, 0.50),
        _log('C', '2026-10-09', 'TOR', 'MTL', '-110', '-110', 0.55, 0.55),
    ]
    results = {
        '2026-10-08|TOR|MTL': {'home_goals': 4, 'away_goals': 2},
        '2026-10-08|BOS|NYR': {'home_goals': 3, 'away_goals': 1},
    }
    histories = {'A': {'snapshots': [
        {'timestamp': '2026-10-08T20:00:00+00:00', 'home_ml': -130, 'away_ml': 110},
    ]}}
    report = score(rows, results, histories.get)

    assert report['games_logged'] == 3
    assert report['games_scored'] == 2
    assert report['games_pending'] == 1
    bets = report['overall']['bets']
    assert bets['n'] == 2 and bets['wins'] == 1
    assert bets['units'] == pytest.approx(100 / 110 - 1, abs=0.01)
    assert bets['clv_n'] == 1
    assert bets['avg_clv'] == pytest.approx(0.0427, abs=0.002)
    assert report['overall']['probabilities']['n'] == 2
    assert report['overall']['probabilities']['p_market'] is not None
    assert 'early' in report['by_segment']
    text = format_report(report)
    assert 'ROI' in text and 'waiting on results: 1' in text


def test_score_with_no_results_is_empty():
    rows = [_log('A', '2026-10-08', 'TOR', 'MTL', '-110', '-110', 0.6, 0.6)]
    report = score(rows, {}, {}.get)
    assert report['games_scored'] == 0 and report['games_pending'] == 1
    assert report['overall']['bets'] == {'n': 0}
    assert scoring.format_report(report)

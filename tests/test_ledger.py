import pytest

from src.utils.performance import (
    daily_summary, ledger_totals, money, parse_american, pick_ledger, picks_for_date, win_profit,
)

DAY = '2026-09-29'
NEXT = '2026-09-30'


def _entry(home='TOR', away='MTL', p_home=0.6, day=DAY, **extra):
    row = {
        'logged_at': day + 'T20:00:00+00:00', 'game_date': day, 'game_time': '7:00 PM ET',
        'start_utc': day + 'T23:00Z', 'home_team': home, 'away_team': away,
        'prior_only': True, 'home_win_prob_used': p_home, 'fair_home_prob': 0.5,
    }
    row.update(extra)
    return row


def test_parse_american():
    assert parse_american('-115') == -115
    assert parse_american('+245') == 245
    assert parse_american('EVEN') == 100
    assert parse_american(None) is None
    assert parse_american('abc') is None
    assert parse_american('0') is None


def test_win_profit():
    assert win_profit(150) == 15
    assert win_profit(-200) == 5
    assert win_profit(-110) == pytest.approx(9.0909, abs=1e-3)


def test_money():
    assert money(8.333) == '+$8.33'
    assert money(-10) == '-$10.00'
    assert money(1234.5) == '+$1,234.50'


def test_ledger_scores_flat_stake_and_running_total():
    entries = [
        _entry(home_ml='-120', away_ml='+100'),
        _entry(home='BOS', away='NYR', p_home=0.4, home_ml='-170', away_ml='+150'),
    ]
    scores = {
        DAY + '|TOR|MTL': {'away_goals': 1, 'home_goals': 2},
        DAY + '|BOS|NYR': {'away_goals': 1, 'home_goals': 2},
    }
    ledger = pick_ledger(entries, scores)
    assert [r['pick'] for r in ledger] == ['TOR', 'NYR']
    assert ledger[0]['profit'] == pytest.approx(8.3333, abs=1e-3)
    assert ledger[1]['profit'] == -10 and ledger[1]['odds'] == 150
    assert ledger[1]['running_total'] == pytest.approx(-1.6667, abs=1e-3)


def test_ledger_skips_ungraded_and_handles_missing_odds():
    entries = [_entry(), _entry(home='BOS', away='NYR', home_ml='-120', away_ml='+100')]
    scores = {DAY + '|TOR|MTL': {'away_goals': 1, 'home_goals': 2}}
    ledger = pick_ledger(entries, scores)
    assert len(ledger) == 1 and ledger[0]['profit'] is None and ledger[0]['running_total'] == 0
    totals = ledger_totals(ledger)
    assert (totals['wins'], totals['losses'], totals['unpriced'], totals['roi']) == (1, 0, 1, None)


def test_daily_summary_and_totals():
    entries = [
        _entry(home_ml='-120', away_ml='+100'),
        _entry(home='BOS', away='NYR', day=NEXT, home_ml='+100', away_ml='-120'),
    ]
    scores = {
        DAY + '|TOR|MTL': {'away_goals': 1, 'home_goals': 2},
        NEXT + '|BOS|NYR': {'away_goals': 2, 'home_goals': 1},
    }
    ledger = pick_ledger(entries, scores)
    days = daily_summary(ledger)
    assert [d['Date'] for d in days] == [DAY, NEXT]
    assert (days[0]['Wins'], days[0]['Losses']) == (1, 0)
    assert days[0]['Running total'] == pytest.approx(8.3333, abs=1e-3)
    assert (days[1]['Wins'], days[1]['Losses']) == (0, 1)
    assert days[1]['Running total'] == pytest.approx(-1.6667, abs=1e-3)
    totals = ledger_totals(ledger)
    assert (totals['wins'], totals['losses'], totals['staked']) == (1, 1, 20.0)
    assert totals['profit'] == pytest.approx(-1.6667, abs=1e-3)
    assert totals['roi'] == pytest.approx(-0.0833, abs=1e-3)


def test_daily_table_shows_odds_and_profit():
    entries = [
        _entry(home_ml='-120', away_ml='+100'),
        _entry(home='BOS', away='NYR', p_home=0.4, home_ml='-170', away_ml='+150'),
        _entry(home='EDM', away='VAN', home_ml='-300', away_ml='+250'),
    ]
    scores = {
        DAY + '|TOR|MTL': {'away_goals': 1, 'home_goals': 2},
        DAY + '|BOS|NYR': {'away_goals': 1, 'home_goals': 2},
    }
    rows = {r['Game']: r for r in picks_for_date(entries, scores, DAY)}
    assert rows['MTL @ TOR']['Odds'] == '-120' and rows['MTL @ TOR']['$10 P/L'] == '+$8.33'
    assert rows['NYR @ BOS']['Odds'] == '+150' and rows['NYR @ BOS']['$10 P/L'] == '-$10.00'
    assert rows['VAN @ EDM']['$10 P/L'] == ''
    assert picks_for_date([_entry()], {}, DAY)[0]['Odds'] == 'n/a'

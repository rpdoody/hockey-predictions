import math

import pytest

from src.utils.gap_stats import gap_summary, log_loss_gaps


def test_summary_of_a_symmetric_set_of_gaps():
    summary = gap_summary([0.01, -0.01, 0.03, -0.03])
    assert summary['n'] == 4 and summary['mean'] == pytest.approx(0.0)
    assert summary['se'] == pytest.approx(0.0129099, abs=1e-6)
    assert summary['low'] == pytest.approx(-1.96 * summary['se'])
    assert summary['high'] == pytest.approx(1.96 * summary['se'])


def test_summary_needs_two_games():
    assert gap_summary([]) is None
    assert gap_summary([0.1]) is None


def _row(home, away, used, home_ml='-110', away_ml='-110'):
    return {'game_date': '2026-10-10', 'home_team': home, 'away_team': away,
            'home_win_prob_used': used, 'home_ml': home_ml, 'away_ml': away_ml}


def _fakes(scores):
    return dict(
        select=lambda rows, which: rows,
        lookup=lambda table, date, home, away: table.get((date, home, away)),
        fair=lambda home_ml, away_ml: None if home_ml is None else 0.5,
    )


def test_gap_is_negative_when_the_model_is_better_and_positive_when_worse():
    scores = {
        ('2026-10-10', 'BOS', 'PHI'): {'home_goals': 3, 'away_goals': 1},
        ('2026-10-10', 'TOR', 'MTL'): {'home_goals': 1, 'away_goals': 2},
    }
    rows = [_row('BOS', 'PHI', 0.6), _row('TOR', 'MTL', 0.6)]
    gaps = log_loss_gaps(rows, scores, **_fakes(scores))
    assert gaps[0] == pytest.approx(-math.log(0.6) + math.log(0.5))
    assert gaps[1] == pytest.approx(-math.log(0.4) + math.log(0.5))
    assert gaps[0] < 0 < gaps[1]


def test_games_without_a_result_a_market_or_a_probability_are_skipped():
    scores = {('2026-10-10', 'BOS', 'PHI'): {'home_goals': 3, 'away_goals': 1}}
    rows = [
        _row('BOS', 'PHI', 0.6),
        _row('TOR', 'MTL', 0.6),
        _row('BOS', 'PHI', 0.6, home_ml=None, away_ml=None),
        _row('BOS', 'PHI', None),
    ]
    assert len(log_loss_gaps(rows, scores, **_fakes(scores))) == 1

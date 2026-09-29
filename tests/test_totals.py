"""Unit tests for the totals model; full-game settlement needs separate modeling."""
import math

import pytest

from src.models.totals import predict_total


def poisson_pmf(mean, goals):
    return math.exp(-mean) * mean**goals / math.factorial(goals)


@pytest.mark.parametrize("line,under_max,push_goals", [(6.0, 5, 6), (6.5, 6, None)])
def test_totals_at_quoted_line(line, under_max, push_goals):
    prediction = predict_total(3.0, 3.0, line=line)
    expected_under = sum(poisson_pmf(6.0, goals) for goals in range(under_max + 1))
    expected_push = poisson_pmf(6.0, push_goals) if push_goals is not None else 0.0
    assert prediction.expected_total == pytest.approx(6.0)
    assert prediction.under_prob == pytest.approx(expected_under, abs=0.00005)
    assert prediction.push_prob == pytest.approx(expected_push, abs=0.00005)
    assert prediction.over_prob == pytest.approx(1 - expected_under - expected_push, abs=0.00005)
    assert prediction.over_prob + prediction.under_prob + prediction.push_prob == pytest.approx(1.0, abs=0.00011)


@pytest.mark.xfail(strict=True, reason="predict_total does not yet validate expected-goals inputs")
@pytest.mark.parametrize("home_xg,away_xg", [(-1.0, 3.0), (math.nan, 3.0), (math.inf, 3.0), (3.0, -1.0), (3.0, math.inf)])
def test_invalid_expected_goals_are_rejected(home_xg, away_xg):
    with pytest.raises(ValueError):
        predict_total(home_xg, away_xg, line=6.0)


@pytest.mark.xfail(strict=True, reason="predict_total does not yet validate total lines")
@pytest.mark.parametrize("line", [-0.5, math.nan, math.inf, 6.25])
def test_invalid_line_is_rejected(line):
    with pytest.raises(ValueError):
        predict_total(3.0, 3.0, line=line)


def test_regulation_tie_can_change_full_game_total_settlement():
    """A 3-3 regulation tie is not a final-score 6; do not treat it as one."""
    regulation_home, regulation_away = 3, 3
    final_home, final_away = 4, 3  # illustrative OT/shootout final
    assert regulation_home + regulation_away == 6
    assert final_home + final_away == 7
    assert regulation_home + regulation_away < 6.5
    assert final_home + final_away > 6.5
    assert regulation_home + regulation_away == 6.0  # push at 6.0
    assert final_home + final_away > 6.0  # over at 6.0

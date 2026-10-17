import pytest

from src.utils.shooting_regression import (
    binomial_tail, position_baselines, position_group, regression_candidates,
)


def _p(name, pos, goals, shots):
    return {'name': name, 'team': 'BOS', 'position': pos, 'games': 12, 'goals': goals, 'shots': shots}


def test_binomial_tail_matches_hand_calculations():
    assert binomial_tail(2, 2, 0.5, upper=True) == pytest.approx(0.25)
    assert binomial_tail(0, 2, 0.5, upper=False) == pytest.approx(0.25)
    assert binomial_tail(0, 5, 0.3, upper=True) == pytest.approx(1.0)
    assert binomial_tail(8, 10, 0.5, upper=True) == pytest.approx(56 / 1024)
    assert binomial_tail(2, 10, 0.5, upper=False) == pytest.approx(56 / 1024)


def test_binomial_tail_rejects_degenerate_probability():
    with pytest.raises(ValueError):
        binomial_tail(1, 5, 0.0)


def test_position_groups():
    assert position_group('D') == 'D'
    assert {position_group(c) for c in ('C', 'L', 'R', None)} == {'F'}


def test_baselines_are_pooled_goals_per_shot_by_group():
    skaters = [_p('a', 'C', 10, 100), _p('b', 'L', 20, 200), _p('c', 'D', 2, 100)]
    assert position_baselines(skaters) == pytest.approx({'F': 0.1, 'D': 0.02})


def _pool():
    forwards = [_p(f'F{i}', 'C', 10, 100) for i in range(40)]
    defense = [_p(f'D{i}', 'D', 8, 200) for i in range(20)]
    return forwards + defense


def test_hot_and_cold_forwards_are_flagged_and_typical_players_are_not():
    skaters = _pool() + [_p('Hot', 'R', 15, 40), _p('Cold', 'L', 0, 100), _p('Tiny', 'C', 5, 10)]
    result = regression_candidates(skaters)
    flagged = {r['name']: r for r in result['rows']}
    assert set(flagged) == {'Hot', 'Cold'}
    assert flagged['Hot']['signal'] == 'hot' and flagged['Cold']['signal'] == 'cold'
    assert flagged['Hot']['goals'] > flagged['Hot']['expected_goals']
    base = flagged['Hot']['baseline_pct']
    assert base < flagged['Hot']['shrunk_pct'] < flagged['Hot']['shooting_pct']
    assert flagged['Cold']['shooting_pct'] < flagged['Cold']['shrunk_pct'] < base


def test_defensemen_are_judged_against_defensemen_not_forwards():
    result = regression_candidates(_pool())
    assert result['rows'] == []
    assert result['baselines']['D'] < result['baselines']['F']


def test_rows_are_sorted_by_how_unlikely_they_are():
    skaters = _pool() + [_p('Hot', 'R', 15, 40), _p('Hotter', 'R', 30, 60)]
    names = [r['name'] for r in regression_candidates(skaters)['rows']]
    assert names == ['Hotter', 'Hot']

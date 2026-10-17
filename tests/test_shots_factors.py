import numpy as np
import pytest

from src.utils.shots_factors import (
    back_to_back, format_experiment, make_adjuster, opponent_factors, pooled_multipliers, run_factor_experiment,
)
from src.utils.shots_model import walk_forward


def _row(date, shots, minutes=20.0, home=True, opponent='BOS'):
    return {'date': date, 'shots': shots, 'minutes': minutes, 'home': home, 'opponent': opponent}


def test_back_to_back_needs_consecutive_days_and_valid_dates():
    assert back_to_back('2026-10-09', '2026-10-10') is True
    assert back_to_back('2026-10-08', '2026-10-10') is False
    assert back_to_back(None, '2026-10-10') is None and back_to_back('bad', '2026-10-10') is None


def test_pooled_multipliers_compare_each_situation_with_all_games():
    days = [1, 2, 4, 5, 7, 8, 10, 11, 13, 14]
    shots = [4, 2, 4, 2, 4, 2, 4, 2, 4, 2]
    rows = [_row(f'2025-11-{d:02d}', s, home=bool(i % 2)) for i, (d, s) in enumerate(zip(days, shots))]
    result = pooled_multipliers([{'prior_rows': rows}])
    assert result['b2b'] == pytest.approx(2 / 3)
    assert result['rested'] == pytest.approx(4 / 3)
    assert pooled_multipliers([{'prior_rows': []}]) == {}


def test_home_and_away_multipliers_split_shots_by_venue():
    rows = [_row(f'2025-11-{d:02d}', 4 if d % 2 else 2, home=bool(d % 2)) for d in range(1, 21)]
    result = pooled_multipliers([{'prior_rows': rows}])
    assert result['home'] == pytest.approx(4 / 3) and result['away'] == pytest.approx(2 / 3)


def test_opponent_factors_are_relative_to_the_league_average():
    teams = [
        {'teamId': 1, 'shotsAgainstPerGame': 28.0}, {'teamId': 2, 'shotsAgainstPerGame': 30.0},
        {'teamId': 3, 'shotsAgainstPerGame': 32.0}, {'teamId': 99, 'shotsAgainstPerGame': 50.0},
    ]
    factors = opponent_factors(teams, {1: 'AAA', 2: 'BBB', 3: 'CCC'})
    assert factors['AAA'] == pytest.approx(28 / 30) and factors['BBB'] == pytest.approx(1.0)
    assert factors['CCC'] == pytest.approx(32 / 30) and 'DDD' not in factors
    assert opponent_factors([], {}) == {}


def test_adjuster_applies_only_the_chosen_inputs():
    mult = {'home': 1.1, 'away': 0.9, 'b2b': 0.95, 'rested': 1.02}
    opp = {'BOS': 1.1}
    row = _row('2026-10-10', 3, home=True, opponent='BOS')
    history = [_row('2026-10-09', 2)]
    assert make_adjuster(mult, opp)(None, row, history) == 1.0
    assert make_adjuster(mult, opp, home=True)(None, row, history) == pytest.approx(1.1)
    assert make_adjuster(mult, opp, rest=True)(None, row, history) == pytest.approx(0.95)
    assert make_adjuster(mult, opp, rest=True)(None, row, []) == 1.0
    assert make_adjuster(mult, opp, opponent_weight=0.5)(None, row, history) == pytest.approx(1.1 ** 0.5)
    assert make_adjuster(mult, opp, opponent_weight=1.0)(None, _row('d', 1, opponent='ZZZ'), []) == 1.0


def test_walk_forward_scales_the_projection_by_the_adjuster():
    prior = [_row(f'2025-11-{d:02d}', 4) for d in range(1, 31)]
    player = {'name': 'A', 'rows': [_row('2026-10-01', 3)], 'prior_rows': prior, 'baseline_rate': 0.1}
    plain = walk_forward([player])[0]['mu']
    doubled = walk_forward([player], adjust=lambda p, r, h: 2.0)[0]['mu']
    assert doubled == pytest.approx(2 * plain)


def _league(n=120, home_boost=1.3, seed=5):
    rng = np.random.default_rng(seed)
    players = []
    for i in range(n):
        rate, minutes = rng.uniform(0.08, 0.16), rng.uniform(15, 21)

        def season(games, year, month):
            rows = []
            for g in range(games):
                home = g % 2 == 0
                mean = rate * minutes * (home_boost if home else 1.0)
                rows.append({'date': f'{year}-{month + g // 28:02d}-{g % 28 + 1:02d}', 'shots': int(rng.poisson(mean)),
                             'minutes': minutes, 'home': home, 'opponent': 'BOS'})
            return rows

        players.append({'name': f'P{i}', 'prior_rows': season(70, 2025, 1), 'rows': season(16, 2026, 10),
                        'baseline_rate': 0.1})
    return players


def test_experiment_finds_a_real_home_effect_and_not_a_fake_opponent_effect():
    players = _league()
    report = run_factor_experiment(players, pooled_multipliers(players), {'BOS': 1.0})
    assert report['games'] == 120 * 16
    home = report['results']['+ home/away']['gap']
    assert home['low'] > 0 and report['multipliers']['home'] > report['multipliers']['away']
    opp = report['results']['+ opponent (full weight)']['gap']
    assert opp['mean'] == pytest.approx(0.0, abs=1e-9)
    text = format_experiment(report)
    assert 'clearly better' in text and 'negligible difference' in text and 'learned multipliers' in text


def test_verdict_ignores_statistically_clear_but_tiny_differences():
    from src.utils.shots_factors import _verdict
    assert _verdict(None) == ''
    assert _verdict({'mean': 0.0002, 'low': 0.0001, 'high': 0.0003}) == 'negligible difference'
    assert _verdict({'mean': 0.005, 'low': 0.002, 'high': 0.008}) == 'clearly better'
    assert _verdict({'mean': -0.005, 'low': -0.008, 'high': -0.002}) == 'clearly worse'
    assert _verdict({'mean': 0.004, 'low': -0.003, 'high': 0.011}) == 'no clear difference'

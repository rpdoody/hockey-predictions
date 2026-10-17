import math

import pytest

from src.utils.shots_model import (
    american_to_prob, blended_rate, devig_two_way, estimate_dispersion, evaluate, expected_value,
    game_rows, nb_pmf, paired_loglik_gap, parse_toi, project_minutes, project_shots, prob_over,
    season_rate, walk_forward,
)


def _row(date, shots, minutes):
    return {'date': date, 'shots': shots, 'minutes': minutes}


def test_parse_toi_and_game_rows_skip_games_without_ice_time():
    assert parse_toi('16:30') == pytest.approx(16.5)
    assert parse_toi(None) is None and parse_toi('bad') is None
    log = [
        {'gameDate': '2026-10-03', 'shots': 4, 'toi': '18:00', 'opponentAbbrev': 'BOS', 'homeRoadFlag': 'H'},
        {'gameDate': '2026-10-01', 'shots': 2, 'toi': '17:30', 'opponentAbbrev': 'NYR', 'homeRoadFlag': 'R'},
        {'gameDate': '2026-10-05', 'shots': 0, 'toi': '00:00'},
    ]
    rows = game_rows(log)
    assert [r['date'] for r in rows] == ['2026-10-01', '2026-10-03']
    assert rows[1]['home'] is True and rows[0]['home'] is False


def test_blended_rate_moves_from_the_prior_toward_the_data_as_minutes_grow():
    prior = 0.10
    assert blended_rate([], prior) == pytest.approx(prior)
    few = [_row('a', 6, 20)]
    many = [_row(str(i), 6, 20) for i in range(30)]
    assert prior < blended_rate(few, prior) < blended_rate(many, prior) < season_rate(many)
    assert blended_rate([], None) is None
    assert blended_rate(few, None) == pytest.approx(0.3)


def test_project_minutes_follows_recent_usage():
    assert project_minutes([], 18.0) == 18.0
    assert project_minutes([], None) is None
    history = [_row(str(i), 2, 24.0) for i in range(12)]
    assert project_minutes(history, 16.0) > 22.5
    assert project_minutes(history, None) == pytest.approx(24.0)


def test_project_shots_needs_some_information():
    assert project_shots([], None, None) is None
    assert project_shots([], 0.1, 20.0) == pytest.approx(2.0)


def test_negative_binomial_sums_to_one_and_matches_poisson_without_spread():
    assert sum(nb_pmf(k, 2.8, 0.2) for k in range(80)) == pytest.approx(1.0, abs=1e-6)
    assert nb_pmf(2, 2.0, 0.0) == pytest.approx(2.0 * math.exp(-2.0))
    assert nb_pmf(0, 0.0, 0.2) == 1.0 and nb_pmf(3, 0.0, 0.2) == 0.0


def test_prob_over_matches_a_hand_calculation_and_spread_fattens_the_tails():
    assert prob_over(2.0, 0.0, 2.5) == pytest.approx(1 - 5 * math.exp(-2.0))
    assert prob_over(2.0, 0.3, 4.5) > prob_over(2.0, 0.0, 4.5)
    assert prob_over(1.0, 0.1, 1.5) < prob_over(3.0, 0.1, 1.5)


def test_dispersion_is_zero_for_poisson_like_data_and_positive_for_overdispersed_data():
    means = [2.0] * 8
    assert estimate_dispersion(means, [2, 2, 2, 2, 2, 2, 2, 2]) == 0.0
    assert estimate_dispersion(means, [0, 5, 1, 4, 0, 6, 1, 3]) > 0.1


def test_odds_helpers():
    assert american_to_prob(-110) == pytest.approx(110 / 210) and american_to_prob(150) == pytest.approx(0.4)
    fair = devig_two_way(-110, -110)
    assert fair['p_over'] == pytest.approx(0.5) and fair['overround'] == pytest.approx(220 / 210 - 1)
    skewed = devig_two_way(-150, 120)
    assert skewed['p_over'] + skewed['p_under'] == pytest.approx(1.0) and skewed['p_over'] > 0.55
    assert expected_value(0.5, 100) == pytest.approx(0.0)
    assert expected_value(0.55, -110) == pytest.approx(0.55 * (100 / 110) - 0.45)


def _walk_player(rows, prior_shots_per_game=4, baseline=0.1):
    prior = [{'date': f'2025-1{i % 3}-0{i % 9 + 1}', 'shots': prior_shots_per_game, 'minutes': 20.0} for i in range(30)]
    return {'name': 'A', 'rows': rows, 'prior_rows': prior, 'baseline_rate': baseline}


def test_walk_forward_never_uses_the_game_it_predicts_or_later_games():
    rows = [{'date': f'2026-10-{d:02d}', 'shots': s, 'minutes': 18.0} for d, s in enumerate([2, 3, 1, 4, 2], start=1)]
    base = _walk_player(rows, 2)
    first = walk_forward([base])
    changed = [dict(r) for r in rows]
    changed[3]['shots'] = 11
    second = walk_forward([dict(base, rows=changed)])
    assert [p['mu'] for p in first[:4]] == pytest.approx([p['mu'] for p in second[:4]])
    assert first[4]['mu'] != pytest.approx(second[4]['mu'])


def test_prior_shrink_pulls_last_seasons_rate_toward_the_position_baseline():
    rows = [{'date': '2026-10-01', 'shots': 3, 'minutes': 20.0}]
    player = _walk_player(rows)
    plain = walk_forward([player])[0]['mu']
    shrunk = walk_forward([player], prior_shrink=600)[0]['mu']
    assert plain == pytest.approx(0.2 * 20.0)
    assert shrunk == pytest.approx((120 + 600 * 0.1) / (600 + 600) * 20.0)
    assert 0.1 * 20 < shrunk < plain
    assert walk_forward([player], prior_shrink=0)[0]['mu'] == pytest.approx(plain)


def test_evaluate_reports_calibration_for_each_line():
    preds = [{'actual': a, 'mu': 2.5, 'naive_prior': 2.0, 'naive_to_date': None} for a in [1, 2, 3, 4, 2, 3, 5, 0] * 5]
    result = evaluate(preds, 'mu')
    assert result['n'] == 40 and set(result['lines']) == {1.5, 2.5, 3.5}
    assert result['lines'][2.5]['observed_over'] == pytest.approx(20 / 40)
    assert result['lines'][1.5]['observed_over'] == pytest.approx(30 / 40)
    assert result['mean_predicted'] == pytest.approx(2.5) and result['mean_actual'] == pytest.approx(2.5)
    assert evaluate(preds, 'naive_prior', lines=(2.5,))['n'] == 40


def test_paired_gap_is_positive_when_the_first_predictor_is_closer_and_zero_for_identical_ones():
    preds = [{'actual': a, 'a': 3.0, 'b': 1.0, 'c': 3.0} for a in [3, 2, 4, 3, 3, 5, 2, 3]]
    better = paired_loglik_gap(preds, 'a', 'b')
    assert better['mean'] > 0 and better['low'] < better['mean'] < better['high']
    same = paired_loglik_gap(preds, 'a', 'c')
    assert same['mean'] == pytest.approx(0.0) and same['se'] == pytest.approx(0.0)
    assert paired_loglik_gap(preds[:1], 'a', 'b') is None

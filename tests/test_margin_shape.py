from src.utils.margin_shape import fit_q, shaped_distribution, two_goal_share
from src.utils.totals_puckline import model_distribution

ENTRIES = [{'home_xg': 3.1 + 0.1 * (i % 4), 'away_xg': 3.0 - 0.1 * (i % 3)} for i in range(40)]


def test_zero_q_matches_the_existing_model():
    assert shaped_distribution(3.2, 2.9, 0.0)['margins'] == model_distribution(3.2, 2.9)['margins']


def test_distributions_stay_normalised_and_totals_unchanged():
    d = shaped_distribution(3.4, 2.8, 0.2)
    assert abs(sum(d['margins'].values()) - 1) < 1e-9
    assert d['totals'] == model_distribution(3.4, 2.8)['totals']


def test_q_raises_two_goal_games_and_lowers_one_goal_games():
    base, shaped = model_distribution(3.4, 2.8)['margins'], shaped_distribution(3.4, 2.8, 0.2)['margins']
    assert shaped[2] > base[2] and shaped[1] < base[1]


def test_fit_q_hits_the_target_share():
    q = fit_q(ENTRIES, 0.60)
    assert 0 < q <= 1
    assert abs(two_goal_share(ENTRIES, q) - 0.60) < 1e-6

import pytest

from src.models.gap_stretch import GAP_STRETCH, MIN_XG, stretch_xg, stretched_fields
from src.models.win_probability import calculate_win_probability


def test_factor_one_leaves_expected_goals_unchanged():
    home, away = stretch_xg(3.4, 2.8, 1.0)
    assert home == pytest.approx(3.4) and away == pytest.approx(2.8)


def test_stretch_widens_the_gap_and_keeps_the_total():
    home, away = stretch_xg(3.4, 2.8, 2.0)
    assert home - away == pytest.approx(1.2)
    assert home + away == pytest.approx(6.2)


def test_stretched_probability_is_further_from_even_for_the_favourite():
    fields = stretched_fields(3.4, 2.8)
    assert fields['home_win_prob_stretch_raw'] > calculate_win_probability(3.4, 2.8).home_win
    assert fields['gap_stretch'] == GAP_STRETCH


def test_expected_goals_never_fall_below_the_floor():
    home, away = stretch_xg(4.5, 1.0, 3.0)
    assert away == MIN_XG and home > 4.5

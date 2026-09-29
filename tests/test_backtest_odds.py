"""Checks for the odds conversion used by the backtest simulator."""
from src.utils.odds import decimal_to_american


def test_favorite_odds_are_near_fair_price():
    assert -110 <= decimal_to_american(1 / 0.52) <= -106
    assert -125 <= decimal_to_american(1 / 0.55) <= -119


def test_underdog_odds_are_near_fair_price():
    assert 120 <= decimal_to_american(1 / 0.45) <= 124

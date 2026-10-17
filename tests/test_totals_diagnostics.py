from src.utils.totals_diagnostics import blend_weight, calibration_table


def _row(model_p, market_p, outcome, market='Total'):
    return {'market': market, 'status': 'graded', 'outcome': outcome,
            'model_p': model_p, 'market_p': market_p, 'line': 6.0}


def test_blend_prefers_market_when_model_is_noise():
    rows = [_row(0.8 if i % 2 else 0.2, 0.5, i % 2 == 0) for i in range(40)]
    assert blend_weight(rows, 'Total')['best_weight'] <= 0.2


def test_blend_needs_a_minimum_sample():
    assert blend_weight([_row(0.5, 0.5, 1)] * 5, 'Total') is None


def test_calibration_bins_cover_every_game():
    rows = [_row(i / 40, 0.5, i % 2) for i in range(40)]
    assert sum(b['n'] for b in calibration_table(rows, 'Total')) == 40

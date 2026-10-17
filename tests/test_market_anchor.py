from src.utils.market_anchor import adjust, fit, report


def _rows(n, informative, seed=1):
    import random
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        m = rng.uniform(0.4, 0.6)
        noise = rng.uniform(-0.1, 0.1)
        true_p = min(max(m + (noise if informative else 0.0), 0.05), 0.95)
        model = min(max(m + (noise if informative else rng.uniform(-0.1, 0.1)), 0.05), 0.95)
        rows.append({'market': 'Total', 'status': 'graded', 'date': '2026-10-{:02d}'.format(1 + i % 28),
                     'market_p': m, 'model_p': model, 'outcome': int(rng.random() < true_p)})
    return rows


def test_pure_noise_model_gets_little_weight():
    assert abs(fit(_rows(600, False))['c']) < 0.5


def test_informative_model_gets_positive_weight():
    assert fit(_rows(3000, True))['c'] > 0.3


def test_adjust_with_zero_params_returns_market():
    assert abs(adjust(0.55, 0.9, {'a': 0.0, 'c': 0.0}) - 0.55) < 1e-9


def test_report_needs_enough_history():
    assert report(_rows(20, False), 'Total') is None
    assert report(_rows(300, True), 'Total')['n_scored'] > 0

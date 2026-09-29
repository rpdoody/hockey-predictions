'''Tests for the Performance page helper.'''
import json

from src.utils.performance import MIN_GAMES, load_scorecard, segment_rows, verdict


def _probs(count, blended=0.69, market=0.70):
    def metrics(loss):
        return {'brier': 0.25, 'log_loss': loss}
    return {
        'n': count,
        'p_raw': metrics(0.71),
        'p_used': metrics(blended),
        'p_market': metrics(market),
    }


def _report(count=2, blended=0.69, market=0.70, bets=None):
    summary = {'probabilities': _probs(count, blended, market), 'bets': bets or {'n': 0}}
    return {
        'games_logged': count, 'games_scored': count, 'games_pending': 0,
        'overall': summary,
        'by_segment': {'prior_only': summary},
    }


def test_load_scorecard_handles_missing_and_invalid_files(tmp_path):
    assert load_scorecard(tmp_path / 'missing.json') is None
    bad = tmp_path / 'bad.json'
    bad.write_text('not json')
    assert load_scorecard(bad) is None
    good = tmp_path / 'good.json'
    good.write_text(json.dumps({'games_scored': 3}))
    assert load_scorecard(good) == {'games_scored': 3}


def test_segment_rows_without_bets_show_n_a():
    rows = segment_rows(_report())
    assert [r['Segment'] for r in rows] == ['All games', 'Last-season ratings only']
    assert rows[0]['Log loss: market'] == '0.7000'
    assert rows[0]['Simulated bets'] == 0
    assert rows[0]['ROI'] == 'n/a'
    assert rows[0]['Avg closing-line value'] == 'n/a'


def test_segment_rows_format_bets():
    bets = {
        'n': 4, 'wins': 3, 'hit_rate': 0.75, 'units': 1.2, 'roi': 0.3,
        'avg_edge': 0.05, 'clv_n': 2, 'avg_clv': 0.012,
    }
    row = segment_rows(_report(bets=bets))[0]
    assert row['Simulated bets'] == 4
    assert row['Win rate'] == '75.0%'
    assert row['Units'] == '+1.20'
    assert row['ROI'] == '+30.0%'
    assert row['Avg closing-line value'] == '+1.2%'
    assert row['Bets with a closing line'] == 2


def test_verdict_needs_a_meaningful_sample():
    text = verdict(_report(count=10))
    assert 'Only 10 games' in text and str(MIN_GAMES) in text
    assert 'No games' in verdict(_report(count=0))


def test_verdict_compares_blended_model_with_market():
    assert 'lower log loss than the market' in verdict(_report(count=200, blended=0.68, market=0.70))
    assert 'does not beat the market' in verdict(_report(count=200, blended=0.72, market=0.70))

'''Tests for the Performance page helper.'''
import json

from src.utils.performance import (
    LOSS, MIN_GAMES, NO_PICK, PENDING, WIN,
    day_summary, load_pick_log, load_scorecard, picks_for_date, segment_rows, verdict,
)

DAY = '2026-09-29'


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


def _entry(home='TOR', away='MTL', p_home=0.6, fair=0.5, logged='2026-09-29T20:00:00+00:00', **extra):
    row = {
        'logged_at': logged, 'game_date': DAY, 'game_time': '7:00 PM ET',
        'start_utc': '2026-09-29T23:00Z', 'home_team': home, 'away_team': away,
        'prior_only': True, 'home_win_prob_used': p_home, 'fair_home_prob': fair,
    }
    row.update(extra)
    return row


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


def test_load_pick_log_reads_all_files_and_skips_bad_lines(tmp_path):
    (tmp_path / '2026-09.jsonl').write_text(json.dumps(_entry()) + '\nnot json\n\n')
    (tmp_path / '2026-10.jsonl').write_text(json.dumps(_entry(home='BOS', away='NYR')) + '\n')
    assert len(load_pick_log(tmp_path)) == 2
    assert load_pick_log(tmp_path / 'missing') == []


def test_picks_for_date_grades_each_pick():
    entries = [
        _entry(),
        _entry(home='BOS', away='NYR', p_home=0.4, fair=0.45),
        _entry(home='EDM', away='VAN'),
    ]
    scores = {
        DAY + '|MTL|TOR': {'away_goals': 1, 'home_goals': 2},
        DAY + '|NYR|BOS': {'away_goals': 1, 'home_goals': 2},
    }
    rows = {r['Game']: r for r in picks_for_date(entries, scores, DAY)}
    tor = rows['MTL @ TOR']
    assert (tor['Pick'], tor['Model win %'], tor['Market win %'], tor['Edge']) == ('TOR', '60.0%', '50.0%', '+10.0%')
    assert tor['Result'] == WIN and tor['Final score'] == 'MTL 1 - TOR 2'
    bos = rows['NYR @ BOS']
    assert (bos['Pick'], bos['Model win %'], bos['Edge']) == ('NYR', '60.0%', '+5.0%')
    assert bos['Result'] == LOSS
    assert rows['VAN @ EDM']['Result'] == PENDING and rows['VAN @ EDM']['Final score'] == ''


def test_picks_for_date_uses_last_entry_logged_before_start():
    early = _entry(p_home=0.6, logged='2026-09-29T15:00:00+00:00')
    later = _entry(p_home=0.3, logged='2026-09-29T20:00:00+00:00')
    after_start = _entry(p_home=0.9, logged='2026-09-29T23:30:00+00:00')
    rows = picks_for_date([early, after_start, later], {}, DAY)
    assert len(rows) == 1 and rows[0]['Pick'] == 'MTL'
    assert picks_for_date([early], {}, '2026-09-28') == []


def test_picks_for_date_handles_missing_probabilities():
    rows = picks_for_date([_entry(fair=None), _entry(home='BOS', away='NYR', p_home=None)], {}, DAY)
    by_game = {r['Game']: r for r in rows}
    assert by_game['MTL @ TOR']['Market win %'] == 'n/a' and by_game['MTL @ TOR']['Edge'] == 'n/a'
    assert by_game['NYR @ BOS']['Pick'] == 'n/a' and by_game['NYR @ BOS']['Result'] == NO_PICK


def test_day_summary():
    assert day_summary([]) == 'No picks were logged for this date.'
    assert day_summary([{'Result': PENDING}]) == 'No finished games yet (1 pending).'
    rows = [{'Result': WIN}, {'Result': WIN}, {'Result': LOSS}, {'Result': PENDING}]
    assert day_summary(rows) == 'Model picked 2 of 3 winners (67%). 1 still pending.'

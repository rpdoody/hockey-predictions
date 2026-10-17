import json
import math

import pytest

from src.utils.shots_edges import build_edges, latest_lines, read_snapshot_rows
from src.utils.shots_model import devig_two_way, expected_value, prob_over

NOW = '2026-10-17T20:00:00Z'


def _line(player='Brad Marchand', book='draftkings', point=2.5, over=-110, under=-110, ts='2026-10-17T15:00:00Z',
          start='2026-10-17T23:00:00Z', label='open', event='e1'):
    return {'snapshot_ts': ts, 'label': label, 'event_id': event, 'commence_time': start, 'home_team': 'Boston Bruins',
            'away_team': 'Philadelphia Flyers', 'book': book, 'player': player, 'line': point,
            'over_price': over, 'under_price': under, 'market_last_update': ts}


def test_latest_lines_keeps_the_newest_snapshot_and_drops_started_games_and_test_rows():
    rows = [
        _line(ts='2026-10-17T15:00:00Z', over=-110), _line(ts='2026-10-17T18:00:00Z', over=-125),
        _line(player='Started Guy', start='2026-10-17T19:00:00Z'),
        _line(player='Test Guy', label='test'),
        _line(book='fanduel', over=-105),
    ]
    lines = latest_lines(rows, NOW)
    assert {(r['player'], r['book']) for r in lines} == {('Brad Marchand', 'draftkings'), ('Brad Marchand', 'fanduel')}
    assert next(r for r in lines if r['book'] == 'draftkings')['over_price'] == -125


def test_read_snapshot_rows_handles_missing_files_and_blank_lines(tmp_path):
    assert read_snapshot_rows(tmp_path / 'nope.jsonl') == []
    path = tmp_path / 'rows.jsonl'
    path.write_text(json.dumps(_line()) + '\n\n' + json.dumps(_line(player='B')) + '\n')
    assert [r['player'] for r in read_snapshot_rows(path)] == ['Brad Marchand', 'B']


def test_build_edges_scores_both_sides_against_the_vig_free_line():
    projections = {('e1', 'Brad Marchand'): {'mu': 3.0, 'team': 'BOS', 'position': 'L', 'games': 8, 'days_since_last': 2}}
    edges = build_edges([_line()], projections, dispersion=0.0)
    assert len(edges) == 1
    e = edges[0]
    p_over = 1 - math.exp(-3.0) * (1 + 3 + 4.5)
    assert e['model_p_over'] == pytest.approx(p_over) and e['model_mean'] == 3.0
    assert e['market_p_over'] == pytest.approx(0.5) and e['best_side'] == 'Over'
    assert e['ev_over'] == pytest.approx(expected_value(p_over, -110))
    assert e['ev_under'] == pytest.approx(expected_value(1 - p_over, -110)) and e['ev_under'] < 0
    assert e['best_edge'] == pytest.approx(p_over - 0.5) and e['team'] == 'BOS' and e['game'] == 'Philadelphia Flyers at Boston Bruins'


def test_build_edges_picks_the_under_when_the_model_expects_fewer_shots():
    projections = {('e1', 'Brad Marchand'): {'mu': 1.5, 'team': 'BOS'}}
    e = build_edges([_line()], projections, dispersion=0.0)[0]
    assert e['best_side'] == 'Under' and e['best_ev'] == e['ev_under'] > 0
    fair = devig_two_way(-110, -110)
    assert e['best_edge'] == pytest.approx((1 - prob_over(1.5, 0.0, 2.5)) - fair['p_under'])


def test_build_edges_skips_lines_it_cannot_score():
    projections = {('e1', 'Brad Marchand'): {'mu': 3.0}, ('e1', 'No Data'): {'mu': None, 'reason': 'unmatched'}}
    lines = [
        _line(under=None), _line(point=3.0), _line(player='No Data'), _line(player='Not Projected'),
        _line(player='Brad Marchand', point=3.5),
    ]
    edges = build_edges(lines, projections)
    assert [(e['player'], e['line']) for e in edges] == [('Brad Marchand', 3.5)]

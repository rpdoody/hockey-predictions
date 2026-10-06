from src.utils.totals_puckline import (
    grade_games, model_distribution, settled_totals, spread_outcome, spread_probs,
    summarize, total_outcome, total_probs,
)


def test_distributions_sum_to_one():
    dist = model_distribution(3.1, 2.8)
    assert abs(sum(dist['totals'].values()) - 1) < 1e-9
    assert abs(sum(dist['margins'].values()) - 1) < 1e-9


def test_over_is_likelier_with_a_low_line_and_probabilities_add_up():
    dist = model_distribution(3.0, 3.0)
    over, under, push = total_probs(dist, 5.5)
    assert over > 0.5 and abs(over + under + push - 1) < 1e-9 and abs(push) < 1e-9
    assert total_probs(dist, 4.5)[0] > over > total_probs(dist, 6.5)[0]


def test_puck_line_favourite_and_underdog():
    dist = model_distribution(4.0, 2.0)
    assert spread_probs(dist, -1.5)[0] < spread_probs(dist, -0.5)[0]
    assert spread_probs(dist, 1.5)[0] > spread_probs(dist, -1.5)[0]
    assert abs(sum(spread_probs(dist, -1.5)) - 1) < 1e-9


def test_shootout_goal_is_not_counted_in_totals():
    score = {'home_goals': 3, 'away_goals': 2}
    assert settled_totals({**score, 'period_type': 'SO'}) == {4}
    assert settled_totals({**score, 'period_type': 'OT'}) == {5}
    assert settled_totals(score) == {5, 4}
    assert settled_totals({'home_goals': 5, 'away_goals': 2}) == {7}


def test_unknown_shootout_is_graded_only_when_both_readings_agree():
    score = {'home_goals': 3, 'away_goals': 2}
    assert total_outcome(score, 4.5) is None
    assert total_outcome(score, 5.5) == 'under'
    assert total_outcome({**score, 'period_type': 'SO'}, 4.5) == 'under'
    assert total_outcome({**score, 'period_type': 'OT'}, 4.5) == 'over'


def test_puck_line_outcome_uses_the_final_margin():
    assert spread_outcome({'home_goals': 3, 'away_goals': 1}, -1.5) == 'home'
    assert spread_outcome({'home_goals': 3, 'away_goals': 2}, -1.5) == 'away'
    assert spread_outcome({'home_goals': 3, 'away_goals': 2}, 1.5) == 'home'


def _entry():
    return {
        'game_date': '2026-09-29', 'espn_game_id': '401891773', 'home_team': 'CAR',
        'away_team': 'FLA', 'start_utc': '2026-09-29T23:00Z',
        'logged_at': '2026-09-29T19:00:00+00:00', 'home_xg': 3.0, 'away_xg': 2.9,
        'home_games_played': 25, 'away_games_played': 25,
    }


HISTORY = {'snapshots': [{
    'timestamp': '2026-09-29T18:36:37+00:00', 'home_ml': -130, 'away_ml': 110,
    'total': 6.5, 'over_odds': 105, 'under_odds': -125,
    'home_pl_odds': 190, 'away_pl_odds': -230, 'home_pl_line': -1.5,
}]}


def test_grades_a_one_nil_shutout_loss_for_the_favourite():
    scores = {'2026-09-29|CAR|FLA': {'home_goals': 0, 'away_goals': 1}}
    rows = grade_games([_entry()], scores, lambda gid: HISTORY)
    by_market = {r['market']: r for r in rows}
    assert set(by_market) == {'Total', 'Puck line'}
    assert all(r['status'] == 'graded' and r['outcome'] == 0 for r in rows)
    assert by_market['Puck line']['line'] == -1.5 and by_market['Puck line']['line_source'] == 'stored'
    assert summarize(rows)[0]['Games'] == 1


def test_missing_line_is_inferred_from_the_moneyline_favourite():
    history = {'snapshots': [{k: v for k, v in HISTORY['snapshots'][0].items() if k != 'home_pl_line'}]}
    rows = grade_games([_entry()], {}, lambda gid: history)
    spread = [r for r in rows if r['market'] == 'Puck line'][0]
    assert spread['line'] == -1.5 and spread['line_source'] == 'inferred' and spread['status'] == 'pending'


def test_no_snapshot_before_the_pick_means_no_rows():
    late = {'snapshots': [{**HISTORY['snapshots'][0], 'timestamp': '2026-09-29T20:00:00+00:00'}]}
    assert grade_games([_entry()], {}, lambda gid: late) == []
    assert grade_games([_entry()], {}, lambda gid: None) == []

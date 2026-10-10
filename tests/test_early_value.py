from src.utils.early_value import EARLY_VALUE_MIN_EDGE_PCT, early_blend_predictions


def _row(home, away, source, used=0.56, logged_at='2026-10-10T12:00:00+00:00', date='2026-10-10'):
    return {
        'game_date': date, 'home_team': home, 'away_team': away, 'model_source': source,
        'home_win_prob_used': used, 'logged_at': logged_at,
    }


def test_only_early_blend_games_on_the_date_are_returned():
    rows = [
        _row('TOR', 'MTL', 'Early blend (last season + this season)'),
        _row('BOS', 'NYR', 'Prior season (20252026)'),
        _row('EDM', 'VAN', 'Legacy'),
        _row('SEA', 'ANA', 'Early blend (last season + this season)', date='2026-10-11'),
    ]
    result = early_blend_predictions(rows, '2026-10-10')
    assert list(result) == [('MTL', 'TOR')]


def test_probabilities_edge_floor_and_basis():
    prediction = early_blend_predictions([_row('TOR', 'MTL', 'Early blend (x)', used=0.58)], '2026-10-10')[('MTL', 'TOR')]
    assert prediction['home_win_prob'] == 0.58
    assert abs(prediction['away_win_prob'] - 0.42) < 1e-9
    assert prediction['min_edge'] == EARLY_VALUE_MIN_EDGE_PCT == 5.0
    assert prediction['basis'] == 'Early blend'


def test_the_latest_logged_entry_wins():
    rows = [
        _row('TOR', 'MTL', 'Early blend (x)', used=0.55, logged_at='2026-10-10T10:00:00+00:00'),
        _row('TOR', 'MTL', 'Early blend (x)', used=0.60, logged_at='2026-10-10T14:00:00+00:00'),
        _row('TOR', 'MTL', 'Early blend (x)', used=0.52, logged_at='2026-10-10T08:00:00+00:00'),
    ]
    assert early_blend_predictions(rows, '2026-10-10')[('MTL', 'TOR')]['home_win_prob'] == 0.60


def test_team_codes_are_normalized_and_missing_probabilities_skipped():
    rows = [_row('LA', 'NJ', 'Early blend (x)'), _row('TB', 'SJ', 'Early blend (x)', used=None)]
    mapping = {'LA': 'LAK', 'NJ': 'NJD', 'TB': 'TBL', 'SJ': 'SJS'}
    result = early_blend_predictions(rows, '2026-10-10', lambda code: mapping.get(code, code))
    assert list(result) == [('NJD', 'LAK')]

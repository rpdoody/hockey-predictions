from auto_capture_odds import build_snapshot
from src.utils import odds_storage
from src.utils.odds_storage import get_game_odds_history, save_odds_snapshot


def _save(**extra):
    return save_odds_snapshot(
        '1', 'CAR', 'FLA', -130, 110, total=6.5, over_odds=105, under_odds=-125,
        home_pl_odds=190, away_pl_odds=-230, **extra,
    )


def test_puck_line_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(odds_storage, 'ODDS_DIR', tmp_path)
    assert _save(home_pl_line=-1.5) is True
    assert get_game_odds_history('1')['snapshots'][0]['home_pl_line'] == -1.5


def test_callers_without_the_line_store_null(tmp_path, monkeypatch):
    monkeypatch.setattr(odds_storage, 'ODDS_DIR', tmp_path)
    assert _save() is True
    assert get_game_odds_history('1')['snapshots'][0]['home_pl_line'] is None


def test_repeat_is_skipped_but_a_line_change_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(odds_storage, 'ODDS_DIR', tmp_path)
    assert _save(home_pl_line=-1.5) is True
    assert _save(home_pl_line=-1.5) is False
    assert _save(home_pl_line=1.5) is True
    assert len(get_game_odds_history('1')['snapshots']) == 2


def _game(**spread):
    return {
        'game_id': 1, 'home_team': 'CAR', 'away_team': 'FLA', 'date': '2026-09-29T21:00Z',
        'odds': [{
            'provider': 'DraftKings',
            'moneyline': {'home': '-130', 'away': '+110'},
            'total': {'over': {'line': 'o6.5', 'odds': '+105'}, 'under': {'line': 'u6.5', 'odds': '-125'}},
            'spread': spread or {
                'home': {'line': '-1.5', 'odds': '+190'},
                'away': {'line': '+1.5', 'odds': '-230'},
            },
        }],
    }


def test_build_snapshot_passes_the_home_line():
    snapshot = build_snapshot(_game())
    assert snapshot['home_pl_line'] == -1.5
    assert (snapshot['home_pl_odds'], snapshot['away_pl_odds']) == (190, -230)


def test_build_snapshot_without_a_spread_leaves_the_line_empty():
    game = _game()
    game['odds'][0].pop('spread')
    snapshot = build_snapshot(game)
    assert snapshot['home_pl_line'] is None and snapshot['home_pl_odds'] is None

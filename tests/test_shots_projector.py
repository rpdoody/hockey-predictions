import pytest

from src.utils.name_match import team_lookup
from src.utils.shots_projector import (
    OPPONENT_WEIGHT, build_context, candidates_by_team, project_event_players, project_for_game,
)

TEAMS = {'BOS': 'Boston Bruins', 'PHI': 'Philadelphia Flyers'}


def _game(date, shots, minutes='20:00', home='H', opp='PHI'):
    return {'gameDate': date, 'shots': shots, 'toi': minutes, 'opponentAbbrev': opp, 'homeRoadFlag': home}


class FakeClient:
    ID_TO_TEAM_MAP = {1: 'BOS', 2: 'PHI'}
    TEAM_NAMES = TEAMS

    def __init__(self):
        prior = [_game(f'2025-11-{d:02d}', 3) for d in range(1, 29)] * 2
        self.logs = {
            (1, '20252026'): prior,
            (1, '20262027'): [_game('2026-10-08', 3), _game('2026-10-10', 4), _game('2026-10-12', 2), _game('2026-10-15', 9)],
            (2, '20252026'): prior, (2, '20262027'): [],
        }
        self.skaters = [
            {'player_id': 1, 'name': 'Brad Marchand', 'team': 'BOS', 'position': 'L', 'games': 70, 'shots': 200, 'toi_pg': 1200},
            {'player_id': 2, 'name': 'Rookie Guy', 'team': 'BOS', 'position': 'D', 'games': 60, 'shots': 100, 'toi_pg': 1100},
        ]

    def get_skater_stats(self, season=None, limit=100, sort='points'):
        return self.skaters

    def get_team_stats(self, season=None):
        return {'data': [{'teamId': 1, 'shotsAgainstPerGame': 30.0}, {'teamId': 2, 'shotsAgainstPerGame': 27.0}]}

    def _fetch_sync(self, url, ttl=None):
        pid = int(url.split('/player/')[1].split('/')[0])
        season = url.split('game-log/')[1].split('/')[0]
        return {'gameLog': list(reversed(self.logs[(pid, season)]))}


def _context(**overrides):
    base = {'season': '20262027', 'prior': '20252026', 'baselines': {'F': 0.12, 'D': 0.08},
            'multipliers': {'home': 1.0, 'away': 1.0, 'b2b': 1.0, 'rested': 1.0}, 'opponents': {'PHI': 1.0, 'BOS': 1.0}}
    base.update(overrides)
    return base


def test_candidates_group_players_under_each_team_including_traded_players():
    skaters = [
        {'player_id': 1, 'name': 'A', 'team': 'BOS', 'position': 'C'},
        {'player_id': 2, 'name': 'B', 'team': 'NYR, TBL', 'position': 'D'},
        {'player_id': 3, 'name': 'C', 'team': '', 'position': 'L'},
    ]
    by_team = candidates_by_team(skaters)
    assert [p['name'] for p in by_team['BOS']] == ['A']
    assert by_team['NYR'][0]['teams'] == ['NYR', 'TBL'] and by_team['TBL'][0]['name'] == 'B'
    assert set(by_team) == {'BOS', 'NYR', 'TBL'}


def test_projection_uses_only_games_before_the_game_date():
    client, ctx = FakeClient(), _context()
    first = project_for_game(client, ctx, 1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-13')
    assert first['games'] == 3 and first['last_game'] == '2026-10-12' and first['days_since_last'] == 1
    client.logs[(1, '20262027')][3]['shots'] = 40
    assert project_for_game(client, ctx, 1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-13')['mu'] == pytest.approx(first['mu'])
    later = project_for_game(client, ctx, 1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-20')
    assert later['games'] == 4 and later['mu'] != pytest.approx(first['mu'])


def test_home_rest_and_opponent_factors_scale_the_projection():
    client = FakeClient()
    neutral = project_for_game(client, _context(), 1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-13')['mu']
    home = project_for_game(client, _context(multipliers={'home': 1.1, 'away': 0.9, 'b2b': 1.0, 'rested': 1.0}),
                            1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-13')['mu']
    away = project_for_game(client, _context(multipliers={'home': 1.1, 'away': 0.9, 'b2b': 1.0, 'rested': 1.0}),
                            1, 'Brad Marchand', 'L', False, 'PHI', '2026-10-13')['mu']
    assert home == pytest.approx(neutral * 1.1) and away == pytest.approx(neutral * 0.9)
    tired = project_for_game(client, _context(multipliers={'home': 1.0, 'away': 1.0, 'b2b': 0.9, 'rested': 1.0}),
                             1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-13')['mu']
    assert tired == pytest.approx(neutral * 0.9)
    leaky = project_for_game(client, _context(opponents={'PHI': 1.2}), 1, 'Brad Marchand', 'L', True, 'PHI', '2026-10-13')['mu']
    assert leaky == pytest.approx(neutral * 1.2 ** OPPONENT_WEIGHT)


def test_a_player_with_no_ice_time_history_at_all_gets_no_projection():
    client = FakeClient()
    client.logs[(2, '20252026')] = []
    result = project_for_game(client, _context(), 2, 'Rookie Guy', 'D', False, 'PHI', '2026-10-13')
    assert result is None


def test_event_players_are_matched_projected_and_unmatched_players_explained():
    client = FakeClient()
    by_team = candidates_by_team(client.skaters)
    lookup = team_lookup(TEAMS)
    base = {'event_id': 'e1', 'home_team': 'Boston Bruins', 'away_team': 'Philadelphia Flyers',
            'commence_time': '2026-10-17T23:00:00Z'}
    entries = [
        dict(base, player='Brad Marchand'), dict(base, player='Brad Marchand'),
        dict(base, player='Nobody Known'), dict(base, player='Brad Marchand', event_id='e2', home_team='Atlantis Sharks'),
        dict(base, player='Brad Marchand', event_id='e3', commence_time='soon'),
    ]
    out = project_event_players(client, _context(), by_team, lookup, entries)
    good = out[('e1', 'Brad Marchand')]
    assert good['mu'] > 0 and good['team'] == 'BOS' and good['opponent'] == 'PHI' and good['home'] is True
    assert good['matched_name'] == 'Brad Marchand' and good['method'] == 'exact' and good['games'] == 4
    assert out[('e1', 'Nobody Known')] == {'mu': None, 'reason': 'unmatched'}
    assert out[('e2', 'Brad Marchand')]['reason'] == 'team not recognised'
    assert out[('e3', 'Brad Marchand')]['reason'] == 'bad start time'
    assert len(out) == 4


def test_build_context_learns_baselines_multipliers_and_opponent_factors():
    ctx = build_context(FakeClient(), '20262027', '20252026', sample=10)
    assert set(ctx) == {'season', 'prior', 'baselines', 'multipliers', 'opponents'}
    assert ctx['baselines']['F'] > 0 and ctx['multipliers']['home'] > 0
    assert ctx['opponents']['BOS'] == pytest.approx(30 / 28.5) and ctx['opponents']['PHI'] == pytest.approx(27 / 28.5)

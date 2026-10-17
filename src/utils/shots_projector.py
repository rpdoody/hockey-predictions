"""Shots projection for upcoming games, built from the same walk-forward code the backtests tested.

Production setting: prior weight 300 and shrink 300 minutes, home/away and rest multipliers, and half-weight
opponent shot volume (the combination that scored best in the extra-inputs experiment). Multipliers and
opponent factors are learned from last season, so nothing here peeks at the games being predicted.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

from src.utils.name_match import match_player, team_abbrev
from src.utils.shooting_regression import position_group
from src.utils.season import to_eastern
from src.utils.shots_backtest import build_players, load_game_rows, position_baselines
from src.utils.shots_factors import make_adjuster, opponent_factors, pooled_multipliers
from src.utils.shots_model import walk_forward

PRODUCTION_SETTING = (300, 300)  # prior_minutes, prior_shrink
OPPONENT_WEIGHT = 0.5
DEFAULT_DISPERSION = 0.04        # spread measured in the backtests (about 0.04); re-measure as data grows


def build_context(client, season: str, prior: str, sample: int = 300) -> dict:
    """Everything the projector learns from last season: position baselines, multipliers and opponent factors."""
    players, _ = build_players(client, season, prior, limit=sample)
    baselines = position_baselines(client.get_skater_stats(season=prior, limit=-1, sort='shots'))
    team_rows = client.get_team_stats(prior).get('data', [])
    return {
        'season': season, 'prior': prior, 'baselines': baselines,
        'multipliers': pooled_multipliers(players),
        'opponents': opponent_factors(team_rows, client.ID_TO_TEAM_MAP),
    }


def candidates_by_team(skaters: List[dict]) -> Dict[str, List[dict]]:
    """Current-season skaters grouped by team abbreviation (a traded player appears under each of his teams)."""
    by_team: Dict[str, List[dict]] = {}
    for p in skaters:
        teams = [t.strip() for t in (p.get('team') or '').split(',') if t.strip()]
        entry = {'player_id': p.get('player_id'), 'name': p.get('name'), 'position': p.get('position'), 'teams': teams}
        for team in teams:
            by_team.setdefault(team, []).append(entry)
    return by_team


def project_for_game(
    client, context: dict, player_id: int, name: str, position: Optional[str],
    home: bool, opponent: str, game_date: str,
) -> Optional[dict]:
    """Expected shots for one player in one game, using only games played before game_date."""
    rows = [r for r in load_game_rows(client, player_id, context['season'], timedelta(hours=6)) if r['date'] < game_date]
    prior_rows = load_game_rows(client, player_id, context['prior'], timedelta(days=30))
    upcoming = {'date': game_date, 'shots': 0, 'minutes': 0.0, 'home': home, 'opponent': opponent}
    player = {
        'name': name, 'rows': rows + [upcoming], 'prior_rows': prior_rows,
        'baseline_rate': context['baselines'].get(position_group(position)),
    }
    adjust = make_adjuster(context['multipliers'], context['opponents'], home=True, rest=True, opponent_weight=OPPONENT_WEIGHT)
    predictions = walk_forward(
        [player], prior_minutes=PRODUCTION_SETTING[0], prior_shrink=PRODUCTION_SETTING[1], adjust=adjust,
    )
    if not predictions or predictions[-1]['date'] != game_date:
        return None
    last_game = rows[-1]['date'] if rows else None
    since = (date.fromisoformat(game_date) - date.fromisoformat(last_game)).days if last_game else None
    return {'mu': predictions[-1]['mu'], 'games': len(rows), 'last_game': last_game, 'days_since_last': since}


def project_event_players(client, context: dict, by_team: Dict[str, List[dict]], team_lookup: Dict[str, str], entries: List[dict]) -> dict:
    """Project every (event, player) in entries. Unmatched or unprojectable players get mu None and a reason."""
    out: dict = {}
    for entry in entries:
        key = (entry['event_id'], entry['player'])
        if key in out:
            continue
        home = team_abbrev(entry['home_team'], team_lookup)
        away = team_abbrev(entry['away_team'], team_lookup)
        if not home or not away:
            out[key] = {'mu': None, 'reason': 'team not recognised'}
            continue
        match, method = match_player(entry['player'], by_team.get(home, []) + by_team.get(away, []))
        if match is None:
            out[key] = {'mu': None, 'reason': method}
            continue
        teams = set(match['teams'])
        if home in teams and away in teams:
            out[key] = {'mu': None, 'reason': 'ambiguous team'}
            continue
        start = to_eastern(entry.get('commence_time') or '')
        if start is None:
            out[key] = {'mu': None, 'reason': 'bad start time'}
            continue
        is_home = home in teams
        try:
            result = project_for_game(
                client, context, match['player_id'], match['name'], match['position'], is_home,
                away if is_home else home, start.date().isoformat(),
            )
        except ConnectionError:
            result = None
        if result is None:
            out[key] = {'mu': None, 'reason': 'no data'}
            continue
        out[key] = dict(
            result, matched_name=match['name'], method=method, position=match['position'],
            team=home if is_home else away, opponent=away if is_home else home, home=is_home,
        )
    return out

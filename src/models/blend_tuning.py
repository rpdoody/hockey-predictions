'''Replay past seasons to choose how fast this season's goal rates should replace last season's.

For each game, both teams' goals for and against per game are blended from last season's
full-season rates and this season's games played so far, then run through the same expected
goals and win probability formulas the live model uses.
'''
import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from src.models.expected_goals import TeamMetrics, calculate_expected_goals
from src.models.season_blend import blend_team_metrics
from src.models.win_probability import calculate_win_probability

FINAL_STATES = {'OFF', 'FINAL'}
K_GRID = (0, 5, 10, 20, 30, 45, 60, 90, 150, 1e9)
BUCKETS = ((0, 9), (10, 19), (20, 39), (40, 400))


def regular_season_games(games: Iterable[dict]) -> List[dict]:
    '''Finished regular-season games with scores, one per game id, oldest first.

    A game that appears more than once is kept once: a repeat would be predicted after its
    own score had already been added to the team rates.
    '''
    kept, seen = [], set()
    for game in games:
        game_id = str(game.get('game_id', ''))
        if len(game_id) >= 6 and game_id[4:6] != '02':
            continue
        if game.get('game_state') not in FINAL_STATES:
            continue
        if game.get('home_score') is None or game.get('away_score') is None:
            continue
        if game_id:
            if game_id in seen:
                continue
            seen.add(game_id)
        kept.append(game)
    return sorted(kept, key=lambda g: (g.get('date') or '', g.get('start_time') or '', str(g.get('game_id'))))


def _sides(game: dict):
    yield game['home_team'], game['home_score'], game['away_score']
    yield game['away_team'], game['away_score'], game['home_score']


def season_rates(games: Iterable[dict]) -> Tuple[Dict[str, Tuple[float, float]], Tuple[float, float]]:
    '''({team: (goals for, goals against) per game}, league average) for a season.'''
    goals_for, goals_against, played = defaultdict(float), defaultdict(float), defaultdict(int)
    for game in games:
        for team, scored, allowed in _sides(game):
            goals_for[team] += scored
            goals_against[team] += allowed
            played[team] += 1
    rates = {t: (goals_for[t] / played[t], goals_against[t] / played[t]) for t in played}
    total = sum(played.values())
    league = (sum(goals_for.values()) / total, sum(goals_against.values()) / total) if total else (3.0, 3.0)
    return rates, league


def _metrics(team: str, goals_for: float, goals_against: float) -> TeamMetrics:
    return TeamMetrics(team, goals_for, goals_against, 30.0, 30.0, 20.0, 80.0)


def replay(
    games: List[dict], prior_rates: dict, league: Tuple[float, float], k: float,
    home_advantage: Optional[float] = None,
) -> List[dict]:
    '''Predict every game from last season blended with the games played so far.'''
    kwargs = {} if home_advantage is None else {'home_advantage': home_advantage}
    goals_for, goals_against, played = defaultdict(float), defaultdict(float), defaultdict(int)
    rows = []
    for game in games:
        built = {}
        for key in ('home_team', 'away_team'):
            team = game[key]
            prior_for, prior_against = prior_rates.get(team, league)
            n = played[team]
            now_for = goals_for[team] / n if n else prior_for
            now_against = goals_against[team] / n if n else prior_against
            built[key] = (
                blend_team_metrics(
                    _metrics(team, now_for, now_against), _metrics(team, prior_for, prior_against), n, k_goals=k,
                ),
                n,
            )
        (home_tm, home_n), (away_tm, away_n) = built['home_team'], built['away_team']
        home_xg, away_xg = calculate_expected_goals(home_tm, away_tm, **kwargs)
        p_home = calculate_win_probability(home_xg, away_xg).home_win
        home_won = game.get('home_won')
        if home_won is None:
            home_won = game['home_score'] > game['away_score']
        rows.append({
            'games_played': min(home_n, away_n), 'p_home': p_home, 'home_won': bool(home_won),
            'xg_total': home_xg + away_xg, 'goals': game['home_score'] + game['away_score'],
        })
        for team, scored, allowed in _sides(game):
            goals_for[team] += scored
            goals_against[team] += allowed
            played[team] += 1
    return rows


def log_loss(rows: List[dict]) -> Optional[float]:
    if not rows:
        return None
    eps = 1e-6
    total = 0.0
    for row in rows:
        p = min(max(row['p_home'], eps), 1 - eps)
        total += -math.log(p if row['home_won'] else 1 - p)
    return total / len(rows)


def total_error(rows: List[dict]) -> Optional[float]:
    '''Mean absolute error of the expected total against the final total.'''
    return sum(abs(r['xg_total'] - r['goals']) for r in rows) / len(rows) if rows else None


def by_bucket(rows: List[dict]) -> Dict[str, List[dict]]:
    '''Rows grouped by how many games the less-played team had already played.'''
    groups = {'{}-{}'.format(lo, hi if hi < 400 else '+'): [] for lo, hi in BUCKETS}
    for row in rows:
        for lo, hi in BUCKETS:
            if lo <= row['games_played'] <= hi:
                groups['{}-{}'.format(lo, hi if hi < 400 else '+')].append(row)
                break
    groups['All games'] = list(rows)
    return groups

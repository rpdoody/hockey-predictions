"""Walk-forward backtest of the shots projection on real game logs; needs no odds data."""
import time
from datetime import timedelta
from typing import Dict, List, Sequence, Tuple

from src.utils.shooting_regression import position_group
from src.utils.shots_model import evaluate, game_rows, walk_forward

GAME_LOG_URL = 'https://api-web.nhle.com/v1/player/{player_id}/game-log/{season}/2'
PRIOR_MINUTES_GRID = (100, 200, 300, 500, 800)


def previous_season_id(season_id: str) -> str:
    start = int(season_id[:4]) - 1
    return f'{start}{start + 1}'


def position_baselines(skaters: List[dict]) -> Dict[str, float]:
    """League shots per minute for forwards ('F') and defensemen ('D') from season summary rows."""
    shots: Dict[str, float] = {}
    minutes: Dict[str, float] = {}
    for p in skaters:
        toi = p.get('toi_pg') or 0
        games = p.get('games') or 0
        if toi <= 0 or games <= 0:
            continue
        group = position_group(p.get('position'))
        shots[group] = shots.get(group, 0) + (p.get('shots') or 0)
        minutes[group] = minutes.get(group, 0) + games * toi / 60
    return {g: shots[g] / minutes[g] for g in minutes if minutes[g] > 0}


def load_game_rows(client, player_id: int, season: str, ttl: timedelta) -> List[dict]:
    data = client._fetch_sync(GAME_LOG_URL.format(player_id=player_id, season=season), ttl=ttl)
    return game_rows(data.get('gameLog', []))


def build_players(client, season: str, prior_season: str, limit: int = 300, pause: float = 0.05) -> Tuple[List[dict], int]:
    """Last season's top shooters (chosen before this season, so the sample is not biased toward lucky starts)."""
    skaters = client.get_skater_stats(season=prior_season, limit=1000, sort='shots')
    baselines = position_baselines(skaters)
    players, skipped = [], 0
    for p in skaters[:limit]:
        try:
            rows = load_game_rows(client, p['player_id'], season, timedelta(hours=6))
            prior_rows = load_game_rows(client, p['player_id'], prior_season, timedelta(days=30))
        except ConnectionError:
            skipped += 1
            continue
        time.sleep(pause)
        if not rows:
            skipped += 1
            continue
        players.append({
            'name': p['name'], 'rows': rows, 'prior_rows': prior_rows,
            'baseline_rate': baselines.get(position_group(p.get('position'))),
        })
    return players, skipped


def run_backtest(players: List[dict], grid: Sequence[float] = PRIOR_MINUTES_GRID, lines: Sequence[float] = (1.5, 2.5, 3.5)) -> dict:
    """Try each prior weight, then compare the best against two naive predictors on the same games."""
    tried = {}
    for prior_minutes in grid:
        result = evaluate(walk_forward(players, prior_minutes=prior_minutes), 'mu', lines)
        tried[prior_minutes] = {'nb_log_likelihood': result['nb_log_likelihood'], 'mae': result['mae'], 'n': result['n']}
    best = max(tried, key=lambda k: tried[k]['nb_log_likelihood'])
    predictions = walk_forward(players, prior_minutes=best)
    common = [p for p in predictions if p['naive_prior'] and p['naive_to_date']]
    comparison = {key: evaluate(common, key, lines) for key in ('mu', 'naive_prior', 'naive_to_date')}
    return {
        'players': len(players), 'games': len(predictions), 'compared_games': len(common),
        'grid': tried, 'best_prior_minutes': best, 'comparison': comparison,
    }


def format_report(report: dict) -> str:
    out = [
        f"players: {report['players']} | games predicted: {report['games']} | games compared: {report['compared_games']}",
        '', 'prior_minutes  nb_log_likelihood   mae',
    ]
    for k, v in report['grid'].items():
        marker = '  <- best' if k == report['best_prior_minutes'] else ''
        out.append(f"{k:>13}  {v['nb_log_likelihood']:>17.4f}  {v['mae']:.3f}{marker}")
    out += ['', 'predictor        mae    nb_log_likelihood  spread']
    for key, e in report['comparison'].items():
        out.append(f"{key:<15} {e['mae']:.3f}  {e['nb_log_likelihood']:>17.4f}  {e['dispersion']:.3f}")
    out += ['', 'model over/under calibration (predicted vs observed over rate):']
    for line, v in report['comparison']['mu']['lines'].items():
        out.append(f"  line {line}: predicted {v['predicted_over']:.3f} | observed {v['observed_over']:.3f} | log loss {v['log_loss']:.4f}")
    return '\n'.join(out)

"""Walk-forward backtest of the shots projection on real game logs; needs no odds data."""
import time
from datetime import timedelta
from itertools import product
from typing import Dict, List, Sequence, Tuple

from src.utils.shooting_regression import position_group
from src.utils.shots_model import evaluate, game_rows, paired_loglik_gap, walk_forward

GAME_LOG_URL = 'https://api-web.nhle.com/v1/player/{player_id}/game-log/{season}/2'
PRIOR_MINUTES_GRID = (100, 300, 800, 1500, 3000)
PRIOR_SHRINK_GRID = (0, 300, 1000, 2000)
DEFAULT_SETTING = (300, 0)


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
    skaters = client.get_skater_stats(season=prior_season, limit=-1, sort='shots')
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


def run_backtest(
    players: List[dict],
    prior_grid: Sequence[float] = PRIOR_MINUTES_GRID,
    shrink_grid: Sequence[float] = PRIOR_SHRINK_GRID,
    lines: Sequence[float] = (1.5, 2.5, 3.5),
) -> dict:
    """Choose settings on the earlier half of the games, then judge them on the later half.

    Picking the best of many settings and scoring it on the same games would flatter it, so the
    comparison against the naive predictors uses only games after the cutoff date.
    """
    settings = set(product(prior_grid, shrink_grid)) | {DEFAULT_SETTING}
    runs = {s: walk_forward(players, prior_minutes=s[0], prior_shrink=s[1]) for s in settings}
    any_run = next(iter(runs.values()))
    dates = sorted({p['date'] for p in any_run})
    cutoff = dates[len(dates) // 2]

    selection = {}
    for setting, preds in runs.items():
        early = [p for p in preds if p['date'] <= cutoff]
        if early:
            selection[setting] = evaluate(early, 'mu', lines)['nb_log_likelihood']
    best = max(selection, key=selection.get)

    default_mu = {(p['player'], p['date']): p['mu'] for p in runs[DEFAULT_SETTING]}
    holdout = []
    for p in runs[best]:
        if p['date'] > cutoff and p['naive_prior'] and p['naive_to_date']:
            holdout.append(dict(p, mu_default=default_mu[(p['player'], p['date'])]))
    comparison = {
        'model (best setting)': evaluate(holdout, 'mu', lines),
        'model (default setting)': evaluate(holdout, 'mu_default', lines),
        'last season average': evaluate(holdout, 'naive_prior', lines),
        'season-to-date average': evaluate(holdout, 'naive_to_date', lines),
    }
    return {
        'players': len(players), 'games': len(any_run), 'cutoff': cutoff, 'holdout_games': len(holdout),
        'prior_grid': list(prior_grid), 'shrink_grid': list(shrink_grid), 'selection': selection,
        'best': best, 'comparison': comparison,
        'gap_vs_last_season': paired_loglik_gap(holdout, 'mu', 'naive_prior'),
        'gap_vs_default': paired_loglik_gap(holdout, 'mu', 'mu_default'),
    }


def _gap_text(gap) -> str:
    if gap is None:
        return 'not enough games'
    verdict = 'no clear difference' if gap['low'] <= 0 <= gap['high'] else ('model better' if gap['mean'] > 0 else 'model worse')
    return f"{gap['mean']:+.4f} (95% range {gap['low']:+.4f} to {gap['high']:+.4f}) -> {verdict}"


def format_report(report: dict) -> str:
    out = [
        f"players: {report['players']} | games predicted: {report['games']} | holdout games (after {report['cutoff']}): {report['holdout_games']}",
        '', 'settings chosen on earlier games (nb log likelihood; rows = prior_minutes, columns = prior_shrink):',
        'prior_minutes ' + ' '.join(f'{s:>9}' for s in report['shrink_grid']),
    ]
    for pm in report['prior_grid']:
        cells = ' '.join(f"{report['selection'][(pm, s)]:>9.4f}" if (pm, s) in report['selection'] else f"{'-':>9}" for s in report['shrink_grid'])
        out.append(f'{pm:>13} {cells}')
    best = report['best']
    out += ['', f'best setting: prior_minutes={best[0]}, prior_shrink={best[1]}',
            '', 'holdout comparison:', 'predictor                   n    mae   nb_ll   mean pred  mean actual']
    for name, e in report['comparison'].items():
        out.append(f"{name:<25} {e['n']:>5} {e['mae']:.3f} {e['nb_log_likelihood']:.4f}  {e['mean_predicted']:>9.3f}  {e['mean_actual']:>11.3f}")
    out += ['', 'paired log likelihood gap per game (positive = model better):',
            f"  vs last season average: {_gap_text(report['gap_vs_last_season'])}",
            f"  vs default setting:     {_gap_text(report['gap_vs_default'])}",
            '', 'best model over/under calibration on holdout (predicted vs observed over rate):']
    for line, v in report['comparison']['model (best setting)']['lines'].items():
        out.append(f"  line {line}: predicted {v['predicted_over']:.3f} | observed {v['observed_over']:.3f} | log loss {v['log_loss']:.4f}")
    return '\n'.join(out)

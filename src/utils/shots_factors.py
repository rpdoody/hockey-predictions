"""Extra inputs for the shots projection: home/away, back-to-back and opponent shot volume.

Every multiplier is learned from LAST season's data, so testing it on this season's games is out of sample.
"""
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence

from src.utils.shots_model import evaluate, paired_loglik_gap, walk_forward

BASE_SETTING = (300, 300)  # prior_minutes, prior_shrink (the backtest's best so far)


def back_to_back(previous_date: Optional[str], this_date: Optional[str]) -> Optional[bool]:
    """True when the previous game was the day before; None when a date is missing."""
    try:
        return (date.fromisoformat(this_date) - date.fromisoformat(previous_date)).days == 1
    except (TypeError, ValueError):
        return None


def pooled_multipliers(players: List[dict]) -> Dict[str, float]:
    """Shots per minute in each situation relative to all games, pooled over last season's logs."""
    buckets: Dict[str, List[float]] = {'home': [0.0, 0.0], 'away': [0.0, 0.0], 'b2b': [0.0, 0.0], 'rested': [0.0, 0.0]}
    total_shots = total_minutes = 0.0
    for player in players:
        rows = player.get('prior_rows') or []
        for i, row in enumerate(rows):
            shots, minutes = row['shots'], row['minutes']
            total_shots += shots
            total_minutes += minutes
            where = buckets['home' if row.get('home') else 'away']
            where[0] += shots
            where[1] += minutes
            if i > 0:
                flag = back_to_back(rows[i - 1].get('date'), row.get('date'))
                if flag is not None:
                    rest = buckets['b2b' if flag else 'rested']
                    rest[0] += shots
                    rest[1] += minutes
    if total_minutes <= 0:
        return {}
    overall = total_shots / total_minutes
    return {name: (s / m) / overall for name, (s, m) in buckets.items() if m > 0}


def opponent_factors(team_rows: List[dict], id_to_abbrev: Dict[int, str]) -> Dict[str, float]:
    """Each team's shots allowed per game relative to the league average (above 1 means it allows more)."""
    allowed = {}
    for row in team_rows:
        abbrev = id_to_abbrev.get(row.get('teamId'))
        value = row.get('shotsAgainstPerGame')
        if abbrev and value:
            allowed[abbrev] = value
    if not allowed:
        return {}
    league = sum(allowed.values()) / len(allowed)
    return {abbrev: value / league for abbrev, value in allowed.items()}


def make_adjuster(
    multipliers: Dict[str, float], opponents: Dict[str, float],
    home: bool = False, rest: bool = False, opponent_weight: float = 0.0,
) -> Callable:
    """Build the projection multiplier for walk_forward from the chosen extra inputs."""
    def adjust(player, row, history):
        factor = 1.0
        if home:
            factor *= multipliers.get('home' if row.get('home') else 'away', 1.0)
        if rest and history:
            flag = back_to_back(history[-1].get('date'), row.get('date'))
            if flag is not None:
                factor *= multipliers.get('b2b' if flag else 'rested', 1.0)
        if opponent_weight:
            factor *= opponents.get(row.get('opponent'), 1.0) ** opponent_weight
        return factor
    return adjust


VARIANTS = {
    '+ home/away': dict(home=True),
    '+ back-to-back': dict(rest=True),
    '+ opponent (half weight)': dict(opponent_weight=0.5),
    '+ opponent (full weight)': dict(opponent_weight=1.0),
    '+ all three (half-weight opponent)': dict(home=True, rest=True, opponent_weight=0.5),
}


def run_factor_experiment(players: List[dict], multipliers: Dict[str, float], opponents: Dict[str, float], setting=BASE_SETTING) -> dict:
    """Score each extra input against the base model on every game, using the paired log likelihood gap."""
    prior_minutes, prior_shrink = setting
    base = walk_forward(players, prior_minutes=prior_minutes, prior_shrink=prior_shrink)
    results = {'base model': {'eval': evaluate(base, 'mu'), 'gap': None}}
    for name, options in VARIANTS.items():
        adjust = make_adjuster(multipliers, opponents, **options)
        variant = walk_forward(players, prior_minutes=prior_minutes, prior_shrink=prior_shrink, adjust=adjust)
        assert [(p['player'], p['date']) for p in variant] == [(p['player'], p['date']) for p in base]
        rows = [dict(v, mu_base=b['mu']) for v, b in zip(variant, base)]
        results[name] = {'eval': evaluate(variant, 'mu'), 'gap': paired_loglik_gap(rows, 'mu', 'mu_base')}
    return {'games': len(base), 'multipliers': multipliers, 'opponents': opponents, 'results': results}


MEANINGFUL_GAIN = 0.001  # per-game log likelihood; smaller differences are treated as negligible


def _verdict(gap) -> str:
    if gap is None:
        return ''
    if abs(gap['mean']) < MEANINGFUL_GAIN:
        return 'negligible difference'
    if gap['low'] > 0:
        return 'clearly better'
    if gap['high'] < 0:
        return 'clearly worse'
    return 'no clear difference'


def format_experiment(report: dict) -> str:
    m = report['multipliers']
    out = [
        f"games scored: {report['games']} (multipliers learned from last season, so every game is out of sample)",
        'learned multipliers (shots per minute vs overall): ' + ', '.join(f'{k} {v:.3f}' for k, v in sorted(m.items())),
    ]
    if report['opponents']:
        ranked = sorted(report['opponents'].items(), key=lambda kv: kv[1])
        out.append('opponent shots allowed vs league: fewest ' + ', '.join(f'{k} {v:.2f}' for k, v in ranked[:3])
                   + ' | most ' + ', '.join(f'{k} {v:.2f}' for k, v in ranked[-3:]))
    out += ['', 'variant                                mean pred  mean actual   nb_ll    gain vs base (95% range)']
    for name, item in report['results'].items():
        e, gap = item['eval'], item['gap']
        tail = '' if gap is None else f"{gap['mean']:+.4f} ({gap['low']:+.4f} to {gap['high']:+.4f})  {_verdict(gap)}"
        out.append(f"{name:<36} {e['mean_predicted']:>9.3f} {e['mean_actual']:>11.3f}  {e['nb_log_likelihood']:.4f}  {tail}")
    out += ['', 'Five variants are compared on the same games, so about one in twenty "clear" results can be luck.',
            'Trust a variant only if its range is clearly above zero and its learned multiplier makes sense.']
    return '\n'.join(out)

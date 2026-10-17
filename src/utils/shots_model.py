"""Shots-on-goal projection: shrunk per-minute rate x projected ice time, with negative binomial spread."""
import math
from typing import Dict, List, Optional, Sequence

PRIOR_MINUTES = 300.0     # weight of the prior rate, in minutes of ice time (assumption; tune with the backtest)
MIN_PRIOR_MINUTES = 300.0  # last-season ice time needed before trusting that player's own prior rate
TOI_SMOOTHING = 0.25      # weight on the newest game when projecting ice time


def parse_toi(value) -> Optional[float]:
    """'16:10' -> 16.17 minutes; None when missing or malformed."""
    try:
        minutes, seconds = str(value).split(':')
        return int(minutes) + int(seconds) / 60
    except (ValueError, AttributeError):
        return None


def game_rows(game_log: List[dict]) -> List[dict]:
    """Per-game rows, oldest first, from an api-web game log. Games without ice time are skipped."""
    rows = []
    for game in game_log:
        minutes = parse_toi(game.get('toi'))
        if not minutes:
            continue
        rows.append({
            'date': game.get('gameDate'), 'shots': game.get('shots', 0) or 0, 'minutes': minutes,
            'opponent': game.get('opponentAbbrev'), 'home': game.get('homeRoadFlag') == 'H',
        })
    return sorted(rows, key=lambda r: r['date'] or '')


def season_rate(rows: Sequence[dict]) -> Optional[float]:
    """Shots per minute over the given games."""
    minutes = sum(r['minutes'] for r in rows)
    return sum(r['shots'] for r in rows) / minutes if minutes > 0 else None


def blended_rate(history: Sequence[dict], prior_rate: Optional[float], prior_minutes: float = PRIOR_MINUTES) -> Optional[float]:
    """This season's shots per minute pulled toward a prior rate; the prior counts as prior_minutes of evidence."""
    shots = sum(r['shots'] for r in history)
    minutes = sum(r['minutes'] for r in history)
    if prior_rate is None:
        return shots / minutes if minutes > 0 else None
    return (shots + prior_minutes * prior_rate) / (minutes + prior_minutes)


def project_minutes(history: Sequence[dict], prior_avg_minutes: Optional[float], smoothing: float = TOI_SMOOTHING) -> Optional[float]:
    """Exponentially weighted ice time, seeded with last season's average."""
    level = prior_avg_minutes
    for row in history:
        level = row['minutes'] if level is None else smoothing * row['minutes'] + (1 - smoothing) * level
    return level


def project_shots(
    history: Sequence[dict], prior_rate: Optional[float], prior_avg_minutes: Optional[float],
    prior_minutes: float = PRIOR_MINUTES, smoothing: float = TOI_SMOOTHING,
) -> Optional[float]:
    """Expected shots on goal for the next game, or None with no usable data."""
    rate = blended_rate(history, prior_rate, prior_minutes)
    minutes = project_minutes(history, prior_avg_minutes, smoothing)
    if rate is None or minutes is None:
        return None
    return rate * minutes


def nb_pmf(k: int, mean: float, dispersion: float) -> float:
    """Negative binomial with variance mean + dispersion * mean^2 (Poisson when dispersion is ~0)."""
    if mean <= 0:
        return 1.0 if k == 0 else 0.0
    if dispersion <= 1e-9:
        return math.exp(k * math.log(mean) - mean - math.lgamma(k + 1))
    r = 1.0 / dispersion
    return math.exp(
        math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
        + r * math.log(r / (r + mean)) + k * math.log(mean / (r + mean))
    )


def prob_over(mean: float, dispersion: float, line: float) -> float:
    """P(shots > line) for a half-point line such as 2.5 (no push is possible)."""
    need = math.floor(line) + 1
    return min(1.0, max(0.0, 1.0 - sum(nb_pmf(k, mean, dispersion) for k in range(need))))


def estimate_dispersion(means: Sequence[float], actuals: Sequence[float]) -> float:
    """Method-of-moments spread: how much more variable shots are than a Poisson with the projected mean."""
    excess = sum((y - m) ** 2 - m for m, y in zip(means, actuals))
    scale = sum(m * m for m in means)
    return max(0.0, excess / scale) if scale > 0 else 0.0


def american_to_prob(price: float) -> float:
    return 100.0 / (price + 100.0) if price > 0 else -price / (-price + 100.0)


def devig_two_way(over_price: float, under_price: float) -> dict:
    """Fair over/under probabilities with the bookmaker margin removed proportionally."""
    over, under = american_to_prob(over_price), american_to_prob(under_price)
    total = over + under
    return {'p_over': over / total, 'p_under': under / total, 'overround': total - 1.0}


def expected_value(prob: float, price: float) -> float:
    """Expected profit per unit staked at American odds `price` when the true win probability is `prob`."""
    profit = price / 100.0 if price > 0 else 100.0 / -price
    return prob * profit - (1.0 - prob)


def walk_forward(players: List[dict], prior_minutes: float = PRIOR_MINUTES, smoothing: float = TOI_SMOOTHING) -> List[dict]:
    """Predict every game from only the games before it.

    Each player dict: name, rows (this season), prior_rows (last season), baseline_rate (fallback shots per minute).
    """
    out = []
    for player in players:
        prior_rows = player.get('prior_rows') or []
        prior_total = sum(r['minutes'] for r in prior_rows)
        prior_rate = season_rate(prior_rows) if prior_total >= MIN_PRIOR_MINUTES else player.get('baseline_rate')
        prior_avg_minutes = prior_total / len(prior_rows) if prior_rows else None
        prior_per_game = sum(r['shots'] for r in prior_rows) / len(prior_rows) if prior_rows else None
        rows = player['rows']
        for i, row in enumerate(rows):
            history = rows[:i]
            mu = project_shots(history, prior_rate, prior_avg_minutes, prior_minutes, smoothing)
            if mu is None:
                continue
            to_date = sum(r['shots'] for r in history) / len(history) if history else prior_per_game
            out.append({
                'player': player['name'], 'date': row['date'], 'actual': row['shots'],
                'mu': mu, 'naive_prior': prior_per_game, 'naive_to_date': to_date,
            })
    return out


def evaluate(predictions: List[dict], key: str = 'mu', lines: Sequence[float] = (1.5, 2.5, 3.5)) -> dict:
    """Error, fit and over/under calibration for one prediction column, using its own fitted spread."""
    rows = [p for p in predictions if p.get(key) is not None and p[key] > 0]
    means, actuals = [p[key] for p in rows], [p['actual'] for p in rows]
    dispersion = estimate_dispersion(means, actuals)
    n = len(rows)
    result = {
        'n': n, 'dispersion': dispersion,
        'mae': sum(abs(m - y) for m, y in zip(means, actuals)) / n,
        'nb_log_likelihood': sum(math.log(max(nb_pmf(int(y), m, dispersion), 1e-12)) for m, y in zip(means, actuals)) / n,
        'lines': {},
    }
    for line in lines:
        predicted = [prob_over(m, dispersion, line) for m in means]
        hits = [1.0 if y > line else 0.0 for y in actuals]
        result['lines'][line] = {
            'predicted_over': sum(predicted) / n, 'observed_over': sum(hits) / n,
            'log_loss': -sum(math.log(min(max(p if h else 1 - p, 1e-9), 1.0)) for p, h in zip(predicted, hits)) / n,
        }
    return result

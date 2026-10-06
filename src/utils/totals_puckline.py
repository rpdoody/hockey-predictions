'''Model totals and puck lines, then grade them against final scores.

Goals are Poisson from the logged expected goals. A tied game goes to overtime:
an overtime goal adds one to the total, a shootout adds nothing to the total
(sportsbooks ignore the shootout goal), and either way the winner's margin is one.
'''
import math
from collections import defaultdict
from itertools import product
from typing import Callable, List, Optional

from src.utils.performance import (
    STAKE, _latest_entries, _parse_time, _stage, parse_american, win_profit,
)

MAX_GOALS = 14
OT_SHARE = 0.6
MIN_EDGE = 0.03
ALL_GAMES = 'All games'


def _pmf(rate: float) -> list:
    values = [math.exp(-rate)]
    for k in range(1, MAX_GOALS + 1):
        values.append(values[-1] * rate / k)
    return values


def model_distribution(home_xg: float, away_xg: float, ot_share: float = OT_SHARE) -> dict:
    '''Settled total-goal and home-margin probabilities for one game.'''
    home_pmf, away_pmf = _pmf(home_xg), _pmf(away_xg)
    home_takes_tie = home_xg / (home_xg + away_xg)
    totals, margins = defaultdict(float), defaultdict(float)
    for h, a in product(range(MAX_GOALS + 1), repeat=2):
        p = home_pmf[h] * away_pmf[a]
        if h == a:
            totals[2 * h] += p * (1 - ot_share)
            totals[2 * h + 1] += p * ot_share
            margins[1] += p * home_takes_tie
            margins[-1] += p * (1 - home_takes_tie)
        else:
            totals[h + a] += p
            margins[h - a] += p
    norm = sum(totals.values())
    return {
        'totals': {k: v / norm for k, v in totals.items()},
        'margins': {k: v / norm for k, v in margins.items()},
    }


def total_probs(dist: dict, line: float) -> tuple:
    '''(over, under, push) probabilities for a total line.'''
    over = sum(p for t, p in dist['totals'].items() if t > line)
    under = sum(p for t, p in dist['totals'].items() if t < line)
    return over, under, 1 - over - under


def spread_probs(dist: dict, home_line: float) -> tuple:
    '''(home covers, away covers, push) for the home team's puck line.'''
    home = sum(p for m, p in dist['margins'].items() if m + home_line > 0)
    away = sum(p for m, p in dist['margins'].items() if m + home_line < 0)
    return home, away, 1 - home - away


def implied_prob(odds: int) -> float:
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)


def fair_two_way(odds_a: int, odds_b: int) -> float:
    '''Vig-free probability of side A from both prices.'''
    a, b = implied_prob(odds_a), implied_prob(odds_b)
    return a / (a + b)


def settled_totals(score: dict) -> set:
    '''Totals a sportsbook could have settled on; a shootout goal never counts.'''
    home, away = score['home_goals'], score['away_goals']
    total, kind = home + away, score.get('period_type')
    if kind == 'SO':
        return {total - 1}
    if kind in ('REG', 'OT'):
        return {total}
    return {total, total - 1} if abs(home - away) == 1 else {total}


def total_outcome(score: dict, line: float) -> Optional[str]:
    '''over, under or push; None when the shootout question changes the answer.'''
    results = {('over' if t > line else 'under' if t < line else 'push') for t in settled_totals(score)}
    return results.pop() if len(results) == 1 else None


def spread_outcome(score: dict, home_line: float) -> str:
    margin = score['home_goals'] - score['away_goals'] + home_line
    return 'home' if margin > 0 else 'away' if margin < 0 else 'push'


def home_spread_line(snapshot: dict) -> tuple:
    '''(home line, source). Without a stored line, the moneyline favourite lays 1.5.'''
    stored = snapshot.get('home_pl_line')
    if stored is not None:
        return float(stored), 'stored'
    home_ml, away_ml = snapshot.get('home_ml'), snapshot.get('away_ml')
    if home_ml is None or away_ml is None:
        return None, None
    home_p, away_p = implied_prob(home_ml), implied_prob(away_ml)
    if home_p == away_p:
        return None, None
    return (-1.5 if home_p > away_p else 1.5), 'inferred'


def snapshot_at(history: Optional[dict], moment) -> Optional[dict]:
    '''Latest odds snapshot taken at or before the moment the pick was logged.'''
    if not history or moment is None:
        return None
    chosen = None
    for snap in history.get('snapshots', []):
        taken = _parse_time(snap.get('timestamp'))
        if taken is not None and taken <= moment:
            chosen = snap
    return chosen


def _grade(base, market, line, source, labels, odds, probs, winner, min_edge, stake):
    odds_a, odds_b = odds
    p_a, p_b = probs[0], probs[1]
    if odds_a is None or odds_b is None or p_a + p_b <= 0:
        return None
    model_a = p_a / (p_a + p_b)
    market_a = fair_two_way(odds_a, odds_b)
    side_a = model_a >= market_a
    edge = abs(model_a - market_a)
    row = {
        **base, 'market': market, 'line': line, 'line_source': source,
        'model_p': model_a, 'market_p': market_a, 'edge': edge,
        'bet_side': labels[0] if side_a else labels[1],
        'bet_odds': odds_a if side_a else odds_b,
        'outcome': None, 'bet_result': None, 'profit': None,
    }
    if winner is None and base['has_score']:
        row['status'] = 'ungradable'
        return row
    if winner is None:
        row['status'] = 'pending'
        return row
    row['status'] = 'graded'
    if winner != 'push':
        row['outcome'] = int(winner == 'a')
    if edge >= min_edge:
        if winner == 'push':
            row['bet_result'], row['profit'] = 'push', 0.0
        elif (winner == 'a') == side_a:
            row['bet_result'], row['profit'] = 'win', win_profit(row['bet_odds'], stake)
        else:
            row['bet_result'], row['profit'] = 'loss', -stake
    return row


def grade_games(
    entries: List[dict], scores: dict, get_history: Callable,
    min_edge: float = MIN_EDGE, ot_share: float = OT_SHARE, stake: float = STAKE,
) -> List[dict]:
    '''One row per game and market (total, puck line) with model, market and result.'''
    rows = []
    for game_date in sorted({e.get('game_date') for e in entries if e.get('game_date')}):
        for away, home, entry in _latest_entries(entries, game_date):
            home_xg, away_xg = entry.get('home_xg'), entry.get('away_xg')
            if home_xg is None or away_xg is None or home_xg + away_xg <= 0:
                continue
            snap = snapshot_at(get_history(str(entry.get('espn_game_id'))), _parse_time(entry.get('logged_at')))
            if snap is None:
                continue
            score = scores.get('{}|{}|{}'.format(game_date, home, away))
            dist = model_distribution(home_xg, away_xg, ot_share)
            base = {
                'date': game_date, 'game': '{} @ {}'.format(away, home),
                'stage': _stage(entry), 'has_score': score is not None,
            }
            line = snap.get('total')
            if line is not None:
                winner = None
                if score is not None:
                    result = total_outcome(score, line)
                    winner = {'over': 'a', 'under': 'b', 'push': 'push'}.get(result)
                row = _grade(
                    base, 'Total', line, 'stored', ('Over', 'Under'),
                    (snap.get('over_odds'), snap.get('under_odds')),
                    total_probs(dist, line), winner, min_edge, stake,
                )
                if row:
                    rows.append(row)
            home_line, source = home_spread_line(snap)
            if home_line is not None:
                winner = None
                if score is not None:
                    winner = {'home': 'a', 'away': 'b', 'push': 'push'}[spread_outcome(score, home_line)]
                labels = ('{} {:+g}'.format(home, home_line), '{} {:+g}'.format(away, -home_line))
                row = _grade(
                    base, 'Puck line', home_line, source, labels,
                    (snap.get('home_pl_odds'), snap.get('away_pl_odds')),
                    spread_probs(dist, home_line), winner, min_edge, stake,
                )
                if row:
                    rows.append(row)
    return rows


def _log_loss(pairs: list) -> Optional[float]:
    if not pairs:
        return None
    eps = 1e-6
    total = 0.0
    for p, y in pairs:
        p = min(max(p, eps), 1 - eps)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(pairs)


def summarize(rows: List[dict], stake: float = STAKE) -> List[dict]:
    '''Display rows per market and segment, graded games only.'''
    groups = {}
    for row in rows:
        if row['status'] != 'graded':
            continue
        for segment in (ALL_GAMES, row['stage']):
            groups.setdefault((row['market'], segment), []).append(row)
    table = []
    for (market, segment), items in sorted(groups.items()):
        decided = [r for r in items if r['outcome'] is not None]
        bets = [r for r in items if r['bet_result']]
        wins = sum(r['bet_result'] == 'win' for r in bets)
        losses = sum(r['bet_result'] == 'loss' for r in bets)
        pushes = len(bets) - wins - losses
        profit = sum(r['profit'] for r in bets)
        staked = stake * (wins + losses)
        table.append({
            'Market': market, 'Segment': segment, 'Games': len(decided),
            'Log loss: model': _log_loss([(r['model_p'], r['outcome']) for r in decided]),
            'Log loss: market': _log_loss([(r['market_p'], r['outcome']) for r in decided]),
            'Bets': len(bets), 'Record': '{}-{}-{}'.format(wins, losses, pushes),
            'Profit': profit, 'ROI': profit / staked if staked else None,
        })
    return table

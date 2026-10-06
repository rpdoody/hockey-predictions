'''Score logged model picks against final results and closing odds.'''
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.utils.odds_parse import parse_price

FINAL_STATES = {'FINAL', 'OFF'}
EARLY_GAMES = 20
_EPS = 1e-6


def _mean(values):
    return sum(values) / len(values)


def american_to_prob(price) -> Optional[float]:
    '''Implied probability (vig included) from American odds.'''
    ml = parse_price(price)
    if ml is None:
        return None
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def fair_home_prob(home_ml, away_ml) -> Optional[float]:
    '''Vig-free home win probability from a two-way moneyline.'''
    home, away = american_to_prob(home_ml), american_to_prob(away_ml)
    if home is None or away is None:
        return None
    return home / (home + away)


def bet_profit(price, won: bool) -> float:
    '''Profit in units for a 1-unit stake at American odds.'''
    if not won:
        return -1.0
    ml = parse_price(price)
    return ml / 100 if ml > 0 else 100 / -ml


def parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def result_key(date: str, home: str, away: str) -> str:
    return f'{date}|{home}|{away}'


def parse_schedule(payload: dict) -> dict:
    '''Final scores from an NHL schedule response, keyed by date|home|away.'''
    results = {}
    for day in payload.get('gameWeek', []):
        day_date = day.get('date')
        for game in day.get('games', []):
            if game.get('gameState') not in FINAL_STATES or not day_date:
                continue
            home = game.get('homeTeam', {})
            away = game.get('awayTeam', {})
            home_goals, away_goals = home.get('score'), away.get('score')
            if home_goals is None or away_goals is None or home_goals == away_goals:
                continue
            key = result_key(day_date, home.get('abbrev'), away.get('abbrev'))
            entry = {'home_goals': home_goals, 'away_goals': away_goals}
            period_type = (game.get('gameOutcome') or {}).get('lastPeriodType')
            if period_type in ('REG', 'OT', 'SO'):
                entry['period_type'] = period_type
            results[key] = entry
    return results


def lookup_result(results: dict, date: str, home: str, away: str) -> Optional[dict]:
    '''Find a final score by exact game date and NHL team codes.'''
    return results.get(result_key(date, home, away))


def select_records(rows: list, which: str = 'last') -> list:
    '''One pre-game log record per game: the first or last logged before the start.'''
    best = {}
    for row in rows:
        game_id = row.get('espn_game_id')
        start = parse_dt(row.get('start_utc'))
        logged = parse_dt(row.get('logged_at'))
        if not game_id or start is None or logged is None or logged >= start:
            continue
        current = best.get(game_id)
        if current is None:
            best[game_id] = (logged, row)
        elif (logged < current[0]) if which == 'first' else (logged > current[0]):
            best[game_id] = (logged, row)
    return [row for _, row in best.values()]


def closing_prices(history: Optional[dict], start_utc) -> Optional[tuple]:
    '''Last moneyline pair captured before the game started.'''
    start = parse_dt(start_utc)
    if not history or start is None:
        return None
    last = None
    for snap in history.get('snapshots', []):
        stamp = parse_dt(snap.get('timestamp'))
        if stamp is None or stamp >= start:
            continue
        if snap.get('home_ml') is None or snap.get('away_ml') is None:
            continue
        last = snap
    return (last['home_ml'], last['away_ml']) if last else None


def segment(record: dict) -> str:
    if record.get('prior_only'):
        return 'prior_only'
    played = [record.get('home_games_played'), record.get('away_games_played')]
    if any(g is None for g in played):
        return 'unknown'
    return 'early' if min(played) < EARLY_GAMES else 'established'


def _make_bet(record, p_used, fair, home_won, closing, min_edge):
    if p_used is None:
        return None
    candidates = []
    sides = (
        ('home', record.get('home_ml'), p_used),
        ('away', record.get('away_ml'), 1 - p_used),
    )
    for side, price, prob in sides:
        implied = american_to_prob(price)
        if implied is not None and prob - implied >= min_edge:
            candidates.append((prob - implied, side, parse_price(price)))
    if not candidates:
        return None
    edge, side, ml = max(candidates)
    won = home_won if side == 'home' else not home_won
    bet = {
        'side': side, 'price': ml, 'edge': edge, 'won': won,
        'profit': bet_profit(ml, won), 'clv': None,
    }
    if fair is not None and closing is not None:
        close_fair = fair_home_prob(*closing)
        if close_fair is not None:
            bet_fair = fair if side == 'home' else 1 - fair
            close_side = close_fair if side == 'home' else 1 - close_fair
            bet['clv'] = close_side - bet_fair
    return bet


def build_entries(records, results, history_for, min_edge=0.03):
    entries, pending = [], 0
    for record in records:
        home, away = record.get('home_team'), record.get('away_team')
        result = lookup_result(results, record.get('game_date'), home, away)
        if result is None:
            pending += 1
            continue
        home_won = result['home_goals'] > result['away_goals']
        p_used = record.get('home_win_prob_used')
        fair = fair_home_prob(record.get('home_ml'), record.get('away_ml'))
        closing = closing_prices(history_for(record.get('espn_game_id')), record.get('start_utc'))
        entries.append({
            'game_id': record.get('espn_game_id'),
            'date': record.get('game_date'),
            'home': home,
            'away': away,
            'segment': segment(record),
            'home_won': 1 if home_won else 0,
            'p_raw': record.get('home_win_prob_raw'),
            'p_used': p_used,
            'p_market': fair,
            'bet': _make_bet(record, p_used, fair, home_won, closing, min_edge),
        })
    return entries, pending


def _clip(p):
    return min(max(p, _EPS), 1 - _EPS)


def prob_metrics(entries):
    keys = ('p_raw', 'p_used', 'p_market')
    common = [e for e in entries if all(e[k] is not None for k in keys)]
    out = {'n': len(common)}
    for key in keys:
        if not common:
            out[key] = None
            continue
        brier = _mean([(e[key] - e['home_won']) ** 2 for e in common])
        loss = -_mean([
            e['home_won'] * math.log(_clip(e[key]))
            + (1 - e['home_won']) * math.log(1 - _clip(e[key]))
            for e in common
        ])
        out[key] = {'brier': round(brier, 4), 'log_loss': round(loss, 4)}
    return out


def bet_metrics(entries):
    bets = [e['bet'] for e in entries if e['bet']]
    if not bets:
        return {'n': 0}
    wins = sum(1 for b in bets if b['won'])
    units = sum(b['profit'] for b in bets)
    clvs = [b['clv'] for b in bets if b['clv'] is not None]
    return {
        'n': len(bets),
        'wins': wins,
        'hit_rate': round(wins / len(bets), 4),
        'units': round(units, 2),
        'roi': round(units / len(bets), 4),
        'avg_edge': round(_mean([b['edge'] for b in bets]), 4),
        'clv_n': len(clvs),
        'avg_clv': round(_mean(clvs), 4) if clvs else None,
    }


def _summary(entries):
    return {'probabilities': prob_metrics(entries), 'bets': bet_metrics(entries)}


def score(rows, results, history_for, min_edge=0.03, which='last') -> dict:
    '''Score pre-game log records against final results.'''
    records = select_records(rows, which)
    entries, pending = build_entries(records, results, history_for, min_edge)
    report = {
        'which': which,
        'min_edge': min_edge,
        'games_logged': len(records),
        'games_scored': len(entries),
        'games_pending': pending,
        'overall': _summary(entries),
        'by_segment': {},
    }
    for name in ('prior_only', 'early', 'established', 'unknown'):
        subset = [e for e in entries if e['segment'] == name]
        if subset:
            report['by_segment'][name] = _summary(subset)
    return report


def _describe(name, summary):
    probs, bets = summary['probabilities'], summary['bets']
    lines = ['{}: {} games with model and market probabilities'.format(name, probs['n'])]
    labels = (('p_raw', 'model raw'), ('p_used', 'model used'), ('p_market', 'market fair'))
    for key, label in labels:
        metrics = probs.get(key)
        if metrics:
            lines.append('  {:<12} log loss {:.4f}   brier {:.4f}'.format(
                label, metrics['log_loss'], metrics['brier']))
    if bets['n']:
        clv = 'n/a' if bets['avg_clv'] is None else '{:+.1%}'.format(bets['avg_clv'])
        lines.append(
            '  bets: {} placed, {} won, {:+.2f} units, ROI {:+.1%}, '
            'avg closing-line value {} ({} with a closing line)'.format(
                bets['n'], bets['wins'], bets['units'], bets['roi'], clv, bets['clv_n'])
        )
    else:
        lines.append('  bets: none')
    return lines


def format_report(report: dict) -> str:
    lines = ['Games logged pre-game: {}, scored: {}, waiting on results: {}'.format(
        report['games_logged'], report['games_scored'], report['games_pending'])]
    lines += _describe('Overall', report['overall'])
    for name, summary in report['by_segment'].items():
        lines += _describe(name, summary)
    return '\n'.join(lines)

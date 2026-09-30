'''Load and format scorer output and logged picks for the Performance page.'''
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
SCORECARD_PATH = ROOT / 'data_files' / 'results' / 'scorecard.json'
FINAL_SCORES_PATH = ROOT / 'data_files' / 'results' / 'final_scores.json'
PICK_LOG_DIR = ROOT / 'data_files' / 'pick_log'
MIN_GAMES = 100
EARLY_GAMES = 20
WIN, LOSS, PENDING, NO_PICK = '✅ Win', '❌ Loss', '⏳ Pending', 'No pick'
SEGMENT_LABELS = {
    'overall': 'All games',
    'prior_only': 'Last-season ratings only',
    'early': 'Under 20 games played',
    'established': '20+ games played',
    'unknown': 'Unknown',
}


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def load_scorecard(path: Path = SCORECARD_PATH) -> Optional[dict]:
    '''Read the scorecard, or None if it is missing or unreadable.'''
    return _read_json(path)


def load_final_scores(path: Path = FINAL_SCORES_PATH) -> dict:
    '''Final scores keyed by game_date|AWAY|HOME, or an empty dict.'''
    data = _read_json(path)
    return data if isinstance(data, dict) else {}


def load_pick_log(directory: Path = PICK_LOG_DIR) -> List[dict]:
    '''Every readable entry from the monthly JSON Lines pick logs.'''
    entries = []
    for path in sorted(Path(directory).glob('*.jsonl')):
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _text(value, spec: str) -> str:
    return 'n/a' if value is None else format(value, spec)


def _log_loss(metrics) -> str:
    return 'n/a' if not metrics else format(metrics['log_loss'], '.4f')


def _parse_time(text):
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return None


def _logged_before_start(entry: dict) -> bool:
    logged, start = _parse_time(entry.get('logged_at')), _parse_time(entry.get('start_utc'))
    return logged is None or start is None or logged < start


def _stage(entry: dict) -> str:
    if entry.get('prior_only'):
        return SEGMENT_LABELS['prior_only']
    played = [entry.get('home_games_played'), entry.get('away_games_played')]
    if None in played:
        return SEGMENT_LABELS['unknown']
    return SEGMENT_LABELS['early' if min(played) < EARLY_GAMES else 'established']


def _pick_row(entry: dict, score: Optional[dict]) -> dict:
    home, away = entry['home_team'], entry['away_team']
    p_home, fair_home = entry.get('home_win_prob_used'), entry.get('fair_home_prob')
    pick = model_p = market_p = edge = None
    result = NO_PICK
    if p_home is not None:
        pick_home = p_home >= 0.5
        pick = home if pick_home else away
        model_p = p_home if pick_home else 1 - p_home
        if fair_home is not None:
            market_p = fair_home if pick_home else 1 - fair_home
            edge = model_p - market_p
        result = PENDING
        if score is not None:
            result = WIN if (score['home_goals'] > score['away_goals']) == pick_home else LOSS
    final = ''
    if score is not None:
        final = '{} {} - {} {}'.format(away, score['away_goals'], home, score['home_goals'])
    return {
        'Time': entry.get('game_time', ''),
        'Game': '{} @ {}'.format(away, home),
        'Pick': pick or 'n/a',
        'Model win %': _text(model_p, '.1%'),
        'Market win %': _text(market_p, '.1%'),
        'Edge': _text(edge, '+.1%'),
        'Result': result,
        'Final score': final,
        'Stage': _stage(entry),
    }


def picks_for_date(entries: List[dict], scores: dict, game_date: str) -> List[dict]:
    '''One row per game on game_date, using the last entry logged before the start.'''
    latest = {}
    for entry in entries:
        if entry.get('game_date') != game_date or not _logged_before_start(entry):
            continue
        key = (entry['away_team'], entry['home_team'])
        if key not in latest or entry.get('logged_at', '') > latest[key].get('logged_at', ''):
            latest[key] = entry
    ordered = sorted(latest.items(), key=lambda item: item[1].get('start_utc') or '')
    return [
        _pick_row(entry, scores.get('{}|{}|{}'.format(game_date, away, home)))
        for (away, home), entry in ordered
    ]


def day_summary(rows: List[dict]) -> str:
    '''One sentence on how the model did on the day.'''
    if not rows:
        return 'No picks were logged for this date.'
    wins = sum(r['Result'] == WIN for r in rows)
    decided = wins + sum(r['Result'] == LOSS for r in rows)
    pending = sum(r['Result'] == PENDING for r in rows)
    if not decided:
        return 'No finished games yet ({} pending).'.format(pending)
    text = 'Model picked {} of {} winners ({:.0%}).'.format(wins, decided, wins / decided)
    if pending:
        text += ' {} still pending.'.format(pending)
    return text


def segment_rows(report: dict) -> List[dict]:
    '''One display row for the overall summary and each segment.'''
    blocks = [('overall', report['overall'])] + list(report.get('by_segment', {}).items())
    rows = []
    for name, summary in blocks:
        probs, bets = summary['probabilities'], summary['bets']
        has_bets = bets.get('n', 0) > 0
        rows.append({
            'Segment': SEGMENT_LABELS.get(name, name),
            'Games compared': probs['n'],
            'Log loss: model (raw)': _log_loss(probs.get('p_raw')),
            'Log loss: model (blended)': _log_loss(probs.get('p_used')),
            'Log loss: market': _log_loss(probs.get('p_market')),
            'Simulated bets': bets.get('n', 0),
            'Win rate': _text(bets.get('hit_rate') if has_bets else None, '.1%'),
            'Units': _text(bets.get('units') if has_bets else None, '+.2f'),
            'ROI': _text(bets.get('roi') if has_bets else None, '+.1%'),
            'Avg closing-line value': _text(bets.get('avg_clv') if has_bets else None, '+.1%'),
            'Bets with a closing line': bets.get('clv_n', 0) if has_bets else 0,
        })
    return rows


def verdict(report: dict) -> str:
    '''Plain-language comparison of the blended model against the market.'''
    probs = report['overall']['probabilities']
    count = probs['n']
    blended, market = probs.get('p_used'), probs.get('p_market')
    if not count or blended is None or market is None:
        return 'No games with full model and market probabilities yet.'
    diff = market['log_loss'] - blended['log_loss']
    if count < MIN_GAMES:
        return (
            f'Only {count} games compared so far; at least {MIN_GAMES} are needed before this '
            f'means anything. Current log loss gap (market minus model): {diff:+.4f}.'
        )
    if diff > 0:
        return f'Across {count} games the blended model has a lower log loss than the market by {diff:.4f}.'
    return f'Across {count} games the blended model does not beat the market (log loss higher by {-diff:.4f}).'

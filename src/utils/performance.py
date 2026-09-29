'''Load and format the scorer scorecard for the Performance page.'''
import json
from pathlib import Path
from typing import List, Optional

SCORECARD_PATH = Path(__file__).resolve().parents[2] / 'data_files' / 'results' / 'scorecard.json'
MIN_GAMES = 100
SEGMENT_LABELS = {
    'overall': 'All games',
    'prior_only': 'Last-season ratings only',
    'early': 'Under 20 games played',
    'established': '20+ games played',
    'unknown': 'Unknown',
}


def load_scorecard(path: Path = SCORECARD_PATH) -> Optional[dict]:
    '''Read the scorecard, or None if it is missing or unreadable.'''
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _text(value, spec: str) -> str:
    return 'n/a' if value is None else format(value, spec)


def _log_loss(metrics) -> str:
    return 'n/a' if not metrics else format(metrics['log_loss'], '.4f')


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

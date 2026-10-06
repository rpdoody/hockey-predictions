'''Automatically capture odds snapshots for GitHub Actions.'''
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from src.api.nhl_client import NHLClient
from src.utils.odds_parse import parse_line, parse_price, to_nhl_abbrev
from src.utils.odds_storage import save_odds_snapshot


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def _provider_key(name) -> str:
    '''Lowercase letters and digits only, so 'Draft Kings' matches 'DraftKings'.'''
    return ''.join(ch for ch in str(name or '').lower() if ch.isalnum())


def select_provider(odds_list: list) -> Optional[dict]:
    '''Prefer DraftKings (any spacing or case), otherwise the first provider listed.'''
    for provider in odds_list:
        if _provider_key(provider.get('provider')) == 'draftkings':
            return provider
    return odds_list[0] if odds_list else None


def build_snapshot(game: dict) -> Optional[dict]:
    '''Turn one parsed ESPN game into save_odds_snapshot arguments.

    Returns None when the game has no usable moneyline. Markets that are not
    offered stay None instead of being filled with made-up defaults.
    '''
    game_id = game.get('game_id')
    home = to_nhl_abbrev(game.get('home_team'))
    away = to_nhl_abbrev(game.get('away_team'))
    if not game_id or not home or not away:
        return None

    selected = select_provider(game.get('odds', []))
    if not selected:
        return None

    moneyline = selected.get('moneyline') or {}
    home_ml = parse_price(moneyline.get('home'))
    away_ml = parse_price(moneyline.get('away'))
    if home_ml is None or away_ml is None:
        return None

    total = selected.get('total') or {}
    over = total.get('over') or {}
    under = total.get('under') or {}
    line = parse_line(over.get('line'))
    if line is None:
        line = parse_line(under.get('line'))
    over_odds = parse_price(over.get('odds')) if line is not None else None
    under_odds = parse_price(under.get('odds')) if line is not None else None

    spread = selected.get('spread') or {}
    home_pl = spread.get('home') or {}
    away_pl = spread.get('away') or {}

    return {
        'game_id': str(game_id),
        'home_team': home,
        'away_team': away,
        'home_ml': home_ml,
        'away_ml': away_ml,
        'total': line,
        'over_odds': over_odds,
        'under_odds': under_odds,
        'home_pl_odds': parse_price(home_pl.get('odds')),
        'away_pl_odds': parse_price(away_pl.get('odds')),
        'home_pl_line': parse_line(home_pl.get('line')),
        'start_time': game.get('date'),
        'provider': selected.get('provider'),
    }


def capture_odds_snapshots() -> int:
    '''Capture odds for the next 3 days. Returns the number of errors.'''
    print(f'[{_stamp()}] Starting odds capture...')

    try:
        odds_data = NHLClient().get_espn_odds(days_ahead=3)
    except Exception as exc:
        print(f'ERROR fetching odds: {exc}')
        traceback.print_exc()
        return 1

    print(f'Found {len(odds_data)} games')
    captured = unchanged = skipped = errors = 0

    for game in odds_data:
        away = game.get('away_team')
        home = game.get('home_team')
        label = f'{away} @ {home}'

        if not game.get('odds'):
            print(f'No odds available for {label}')
            skipped += 1
            continue

        snapshot = build_snapshot(game)
        if snapshot is None:
            print(f'Incomplete odds for {label}')
            skipped += 1
            continue

        try:
            written = save_odds_snapshot(**snapshot)
        except Exception as exc:
            print(f'ERROR saving {label}: {exc}')
            errors += 1
            continue

        if written:
            captured += 1
            print(f'Captured {label}: ML {snapshot["away_ml"]}/{snapshot["home_ml"]}, total {snapshot["total"]}')
        else:
            unchanged += 1

    print(f'Summary: {captured} captured, {unchanged} unchanged, {skipped} skipped, {errors} errors')
    print(f'[{_stamp()}] Capture complete')
    return errors


if __name__ == '__main__':
    sys.exit(1 if capture_odds_snapshots() else 0)

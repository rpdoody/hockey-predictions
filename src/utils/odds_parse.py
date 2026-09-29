'''Helpers for cleaning ESPN odds fields and team codes.'''
import re
from typing import Any, Optional

ESPN_TO_NHL = {'LA': 'LAK', 'NJ': 'NJD', 'SJ': 'SJS', 'TB': 'TBL', 'UTAH': 'UTA'}

_NUMBER = re.compile(r'[-+]?\d+(?:\.\d+)?')


def to_nhl_abbrev(code: Optional[str]) -> Optional[str]:
    '''Map an ESPN team code to the NHL API code (unknown codes pass through).'''
    if code is None:
        return None
    return ESPN_TO_NHL.get(code, code)


def parse_line(value: Any) -> Optional[float]:
    '''Parse a line such as 'o6.5', 'u5.5', '-1.5' or 6.5; None if unusable.'''
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER.search(str(value))
    return float(match.group()) if match else None


def parse_price(value: Any) -> Optional[int]:
    '''Parse American odds such as '-110', '+150', 150 or 'EVEN'; None if unusable.'''
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, (int, float)):
        price = int(round(value))
    else:
        text = str(value).strip().upper()
        if text in {'EVEN', 'EV', 'PK'}:
            return 100
        match = _NUMBER.fullmatch(text)
        if not match:
            return None
        price = int(round(float(match.group())))
    return price if abs(price) >= 100 else None

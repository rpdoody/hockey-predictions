"""Match sportsbook player and team names to NHL names."""
import difflib
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

TEAM_ALIASES = {'utah mammoth': 'UTA', 'utah hockey club': 'UTA'}
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
FUZZY_CUTOFF = 0.86   # how similar two names must be to count as the same player
FUZZY_MARGIN = 0.04   # the best match must beat the runner-up by this much


def normalize_name(name) -> str:
    """Lowercase, drop accents, punctuation and Jr/Sr style suffixes so spellings compare equal."""
    text = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode().lower()
    text = text.replace("'", '').replace('.', ' ').replace('-', ' ')
    tokens = [t for t in re.sub(r'[^a-z ]', ' ', text).split() if t not in SUFFIXES]
    return ' '.join(tokens)


def team_lookup(team_names: Dict[str, str]) -> Dict[str, str]:
    """Normalized full team name -> NHL abbreviation, including known renames."""
    lookup = {normalize_name(full): abbrev for abbrev, full in team_names.items()}
    lookup.update(TEAM_ALIASES)
    return lookup


def team_abbrev(name: str, lookup: Dict[str, str]) -> Optional[str]:
    return lookup.get(normalize_name(name))


def match_player(name: str, candidates: List[dict]) -> Tuple[Optional[dict], str]:
    """Find the candidate (a dict with 'name') that a sportsbook name refers to.

    Returns (candidate, method) with method 'exact' or 'fuzzy', or (None, reason) where the
    reason is 'unmatched' or 'ambiguous' (two players the name could be, e.g. same name on one team).
    """
    target = normalize_name(name)
    if not target or not candidates:
        return None, 'unmatched'
    normalized = [(normalize_name(c['name']), c) for c in candidates]
    exact = [c for n, c in normalized if n == target]
    if len(exact) == 1:
        return exact[0], 'exact'
    if len(exact) > 1:
        return None, 'ambiguous'
    scored = sorted(((difflib.SequenceMatcher(None, target, n).ratio(), c) for n, c in normalized), key=lambda item: -item[0])
    best_score, best = scored[0]
    if best_score < FUZZY_CUTOFF:
        return None, 'unmatched'
    if len(scored) > 1 and scored[1][0] > best_score - FUZZY_MARGIN:
        return None, 'ambiguous'
    return best, 'fuzzy'

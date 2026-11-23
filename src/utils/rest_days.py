"""Rest and schedule-density fields for the pick log.

These are logged only. Nothing in the model or the recommendation logic reads them yet.
"""
from datetime import date, timedelta
from typing import Iterable, List, Optional

REGULAR_SEASON, PLAYOFFS = 2, 3


def schedule_dates(schedule) -> List[date]:
    """Sorted, de-duplicated dates of a team's regular-season and playoff games.

    Uses scheduled dates, not results, so a stale cached schedule still gives the right gaps.
    """
    if not isinstance(schedule, dict):
        return []
    games = schedule.get("games")
    if not isinstance(games, list):
        return []
    found = set()
    for game in games:
        if not isinstance(game, dict) or game.get("gameType") not in (REGULAR_SEASON, PLAYOFFS):
            continue
        try:
            found.add(date.fromisoformat(str(game.get("gameDate"))[:10]))
        except ValueError:
            continue
    return sorted(found)


def team_game_dates(client, team: str, season: str, cache: dict) -> List[date]:
    """A team's game dates for the season, fetched once per team per run; empty on any failure."""
    if team not in cache:
        try:
            cache[team] = schedule_dates(client.get_team_schedule(team, season=season))
        except Exception:
            cache[team] = []
    return cache[team]


def rest_fields(game_date: str, dates: Iterable[date], prefix: str) -> dict:
    """Rest fields for one team, keyed with the given prefix ('home' or 'away').

    rest_days is days since the previous game (1 means back-to-back), or None when the team has no
    earlier game this season or the date cannot be read. games_last_7 counts games in the 7 days
    before the game date.
    """
    empty = {
        f"{prefix}_rest_days": None,
        f"{prefix}_back_to_back": None,
        f"{prefix}_games_last_7": None,
    }
    try:
        day = date.fromisoformat(str(game_date)[:10])
    except ValueError:
        return empty
    dates = list(dates)
    if not dates:
        return empty
    earlier = [d for d in dates if d < day]
    rest = (day - max(earlier)).days if earlier else None
    window_start = day - timedelta(days=7)
    return {
        f"{prefix}_rest_days": rest,
        f"{prefix}_back_to_back": None if rest is None else rest == 1,
        f"{prefix}_games_last_7": sum(1 for d in earlier if d >= window_start),
    }

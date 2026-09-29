"""NHL season and time-zone helpers."""
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# A new season becomes "current" on this month's first day. August 1 is before
# preseason games, so a team with no games yet has no current-season stats and
# gets skipped instead of being priced from last year's numbers.
ROLLOVER_MONTH = 8


def season_start_year(today: Optional[date] = None) -> int:
    """Calendar year in which the current season starts."""
    today = today or datetime.now(EASTERN).date()
    return today.year if today.month >= ROLLOVER_MONTH else today.year - 1


def current_season_id(today: Optional[date] = None) -> str:
    """NHL API season ID, e.g. "20262027"."""
    year = season_start_year(today)
    return f"{year}{year + 1}"


def current_season_name(today: Optional[date] = None) -> str:
    """Display season name, e.g. "2026-27"."""
    year = season_start_year(today)
    return f"{year}-{(year + 1) % 100:02d}"


def to_eastern(iso_timestamp: str) -> Optional[datetime]:
    """Parse an ISO timestamp ("Z" or offset) and convert it to US Eastern time."""
    try:
        parsed = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(EASTERN)

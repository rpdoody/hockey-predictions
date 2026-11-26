"""Keep a good best_bets_today.json when a later run finds no games to evaluate."""
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

BEST_BETS = Path("data_files/best_bets_today.json")
LOG_DIR = Path("data_files/pick_log")
STATE_DIR = Path(tempfile.gettempdir()) / "best_bets_guard"


def count_log_lines(log_dir: Path = LOG_DIR) -> int:
    """Total non-empty lines across the monthly pick log files."""
    total = 0
    for path in Path(log_dir).glob("*.jsonl"):
        total += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return total


def bets_for_day(path: Path, day: str) -> List[dict]:
    """Bets in a best-bets file dated day; empty when the file is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        bets = data.get("bets") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [b for b in bets if isinstance(b, dict) and b.get("game_date") == day]


def should_restore(new_bets: List[dict], old_bets: List[dict], records_appended: int) -> bool:
    """Restore only when the run evaluated no games at all (odds or fetch failure).

    A run that evaluated games and found no edge is a real empty result and stays empty.
    """
    return not new_bets and bool(old_bets) and records_appended == 0


def before() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if BEST_BETS.exists():
        shutil.copyfile(BEST_BETS, STATE_DIR / "previous.json")
    else:
        (STATE_DIR / "previous.json").unlink(missing_ok=True)
    (STATE_DIR / "log_lines.txt").write_text(str(count_log_lines()))
    print("[guard] saved previous best bets and pick log size")


def after() -> None:
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    try:
        lines_before = int((STATE_DIR / "log_lines.txt").read_text())
    except (OSError, ValueError):
        print("[guard] no saved state; leaving the file alone")
        return
    appended = count_log_lines() - lines_before
    new_bets = bets_for_day(BEST_BETS, today)
    old_bets = bets_for_day(STATE_DIR / "previous.json", today)
    if should_restore(new_bets, old_bets, appended):
        shutil.copyfile(STATE_DIR / "previous.json", BEST_BETS)
        print(f"[guard] run evaluated no games; restored {len(old_bets)} earlier bets for {today}")
    else:
        print(f"[guard] keeping new file ({len(new_bets)} bets, {appended} log records appended)")


if __name__ == "__main__":
    {"before": before, "after": after}[sys.argv[1]]()

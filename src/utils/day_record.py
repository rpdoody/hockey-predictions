"""Record of the simulated totals and puck-line bets for one day."""
from typing import Iterable, Optional

MARKETS = ("Total", "Puck line")


def day_record(rows: Iterable[dict], day: str, stage: Optional[str] = None) -> dict:
    """Wins, losses, pushes and profit per market for simulated bets on one game date.

    Only graded bets count. Pass stage to limit the count to one segment label.
    """
    rows = list(rows)
    record = {}
    for market in MARKETS:
        bets = [
            r for r in rows
            if r.get("date") == day and r.get("market") == market and r.get("bet_result")
            and (stage is None or r.get("stage") == stage)
        ]
        wins = sum(r["bet_result"] == "win" for r in bets)
        losses = sum(r["bet_result"] == "loss" for r in bets)
        record[market] = {
            "bets": len(bets),
            "wins": wins,
            "losses": losses,
            "pushes": len(bets) - wins - losses,
            "profit": sum(r.get("profit") or 0.0 for r in bets),
        }
    return record

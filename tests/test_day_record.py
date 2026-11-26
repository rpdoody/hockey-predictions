from src.utils.day_record import day_record

EST = "20+ games played"


def _row(date, market, result, profit, stage=EST):
    return {"date": date, "market": market, "bet_result": result, "profit": profit, "stage": stage}


def test_counts_each_market_separately():
    rows = [
        _row("2026-11-24", "Total", "win", 9.09),
        _row("2026-11-24", "Total", "loss", -10.0),
        _row("2026-11-24", "Puck line", "win", 6.5),
        _row("2026-11-24", "Puck line", "push", 0.0),
    ]
    rec = day_record(rows, "2026-11-24")
    assert (rec["Total"]["wins"], rec["Total"]["losses"], rec["Total"]["pushes"]) == (1, 1, 0)
    assert rec["Total"]["profit"] == 9.09 - 10.0
    assert (rec["Puck line"]["wins"], rec["Puck line"]["pushes"], rec["Puck line"]["bets"]) == (1, 1, 2)


def test_other_days_and_non_bets_are_ignored():
    rows = [
        _row("2026-11-23", "Total", "win", 9.0),
        _row("2026-11-24", "Total", None, None),
    ]
    rec = day_record(rows, "2026-11-24")
    assert rec["Total"]["bets"] == 0
    assert rec["Puck line"]["bets"] == 0


def test_stage_filter_limits_the_count():
    rows = [
        _row("2026-11-24", "Total", "win", 9.0),
        _row("2026-11-24", "Total", "loss", -10.0, stage="Under 20 games played"),
    ]
    assert day_record(rows, "2026-11-24", stage=EST)["Total"]["bets"] == 1
    assert day_record(rows, "2026-11-24")["Total"]["bets"] == 2

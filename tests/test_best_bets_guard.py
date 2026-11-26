from src.utils.best_bets_guard import bets_for_day, count_log_lines, should_restore

BET = {"game_date": "2026-11-26", "pick": "TOR"}


def test_restores_only_when_nothing_was_evaluated():
    assert should_restore([], [BET], 0)
    assert not should_restore([], [BET], 12)
    assert not should_restore([BET], [BET], 0)
    assert not should_restore([], [], 0)


def test_bets_for_day_filters_by_date_and_survives_bad_files(tmp_path):
    good = tmp_path / "a.json"
    good.write_text('{"bets": [{"game_date": "2026-11-26"}, {"game_date": "2026-11-25"}]}')
    assert len(bets_for_day(good, "2026-11-26")) == 1
    bad = tmp_path / "b.json"
    bad.write_text("not json")
    assert bets_for_day(bad, "2026-11-26") == []
    assert bets_for_day(tmp_path / "missing.json", "2026-11-26") == []


def test_count_log_lines_skips_blank_lines(tmp_path):
    (tmp_path / "2026-11.jsonl").write_text('{"a": 1}\n\n{"a": 2}\n')
    assert count_log_lines(tmp_path) == 2

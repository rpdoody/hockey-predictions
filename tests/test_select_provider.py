from auto_capture_odds import select_provider


def test_spaced_name_is_matched_ahead_of_other_books():
    odds = [{'provider': 'Caesars'}, {'provider': 'Draft Kings'}]
    assert select_provider(odds)['provider'] == 'Draft Kings'


def test_exact_and_uppercase_names_still_match():
    assert select_provider([{'provider': 'Bet365'}, {'provider': 'DraftKings'}])['provider'] == 'DraftKings'
    assert select_provider([{'provider': 'Bet365'}, {'provider': 'DRAFTKINGS'}])['provider'] == 'DRAFTKINGS'


def test_falls_back_to_first_provider_without_draftkings():
    odds = [{'provider': 'Caesars'}, {'provider': 'Bet365'}]
    assert select_provider(odds)['provider'] == 'Caesars'


def test_empty_list_and_missing_name_are_safe():
    assert select_provider([]) is None
    assert select_provider([{}])  == {}

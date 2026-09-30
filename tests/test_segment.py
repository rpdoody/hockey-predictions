from src.utils.scoring import segment


def test_prior_only_records_get_their_own_segment():
    record = {'prior_only': True, 'home_games_played': None, 'away_games_played': None}
    assert segment(record) == 'prior_only'


def test_games_played_decide_the_rest():
    assert segment({'home_games_played': 5, 'away_games_played': 30}) == 'early'
    assert segment({'home_games_played': 25, 'away_games_played': 30}) == 'established'
    assert segment({'home_games_played': None, 'away_games_played': 30}) == 'unknown'

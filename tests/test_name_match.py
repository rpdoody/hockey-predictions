import pytest

from src.utils.name_match import match_player, normalize_name, team_abbrev, team_lookup

TEAMS = {'MTL': 'Montreal Canadiens', 'STL': 'St. Louis Blues', 'UTA': 'Utah Hockey Club', 'BOS': 'Boston Bruins'}


def test_normalize_name_drops_accents_punctuation_and_suffixes():
    assert normalize_name('Nick Suzuki') == 'nick suzuki'
    assert normalize_name('Jesperi Kotkaniemi') == normalize_name('JESPERI  KOTKANIEMI')
    assert normalize_name("Ryan O'Reilly") == 'ryan oreilly'
    assert normalize_name('T.J. Oshie') == 't j oshie'
    assert normalize_name('Jean-Gabriel Pageau') == 'jean gabriel pageau'
    assert normalize_name('Éric Staal Jr.') == 'eric staal'
    assert normalize_name(None) == ''


def test_team_lookup_handles_accents_punctuation_and_renames():
    lookup = team_lookup(TEAMS)
    assert team_abbrev('Montréal Canadiens', lookup) == 'MTL'
    assert team_abbrev('St Louis Blues', lookup) == 'STL'
    assert team_abbrev('Utah Mammoth', lookup) == 'UTA'
    assert team_abbrev('Utah Hockey Club', lookup) == 'UTA'
    assert team_abbrev('Atlantis Sharks', lookup) is None


def _c(name):
    return {'name': name, 'player_id': hash(name) % 1000}


def test_exact_match_ignores_case_accents_and_suffixes():
    candidates = [_c('Brad Marchand'), _c('Charlie McAvoy')]
    assert match_player('brad marchand', candidates)[1] == 'exact'
    assert match_player('Charlie McAvoy', candidates)[0]['name'] == 'Charlie McAvoy'
    assert match_player('Pavel Zacha Jr.', [_c('Pavel Zacha')])[1] == 'exact'


def test_fuzzy_match_accepts_a_close_spelling_but_not_a_loose_one():
    candidates = [_c('Alexander Ovechkin'), _c('Dylan Strome')]
    found, method = match_player('Alexander Ovechkn', candidates)
    assert method == 'fuzzy' and found['name'] == 'Alexander Ovechkin'
    assert match_player('Sidney Crosby', candidates) == (None, 'unmatched')


def test_same_name_twice_is_ambiguous_and_near_twins_do_not_guess():
    twins = [_c('Elias Pettersson'), _c('Elias Pettersson')]
    assert match_player('Elias Pettersson', twins) == (None, 'ambiguous')
    close = [_c('Alex Newhook'), _c('Alex Newhooke')]
    assert match_player('Alex Newhoo', close)[1] in ('ambiguous', 'unmatched')
    assert match_player('Anyone', []) == (None, 'unmatched')

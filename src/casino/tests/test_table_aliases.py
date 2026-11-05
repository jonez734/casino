"""Top-level play aliases route to ``table <verb>``; the verbs and their gates come from the game packages.

Blackjack and poker each declare their TABLE_VERBS. The table dispatch and the client menu both read those
declarations, so a verb's allowed table types cannot disagree between the two.
"""

import pytest

from casino.client import menu
from casino.client.menu import MenuOption, _check_top_level_names
from casino.commands.table import play

pytestmark = pytest.mark.unit


def _option(letter):
    return next(o for o in menu._OPTIONS_SPEC if o.letter == letter)


def test_play_aliases_point_at_table_not_game_or_poker():
    table = _option("table")
    assert set(table.aliases) == set(play.union_of_verbs())
    assert table.alias_subcommand == {v: v for v in table.aliases}
    assert _option("game").aliases == ()


def test_each_game_declares_its_table_verbs():
    from casino.commands.blackjack import TABLE_VERBS as bj
    from casino.commands.poker import TABLE_VERBS as pk

    assert set(bj) == {"bet", "hit", "stand", "double", "split", "play"}
    assert set(pk) == {"bet", "check", "call", "raise", "fold", "allin", "start"}


def test_the_dispatch_map_is_the_game_declarations():
    from casino.commands.blackjack import TABLE_VERBS as bj
    from casino.commands.poker import TABLE_VERBS as pk

    assert set(play.PLAY_VERBS["blackjack"]) == set(bj)
    assert set(play.PLAY_VERBS["poker"]) == set(pk)


@pytest.mark.parametrize("verb,types", [
    ("bet", {"blackjack", "poker"}),
    ("hit", {"blackjack"}),
    ("play", {"blackjack"}),
    ("double", {"blackjack"}),
    ("start", {"poker"}),
    ("check", {"poker"}),
])
def test_menu_gates_each_verb_to_the_types_that_declare_it(verb, types):
    sub = _option("table").subcommands[verb]
    assert set(sub.allowed_game_types) == types
    assert sub.requires_seated is True


def test_double_is_hidden_at_a_poker_table_and_play_is_hidden_at_poker():
    from casino.client.menu import _checker
    from bbsengine6.menu_next import visible_options

    class C:
        current_table_moniker = "p"
        current_table_game_type = "poker"
        args = None

    table = _option("table")
    shown = {s.letter for s in visible_options(tuple(table.subcommands.values()), C(), check=_checker(C()))}
    assert "double" not in shown and "play" not in shown
    assert "start" in shown and "check" in shown


def test_top_level_names_are_unique_in_the_real_menu():
    _check_top_level_names(menu._OPTIONS_SPEC)


def test_a_clashing_alias_is_refused_naming_both():
    spec = (MenuOption("bet", "Bet"), MenuOption("wager", "Wager", aliases=("bet",)))
    with pytest.raises(ValueError, match="'bet'.*'bet'.*'wager'|'bet' is used by both"):
        _check_top_level_names(spec)

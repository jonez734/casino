"""``table <verb>`` routes by the seated table's type, and refuses loudly otherwise."""

import pytest

from casino.commands.table import play


pytestmark = pytest.mark.unit


def test_unseated_refuses_with_not_seated():
    r = play.resolve("hit", seated=False, game_type=None)
    assert isinstance(r, play.Refusal)
    assert "not seated" in r.message


def test_seated_without_a_type_refuses_as_not_seated():
    r = play.resolve("hit", seated=True, game_type=None)
    assert isinstance(r, play.Refusal) and "not seated" in r.message


@pytest.mark.parametrize("verb", ["bet", "hit", "stand", "double", "split", "play"])
def test_blackjack_routes_its_verbs(verb):
    assert play.resolve(verb, seated=True, game_type="blackjack") == "blackjack"


@pytest.mark.parametrize("verb", ["bet", "check", "call", "raise", "fold", "allin", "start"])
def test_poker_routes_its_verbs(verb):
    assert play.resolve(verb, seated=True, game_type="poker") == "poker"


def test_poker_refuses_double_and_names_the_type():
    r = play.resolve("double", seated=True, game_type="poker")
    assert isinstance(r, play.Refusal)
    assert r.message == "poker has no double"


def test_blackjack_refuses_start_and_names_the_type():
    r = play.resolve("start", seated=True, game_type="blackjack")
    assert isinstance(r, play.Refusal)
    assert r.message == "blackjack has no start"


def test_play_is_blackjacks_and_start_is_pokers_not_the_same_action():
    assert "play" in play.PLAY_VERBS["blackjack"] and "play" not in play.PLAY_VERBS["poker"]
    assert "start" in play.PLAY_VERBS["poker"] and "start" not in play.PLAY_VERBS["blackjack"]


def test_an_unknown_game_type_refuses_loudly():
    r = play.resolve("hit", seated=True, game_type="craps")
    assert isinstance(r, play.Refusal) and "no play verbs for craps" in r.message


def test_verbs_for_is_empty_when_not_at_a_table():
    assert play.verbs_for(None) == ()
    assert "double" not in play.verbs_for("poker")
    assert "double" in play.verbs_for("blackjack")


def test_union_covers_every_type_once():
    union = play.union_of_verbs()
    assert len(union) == len(set(union))
    for verbs in play.PLAY_VERBS.values():
        assert set(verbs) <= set(union)


class _Client:
    def __init__(self, moniker=None, game_type=None):
        self.current_table_moniker = moniker
        self.current_table_game_type = game_type


def _recorders(monkeypatch):
    """Replace each game package's TABLE_VERBS entry with a recorder, the single point dispatch reads."""
    from casino.commands.blackjack import __init__ as _bj  # noqa: F401
    import importlib

    ran = []
    for pkg in ("casino.commands.blackjack", "casino.commands.poker"):
        mod = importlib.import_module(pkg)
        recorded = {
            verb: (lambda args, client=None, _n=verb, **kw: ran.append(_n) or True)
            for verb in mod.TABLE_VERBS
        }
        monkeypatch.setattr(mod, "TABLE_VERBS", recorded)
    return ran


def test_dispatch_runs_blackjacks_hit_at_a_blackjack_table(monkeypatch):
    ran = _recorders(monkeypatch)
    assert play.dispatch("hit", None, client=_Client("bj-a", "blackjack")) is True
    assert ran == ["hit"]


def test_dispatch_runs_pokers_start_at_a_poker_table(monkeypatch):
    ran = _recorders(monkeypatch)
    assert play.dispatch("start", None, client=_Client("p-a", "poker")) is True
    assert ran == ["start"]


def test_dispatch_refuses_double_at_a_poker_table_and_runs_nothing(monkeypatch):
    ran = _recorders(monkeypatch)
    assert play.dispatch("double", None, client=_Client("p-a", "poker")) is False
    assert ran == []


def test_dispatch_unseated_runs_nothing(monkeypatch):
    ran = _recorders(monkeypatch)
    assert play.dispatch("hit", None, client=_Client(None, None)) is False
    assert ran == []

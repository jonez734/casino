#!/usr/bin/env python3
# casino/tests/test_main_menu_visibility.py
# End-to-end pins for the door-mode main menu's visibility filter.
#
# These tests walk ``casino.main`` source directly so the spec under
# test is the one in HEAD, not a hand-maintained fixture. They also
# exercise ``casino.menu_lib.visible_options`` (the actual runtime
# filter) against the recovered spec, so the contract pins the
# composition of the two.
#
# What is pinned:
#   * Not seated: seat-gated actions and the connect-only Disconnect
#     are hidden; always-available options and game launchers show.
#   * Seated at blackjack: the Blackjack launcher hides itself; Bet /
#     Hit / Stand / Play become visible.
#   * Seated at poker: the Poker launcher hides itself; blackjack-only
#     Hit / Stand drop; Bet stays (allowed types include poker); Play
#     stays.
#   * Seated at yahtzee: only the Yahtzee launcher hides; the other
#     launchers stay; Play stays.
#   * Connection flag: Disconnect shows only when ``connected`` is
#     truthy; otherwise it is hidden even for a seated player.

import sys
import unittest
from types import SimpleNamespace


sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _kwarg_value(node):
    """Convert a kwarg AST node to a Python value.

    Handles literal constants (string, int, bool, None) and
    ``frozenset({...})`` calls; anything else raises so a future
    spec change is caught loudly instead of silently coerced.
    """
    import ast

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) == 1
    ):
        return frozenset(ast.literal_eval(node.args[0]))
    return ast.literal_eval(node)


def _main_options():
    """Return ``casino.main``'s ``options`` tuple as real
    ``MenuOption`` instances, reconstructed from AST.

    Importing ``casino.main`` as a submodule (not via
    ``from casino import main``) avoids accidentally binding to the
    ``main`` function re-exported from ``casino/__init__.py``.
    """
    import ast
    import importlib
    import inspect

    main_module = importlib.import_module("casino.main")
    from casino.menu_lib import MenuOption

    src = inspect.getsource(main_module)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "options"
        ):
            out = []
            for elt in node.value.elts:
                if not (
                    isinstance(elt, ast.Call)
                    and isinstance(elt.func, ast.Name)
                    and elt.func.id == "MenuOption"
                ):
                    continue
                args = [ast.literal_eval(a) for a in elt.args]
                kwargs = {kw.arg: _kwarg_value(kw.value) for kw in elt.keywords}
                out.append(MenuOption(*args, **kwargs))
            return out
    raise AssertionError("options tuple not found in casino.main")


class TestMainMenuVisibility(unittest.TestCase):
    """End-to-end visibility contract for casino.main's door-mode
    main menu. The spec under test is reconstructed from AST so
    these tests are order-independent and not affected by which
    other tests have already loaded ``casino.main``.
    """

    @classmethod
    def setUpClass(cls):
        cls.options = _main_options()

    def _visible(self, state):
        from casino.menu_lib import visible_options

        return visible_options(self.options, state)

    def _labels_for(self, state, letter):
        return [o.label for o in self._visible(state) if o.letter == letter]

    # ---- always-available options stay visible regardless of seat ----

    def test_unseated_shows_always_available_options(self):
        """Connect / List / Join / View / Watch / Unwatch / Global /
        Bank / Maintenance must show even when not at a table.
        Disconnect must hide because no connection is open yet.
        """
        state = SimpleNamespace(
            current_table_moniker=None,
            current_table_game_type=None,
            connected=False,
        )
        labels = {o.label for o in self._visible(state)}
        for must in ("Connect", "List tables", "Join table", "View table",
                     "Watch table", "Unwatch table", "Global msg", "Bank",
                     "Maintenance"):
            self.assertIn(must, labels, f"{must!r} should be visible unseated")
        self.assertNotIn(
            "Disconnect", labels, "Disconnect must hide when not connected"
        )

    def test_unseated_hides_seat_gated_actions(self):
        """Bet / Hit / Stand / Play all require a seat; none must show
        when the player is not at a table.
        """
        state = SimpleNamespace(
            current_table_moniker=None,
            current_table_game_type=None,
            connected=False,
        )
        labels = {o.label for o in self._visible(state)}
        for hidden in ("Bet", "Hit", "Stand", "Play"):
            self.assertNotIn(hidden, labels, f"{hidden!r} must hide when unseated")

    # ---- blackjack seat ----

    def test_seated_at_blackjack_shows_actions_and_hides_launcher(self):
        """At a blackjack table: Bet/Hit/Stand/Play visible; the
        Blackjack launcher hides itself.
        """
        state = SimpleNamespace(
            current_table_moniker="bj-1",
            current_table_game_type="blackjack",
            connected=True,
        )
        labels = {o.label for o in self._visible(state)}
        for must in ("Bet", "Hit", "Stand", "Play"):
            self.assertIn(must, labels, f"{must!r} should be visible at bj")
        self.assertNotIn(
            "Blackjack", labels, "Blackjack launcher must hide when seated at bj"
        )

    # ---- poker seat ----

    def test_seated_at_poker_drops_blackjack_only_actions(self):
        """At a poker table: Hit/Stand hide (blackjack-only); Bet
        stays (allowed types include poker); Play stays; Poker
        launcher hides itself.
        """
        state = SimpleNamespace(
            current_table_moniker="poker-1",
            current_table_game_type="poker",
            connected=True,
        )
        labels = {o.label for o in self._visible(state)}
        for must in ("Bet", "Play"):
            self.assertIn(must, labels, f"{must!r} should be visible at poker")
        for hidden in ("Hit", "Stand"):
            self.assertNotIn(
                hidden, labels, f"{hidden!r} must hide at poker (bj-only)"
            )
        self.assertNotIn(
            "Poker", labels, "Poker launcher must hide when seated at poker"
        )

    # ---- yahtzee seat ----

    def test_seated_at_yahtzee_drops_blackjack_only_actions(self):
        """At a yahtzee table: Hit/Stand hide (blackjack-only); Bet
        hides (not in yahtzee allowed list); Play stays; Yahtzee
        launcher hides itself.
        """
        state = SimpleNamespace(
            current_table_moniker="yahtzee-1",
            current_table_game_type="yahtzee",
            connected=True,
        )
        labels = {o.label for o in self._visible(state)}
        for must in ("Play",):
            self.assertIn(must, labels, f"{must!r} should be visible at yahtzee")
        for hidden in ("Hit", "Stand", "Bet", "Yahtzee"):
            self.assertNotIn(
                hidden,
                labels,
                f"{hidden!r} must hide at yahtzee: Hit/Stand are bj-only, "
                f"Bet is bj+poker only, Yahtzee launcher hides when seated",
            )

    # ---- connection flag ----

    def test_no_connection_hides_disconnect(self):
        """Even for a seated player, Disconnect must hide when
        ``connected`` is False.
        """
        state = SimpleNamespace(
            current_table_moniker="bj-1",
            current_table_game_type="blackjack",
            connected=False,
        )
        labels = {o.label for o in self._visible(state)}
        self.assertNotIn("Disconnect", labels)

    def test_connected_shows_disconnect(self):
        """When connected, Disconnect must be visible even when not
        seated.
        """
        state = SimpleNamespace(
            current_table_moniker=None,
            current_table_game_type=None,
            connected=True,
        )
        labels = {o.label for o in self._visible(state)}
        self.assertIn("Disconnect", labels)

    # ---- post-join window ----

    def test_post_join_window_hides_type_scoped_actions(self):
        """Briefly after join_table, current_table_game_type is
        None. Actions with allowed_game_types must hide (we don't
        know the game yet); Play (no type restriction) must stay.
        """
        state = SimpleNamespace(
            current_table_moniker="some-table",
            current_table_game_type=None,
            connected=True,
        )
        labels = {o.label for o in self._visible(state)}
        # Bet / Hit / Stand have type scopes; they must hide.
        for hidden in ("Bet", "Hit", "Stand"):
            self.assertNotIn(
                hidden,
                labels,
                f"{hidden!r} must hide when game_type is unknown",
            )
        # Play has no type restriction; it stays.
        self.assertIn("Play", labels, "Play should stay without type restriction")


if __name__ == "__main__":
    unittest.main()

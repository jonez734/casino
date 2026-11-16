#!/usr/bin/env python3
# casino/tests/test_registered_types_have_handlers.py
# Every message type the casino server registers to a service must be answered by a handler in
# that game's module. A registered type with no handler is a silent drop: the router hands the
# message to the service, which returns None, and the client waits for a reply that never comes.

import ast
from pathlib import Path

CASINO = Path(__file__).resolve().parents[1]
HANDLER = CASINO / "api" / "handler.py"

# Each game's api_handler answers the types registered for that game's service.
GAME_HANDLERS = {
    "yahtzee": CASINO / "yahtzee" / "api_handler.py",
    "tictactoe": CASINO / "tictactoe" / "api_handler.py",
}


def _literals(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for c in node.comparators:
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    out.add(c.value)
                if isinstance(c, (ast.Tuple, ast.List, ast.Set)):
                    out.update(e.value for e in c.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
        if isinstance(node, ast.Dict):
            out.update(k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
    return out


def _registered_types(tree):
    types = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "register_service" \
                and len(node.args) >= 2 and isinstance(node.args[1], ast.List):
            types.update(e.value for e in node.args[1].elts if isinstance(e, ast.Constant))
    return types


def test_handler_registrations_are_answered_by_a_branch_or_a_game_handler():
    tree = ast.parse(HANDLER.read_text(encoding="utf-8"))
    registered = _registered_types(tree)
    assert registered, "no register_service calls found"
    answered = _literals(tree)
    for game, path in GAME_HANDLERS.items():
        answered |= _literals(ast.parse(path.read_text(encoding="utf-8")))
    unanswered = sorted(t for t in registered if t not in answered)
    assert not unanswered, f"registered but never answered (silent drop): {unanswered}"


def test_each_game_answers_the_types_it_is_registered_for():
    tree = ast.parse(HANDLER.read_text(encoding="utf-8"))
    registered = _registered_types(tree)
    for game, path in GAME_HANDLERS.items():
        mine = {t for t in registered if t.startswith(game + "_")}
        answered = _literals(ast.parse(path.read_text(encoding="utf-8")))
        missing = sorted(mine - answered)
        assert not missing, f"{game} registers {missing} but its api_handler does not answer them"


def test_every_table_message_handled_is_registered_with_the_table_service():
    # The reverse of the check above: a table message with a branch in the router must be registered with the
    # table service, or the transport never routes it there ("No handler for message type").
    tree = ast.parse(HANDLER.read_text(encoding="utf-8"))
    table_types = {"list_tables", "table_info", "create_table", "update_table", "join_table", "leave_table",
                   "add_bot", "remove_bot", "fill_bots", "watch_table", "stop_watching", "show_hands"}
    handled = {t for t in table_types if t in _literals(tree)}
    registered = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "register_service" \
                and node.args and isinstance(node.args[0], ast.Attribute) and node.args[0].attr == "table_service" \
                and len(node.args) >= 2 and isinstance(node.args[1], ast.List):
            registered.update(e.value for e in node.args[1].elts if isinstance(e, ast.Constant))
    unregistered = sorted(handled - registered)
    assert not unregistered, f"handled but not registered with the table service: {unregistered}"

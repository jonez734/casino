#!/usr/bin/env python3
# casino/tests/test_client_screen_init_order.py
# The client must initialize the screen (scroll region for the bottom bar) before anything prints
# or prompts, including the moniker and password prompts. Otherwise the first output lands on an
# unconfigured screen and the bar can scroll away.

import inspect

import pytest

from casino.client import casino_client as cc


def _run_source():
    """The body of run() with its docstring removed, so text in the docstring cannot match."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(cc.CasinoClient._session)))
    fn = tree.body[0]
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(getattr(fn.body[0], "value", None), ast.Constant) else fn.body
    return "\n".join(ast.unparse(stmt) for stmt in body)


@pytest.mark.unit
def test_run_initializes_the_screen_before_the_auth_prompt():
    src = _run_source()
    assert "_ensure_client_screen()" in src, "run() must initialize the screen"
    assert src.index("_ensure_client_screen()") < src.index("cmd_auth()"), (
        "the screen must be initialized before the moniker/password prompts"
    )


@pytest.mark.unit
def test_run_initializes_the_screen_before_attaching_the_bar():
    src = _run_source()
    assert src.index("_ensure_client_screen()") < src.index("_bar.attach("), (
        "the screen must be initialized before the bottom bar is attached"
    )


@pytest.mark.unit
def test_screen_init_runs_once_per_process(monkeypatch):
    from casino.client import casino_client as mod

    calls = []
    monkeypatch.setattr(mod, "_screen_ready", False, raising=False)
    monkeypatch.setattr(mod.screen_mod, "init", lambda *a, **kw: calls.append(kw))
    mod._ensure_client_screen()
    mod._ensure_client_screen()
    assert len(calls) == 1, "screen.init() must run exactly once"

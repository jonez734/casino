# casino/tests/test_casino_login_role.py
# Casino's database connections keep the login role. bed runs each member's request under that
# member's database role; casino's writes are gated by casino's access rules instead, so every
# request-path connection goes through casino.dal.conn, which passes set_role=False.

from __future__ import annotations

import re
from pathlib import Path

import casino

ROOT = Path(casino.__file__).resolve().parent

# Request-path code: must not call database.connect directly. startup, the CLI and the
# maintenance tools run outside a request, and keep their own connections.
REQUEST_PATH = [
    "api/handler.py", "dal/bet.py", "dal/game.py", "dal/player.py", "dal/slots.py", "dal/table.py",
    "services/bank.py", "services/bots.py", "services/game.py", "services/slots.py",
    "tictactoe/service.py", "yahtzee/service.py",
]


def test_the_wrapper_keeps_the_login_role():
    from casino.dal import conn
    import inspect

    src = inspect.getsource(conn.connect)
    assert 'kwargs.setdefault("set_role", False)' in src


def test_request_path_does_not_open_connections_directly():
    offenders = []
    for rel in REQUEST_PATH:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if re.search(r"\bdatabase\.connect\(", text):
            offenders.append(rel)
    assert offenders == [], f"these request-path modules call database.connect directly: {offenders}"


def test_a_connection_keeps_the_login_role_when_a_member_role_is_set():
    from bbsengine6 import database
    from casino.dal import conn

    class FakeConn:
        pass

    seen = {}

    def fake_connect(args, pool=None, **kwargs):
        seen.update(kwargs)
        return FakeConn()

    import casino.dal.conn as mod
    original = mod.database.connect
    mod.database.connect = fake_connect
    database.set_current_role("m_bjbed_a")
    try:
        conn.connect(object())
    finally:
        database.set_current_role(None)
        mod.database.connect = original
    assert seen.get("set_role") is False

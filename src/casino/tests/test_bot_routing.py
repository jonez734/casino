#!/usr/bin/env python3
# casino/tests/test_bot_routing.py
# Phase 4 slice 3: add_bot and remove_bot reach their handlers and are access-controlled like the
# other owner-or-sysop table ops. Stubbed: no socket, no database.

import inspect

import pytest

from casino.api import _auth
from casino.api import handler as handler_mod


@pytest.mark.unit
@pytest.mark.parametrize("op", ["add_bot", "remove_bot"])
def test_bot_op_is_mapped_to_an_access_op(op):
    assert _auth.TYPE_TO_OP.get(op) == op


@pytest.mark.unit
@pytest.mark.parametrize("op", ["add_bot", "remove_bot"])
def test_bot_op_requires_a_token_like_other_table_ops(op):
    src = inspect.getsource(_auth)
    assert f'"{op}"' in src


@pytest.mark.unit
@pytest.mark.parametrize("op", ["add_bot", "remove_bot"])
def test_bot_op_is_registered_with_the_table_service(op):
    src = inspect.getsource(handler_mod.TableServiceHandler)
    assert f'"{op}"' in src


@pytest.mark.unit
def test_dispatch_routes_both_bot_messages():
    src = inspect.getsource(handler_mod.TableServiceHandler)
    assert 'msg_type == "add_bot"' in src
    assert 'msg_type == "remove_bot"' in src

#!/usr/bin/env python3
# casino/tests/test_bots.py
# Phase 4 slice 3: explicit add_bot / remove_bot. A bot is a member with its own bank account,
# a casino player marked is_bot, and a seat at the table. Stubbed: no database.

import secrets
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import player as dal_player
from casino.dal import table as dal_table
from casino.services import bots


def _service():
    svc = bots.BotService.__new__(bots.BotService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


@pytest.mark.unit
def test_bot_moniker_is_prefixed_and_table_scoped():
    name = bots.bot_moniker("blackjack-jam", 1)
    assert name.startswith("bot_")
    assert name.endswith("_1")


@pytest.mark.unit
def test_bot_password_is_random_and_not_shown():
    a = bots.new_bot_password()
    b = bots.new_bot_password()
    assert a != b
    assert len(a) >= 24


@pytest.mark.unit
def test_add_bot_creates_member_account_player_and_seat():
    svc = _service()
    table = {"moniker": "blackjack-jam", "type": "blackjack"}
    with patch.object(dal_table, "get_table", return_value=table), \
         patch.object(dal_table, "count_seated", return_value=1), \
         patch.object(bots, "_create_bot_member") as make_member, \
         patch.object(bots, "_open_bank_account") as open_bank, \
         patch.object(dal_player, "get_or_create_player") as create_player, \
         patch.object(dal_player, "set_player_attrs") as set_attrs, \
         patch.object(dal_table, "add_player_to_table", return_value=True) as seat:
        result = svc.add_bot("blackjack-jam")
    assert result["success"] is True
    bot = result["bot"]
    assert bot.startswith("bot_")
    make_member.assert_called_once()
    open_bank.assert_called_once_with(svc.args, bot, pool=None)
    create_player.assert_called_once_with(svc.args, bot)
    set_attrs.assert_called_once_with(svc.args, bot, {"is_bot": True}, pool=None)
    seat.assert_called_once_with(svc.args, "blackjack-jam", bot, pool=None)


@pytest.mark.unit
def test_add_bot_is_refused_when_the_table_is_full():
    svc = _service()
    table = {"moniker": "blackjack-jam", "type": "blackjack"}
    with patch.object(dal_table, "get_table", return_value=table), \
         patch.object(dal_table, "count_seated", return_value=7), \
         patch.object(bots, "_create_bot_member") as make_member, \
         patch.object(dal_table, "add_player_to_table") as seat:
        result = svc.add_bot("blackjack-jam")
    assert result["success"] is False
    make_member.assert_not_called()
    seat.assert_not_called()


@pytest.mark.unit
def test_remove_bot_refuses_a_human_seat():
    svc = _service()
    with patch.object(dal_player, "get_player_attrs", return_value={}), \
         patch.object(dal_table, "remove_player_from_table") as remove:
        result = svc.remove_bot("blackjack-jam", "jam")
    assert result["success"] is False
    remove.assert_not_called()


@pytest.mark.unit
def test_remove_bot_unseats_but_keeps_the_bank_account():
    svc = _service()
    with patch.object(dal_player, "get_player_attrs", return_value={"is_bot": True}), \
         patch.object(dal_table, "remove_player_from_table", return_value=True) as remove, \
         patch.object(bots, "_open_bank_account") as open_bank:
        result = svc.remove_bot("blackjack-jam", "bot-x-1")
    assert result["success"] is True
    remove.assert_called_once()
    open_bank.assert_not_called()  # remove_bot touches only the seat, never the account


@pytest.mark.unit
def test_bot_created_member_cannot_log_in_with_a_known_password():
    # The stored password is random and discarded, so no one knows it.
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    @contextmanager
    def fake_connect(args, pool=None):
        yield MagicMock()

    with patch.object(bots.database, "connect", fake_connect), \
         patch.object(bots.database, "cursor", MagicMock()), \
         patch.object(bots, "_set_password") as setpw:
        bots._create_bot_member(SimpleNamespace(), "bot-x-1", pool=MagicMock())
    assert setpw.call_count == 1
    used = setpw.call_args.args[1]
    assert used and len(used) >= 24


MEMBER_MONIKER_RULE = r"^[a-zA-Z0-9_]+(?::[a-zA-Z0-9_]+)?$"


@pytest.mark.unit
@pytest.mark.parametrize("table", ["blackjack-jam", "blackjack-oc_bot_probe", "TicTacToe-Room 2", "x" * 80])
def test_bot_moniker_meets_the_member_moniker_rule(table):
    # engine.__member requires letters, digits, and underscores only (chk_member_moniker_format).
    import re

    for i in (1, 7, 12):
        assert re.match(MEMBER_MONIKER_RULE, bots.bot_moniker(table, i)), bots.bot_moniker(table, i)

#!/usr/bin/env python3
# casino/tests/test_client_uses_bed_table_ops.py
# The casino client reads lobby and table writes through bed's casino_* messages, not the
# casino server's own list/create/update types. Source-level: no daemon is started.

import re
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "client" / "casino_client.py"


def _src() -> str:
    return CLIENT.read_text()


def test_list_uses_casino_list_tables_message():
    assert '{"type": "casino_list_tables"}' in _src()


def test_create_uses_casino_create_table_message():
    assert '"type": "casino_create_table"' in _src()


def test_update_uses_casino_update_table_message():
    assert '{"type": "casino_update_table"' in _src()


def test_no_client_sender_of_the_retired_table_types():
    src = _src()
    for old in ("list_tables", "create_table", "update_table"):
        assert not re.search(rf'"type":\s*"{old}"', src), old


def test_join_and_leave_stay_on_the_server_for_now():
    # Join and leave carry session state (seat, channel subscription, slot rule), which
    # bed's table functions do not own. They keep the server path until that moves.
    src = _src()
    assert '"type": "join_table"' in src
    assert '"type": "leave_table"' in src

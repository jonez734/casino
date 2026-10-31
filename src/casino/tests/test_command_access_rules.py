"""Command packages enforce their access rules through ``access()``.

The menu calls ``module.check(args, module_path, op, client=...)`` for each entry.
These rules decide what the player sees: an unauthenticated player sees no
command, admin ops need a sysop, and ``update_table`` needs a sysop or a table
owner. The server still enforces ownership when the command runs.
"""

import unittest
from types import SimpleNamespace

from casino.commands import admin, table


def _client(**attrs):
    base = dict(authenticated=True, is_sysop=False, owns_tables=False)
    base.update(attrs)
    return SimpleNamespace(**base)


class TestAdminAccess(unittest.TestCase):
    def test_unauthenticated_is_denied(self):
        self.assertFalse(admin.access(None, "watch_table", client=_client(authenticated=False)))

    def test_missing_client_is_denied(self):
        self.assertFalse(admin.access(None, "watch_table"))

    def test_sysop_is_allowed_admin_ops(self):
        for op in ("watch_table", "stop_watching", "kick_player"):
            with self.subTest(op=op):
                self.assertTrue(admin.access(None, op, client=_client(is_sysop=True)))

    def test_non_sysop_is_denied_admin_ops(self):
        for op in ("watch_table", "stop_watching", "kick_player"):
            with self.subTest(op=op):
                self.assertFalse(admin.access(None, op, client=_client(is_sysop=False)))


class TestTableAccess(unittest.TestCase):
    def test_unauthenticated_is_denied(self):
        self.assertFalse(table.access(None, "list_tables", client=_client(authenticated=False)))

    def test_authenticated_player_may_list_and_create(self):
        for op in ("list_tables", "create_table", "join_table"):
            with self.subTest(op=op):
                self.assertTrue(table.access(None, op, client=_client()))

    def test_update_is_denied_to_a_player_who_owns_no_table(self):
        self.assertFalse(table.access(None, "update_table", client=_client()))

    def test_update_is_allowed_to_an_owner(self):
        self.assertTrue(table.access(None, "update_table", client=_client(owns_tables=True)))

    def test_update_is_allowed_to_a_sysop(self):
        self.assertTrue(table.access(None, "update_table", client=_client(is_sysop=True)))


if __name__ == "__main__":
    unittest.main()

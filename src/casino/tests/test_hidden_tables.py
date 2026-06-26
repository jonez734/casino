#!/usr/bin/env python3
# casino/tests/test_hidden_tables.py
# Tests for hidden table functionality

import argparse
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class MockCursor:
    def __init__(self, rows=None, fetchone_value=None):
        self._rows = rows or []
        self._fetchone_value = fetchone_value
        self._index = 0
        self.rowcount = len(self._rows) if rows else 0

    def fetchone(self):
        if self._fetchone_value is not None:
            return self._fetchone_value
        if self._index < len(self._rows):
            result = self._rows[self._index]
            self._index += 1
            return result
        return None

    def __iter__(self):
        return iter(self._rows)

    def execute(self, *args, **kwargs):
        pass


class MockConnection:
    def __init__(self, rows=None, fetchone_value=None):
        self._rows = rows or []
        self._fetchone_value = fetchone_value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return MagicMock(return_value=MockCursor(self._rows, self._fetchone_value))


class TestHiddenTableDAL(unittest.TestCase):
    """Test that hidden flag is properly handled at the DAL layer."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test")

    def test_create_table_with_hidden_true(self):
        """Hidden=True is stored when creating a table."""
        from casino.dal import table as dal_table

        mock_row = {
            "moniker": "secret-bj",
            "type": "blackjack",
            "minimumbet": 10,
            "maximumbet": 100,
            "ownermoniker": "owner1",
            "ownersince": None,
            "accountid": 1,
            "cheat": False,
            "cheatpercent": None,
            "attrs": {},
            "shoe_cards": [],
            "shoe_uses": 0,
            "location": "NorthAlpha",
            "status": "open",
            "hidden": True,
        }

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchone.side_effect = [
                {"moniker": "owner1"},
                None,
                {"id": 1},
                mock_row,
            ]
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            result = dal_table.create_table(
                self.args,
                "blackjack",
                "owner1",
                min_bet=10,
                max_bet=100,
                moniker="secret-bj",
                hidden=True,
            )

            self.assertIsNotNone(result)
            self.assertTrue(result["hidden"])

    def test_create_table_default_hidden_false(self):
        """Hidden defaults to False."""
        from casino.dal import table as dal_table

        mock_row = {
            "moniker": "public-bj",
            "type": "blackjack",
            "minimumbet": 10,
            "maximumbet": 100,
            "ownermoniker": "owner1",
            "ownersince": None,
            "accountid": 1,
            "cheat": False,
            "cheatpercent": None,
            "attrs": {},
            "shoe_cards": [],
            "shoe_uses": 0,
            "location": "NorthAlpha",
            "status": "open",
            "hidden": False,
        }

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchone.side_effect = [
                {"moniker": "owner1"},
                None,
                {"id": 1},
                mock_row,
            ]
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            result = dal_table.create_table(
                self.args,
                "blackjack",
                "owner1",
                min_bet=10,
                max_bet=100,
                moniker="public-bj",
            )

            self.assertIsNotNone(result)
            self.assertFalse(result["hidden"])

    def test_list_tables_excludes_hidden_by_default(self):
        """list_tables filters out hidden tables when include_hidden=False."""
        from casino.dal import table as dal_table

        mock_rows = [
            {
                "moniker": "public-bj",
                "type": "blackjack",
                "minimumbet": 10,
                "maximumbet": 100,
                "ownermoniker": "owner1",
                "ownersince": None,
                "accountid": 1,
                "cheat": False,
                "cheatpercent": None,
                "attrs": {},
                "shoe_cards": [],
                "shoe_uses": 0,
                "location": None,
                "status": "open",
                "hidden": False,
            },
        ]

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.__iter__ = MagicMock(return_value=iter(mock_rows))
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            tables = dal_table.list_tables(self.args, include_hidden=False)

            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]["moniker"], "public-bj")
            # Hidden filter should be in the SQL we ran
            sql_str = str(mock_cur.execute.call_args.args[0])
            self.assertIn("hidden", sql_str.lower())

    def test_list_tables_includes_hidden_when_requested(self):
        """list_tables returns hidden tables when include_hidden=True."""
        from casino.dal import table as dal_table

        mock_rows = [
            {
                "moniker": "public-bj",
                "type": "blackjack",
                "minimumbet": 10,
                "maximumbet": 100,
                "ownermoniker": "owner1",
                "ownersince": None,
                "accountid": 1,
                "cheat": False,
                "cheatpercent": None,
                "attrs": {},
                "shoe_cards": [],
                "shoe_uses": 0,
                "location": None,
                "status": "open",
                "hidden": False,
            },
            {
                "moniker": "secret-bj",
                "type": "blackjack",
                "minimumbet": 10,
                "maximumbet": 100,
                "ownermoniker": "owner2",
                "ownersince": None,
                "accountid": 2,
                "cheat": False,
                "cheatpercent": None,
                "attrs": {},
                "shoe_cards": [],
                "shoe_uses": 0,
                "location": None,
                "status": "open",
                "hidden": True,
            },
        ]

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.__iter__ = MagicMock(return_value=iter(mock_rows))
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            tables = dal_table.list_tables(self.args, include_hidden=True)

            self.assertEqual(len(tables), 2)
            self.assertEqual(tables[0]["moniker"], "public-bj")
            self.assertEqual(tables[1]["moniker"], "secret-bj")
            self.assertTrue(tables[1]["hidden"])

    def test_get_table_returns_hidden_field(self):
        """get_table returns the hidden flag for a known table."""
        from casino.dal import table as dal_table

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = {
                "moniker": "secret-bj",
                "type": "blackjack",
                "minimumbet": 10,
                "maximumbet": 100,
                "ownermoniker": "owner2",
                "ownersince": None,
                "accountid": 2,
                "cheat": False,
                "cheatpercent": None,
                "attrs": {},
                "shoe_cards": [],
                "shoe_uses": 0,
                "location": None,
                "status": "open",
                "hidden": True,
            }
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            table = dal_table.get_table(self.args, "secret-bj")
            self.assertIsNotNone(table)
            self.assertTrue(table["hidden"])

    def test_update_table_hidden_flag(self):
        """update_table accepts hidden as a writable field."""
        from casino.dal import table as dal_table

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.rowcount = 1
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            with patch("casino.dal.table.get_table") as mock_get:
                mock_get.return_value = {
                    "moniker": "secret-bj",
                    "type": "blackjack",
                    "minimumbet": 10,
                    "maximumbet": 100,
                    "ownermoniker": "owner2",
                    "status": "open",
                    "hidden": True,
                }

                result = dal_table.update_table(
                    self.args, "secret-bj", hidden=True
                )

                self.assertIsNotNone(result)
                self.assertTrue(result["hidden"])
                # Verify SQL was built with hidden clause
                sql = mock_cur.execute.call_args.args[0]
                self.assertIn("hidden", sql.lower())


class TestHiddenTableService(unittest.TestCase):
    """Test that TableService properly enforces the hidden semantics."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test")

    def test_create_table_with_hidden(self):
        """Service propagates the hidden flag through to the DAL."""
        from casino.services.table import TableService

        with patch("casino.dal.table.create_table") as mock_create:
            mock_create.return_value = {
                "moniker": "secret-bj",
                "type": "blackjack",
                "minimumbet": 10,
                "maximumbet": 100,
                "ownermoniker": "owner1",
                "status": "open",
                "hidden": True,
            }

            service = TableService(self.args)
            result = service.create_table(
                "blackjack", "owner1", min_bet=10, max_bet=100,
                moniker="secret-bj", hidden=True,
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["table"]["hidden"])
            # Verify hidden was passed through to DAL
            _, kwargs = mock_create.call_args
            self.assertTrue(kwargs.get("hidden"))

    def test_list_tables_for_user_excludes_hidden(self):
        """Non-sysop list_tables excludes hidden tables."""
        from casino.services.table import TableService

        with patch("casino.dal.table.list_tables") as mock_list:
            mock_list.return_value = [
                {
                    "moniker": "public-bj",
                    "type": "blackjack",
                    "minimumbet": 10,
                    "maximumbet": 100,
                    "ownermoniker": "owner1",
                    "status": "open",
                    "hidden": False,
                },
            ]
            with patch("casino.dal.table.get_table_players") as mock_players:
                mock_players.return_value = []
                with patch("casino.dal.table.get_table_spectators") as mock_specs:
                    mock_specs.return_value = []

                    service = TableService(self.args)
                    result = service.list_tables(is_sysop=False)

                    self.assertEqual(len(result), 1)
                    self.assertEqual(result[0]["moniker"], "public-bj")
                    # Verify DAL was called with include_hidden=False
                    _, kwargs = mock_list.call_args
                    self.assertFalse(kwargs.get("include_hidden"))

    def test_list_tables_for_sysop_includes_hidden(self):
        """Sysop list_tables includes hidden tables."""
        from casino.services.table import TableService

        with patch("casino.dal.table.list_tables") as mock_list:
            mock_list.return_value = [
                {
                    "moniker": "public-bj",
                    "type": "blackjack",
                    "minimumbet": 10,
                    "maximumbet": 100,
                    "ownermoniker": "owner1",
                    "status": "open",
                    "hidden": False,
                },
                {
                    "moniker": "secret-bj",
                    "type": "blackjack",
                    "minimumbet": 10,
                    "maximumbet": 100,
                    "ownermoniker": "owner2",
                    "status": "open",
                    "hidden": True,
                },
            ]
            with patch("casino.dal.table.get_table_players") as mock_players:
                mock_players.return_value = []
                with patch("casino.dal.table.get_table_spectators") as mock_specs:
                    mock_specs.return_value = []

                    service = TableService(self.args)
                    result = service.list_tables(is_sysop=True)

                    self.assertEqual(len(result), 2)
                    # Verify DAL was called with include_hidden=True
                    _, kwargs = mock_list.call_args
                    self.assertTrue(kwargs.get("include_hidden"))

    def test_update_table_with_hidden_flag(self):
        """update_table accepts hidden flag in updates."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "secret-bj",
            "type": "blackjack",
            "minimumbet": 10,
            "maximumbet": 100,
            "ownermoniker": "owner1",
            "status": "open",
            "hidden": True,
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.update_table") as mock_update:
                mock_get.return_value = mock_table
                mock_update.return_value = {**mock_table, "hidden": True}

                service = TableService(self.args)
                result = service.update_table(
                    "secret-bj", "owner1", is_sysop=False, hidden=True
                )

                self.assertTrue(result["success"])
                self.assertTrue(result["table"]["hidden"])

    def test_update_table_rejects_non_boolean_hidden(self):
        """update_table rejects hidden values that aren't booleans."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "secret-bj",
            "type": "blackjack",
            "ownermoniker": "owner1",
            "status": "open",
            "hidden": False,
        }

        with patch("casino.dal.table.get_table") as mock_get:
            mock_get.return_value = mock_table

            service = TableService(self.args)
            result = service.update_table(
                "secret-bj", "owner1", is_sysop=False, hidden="yes"
            )

            self.assertFalse(result["success"])
            self.assertIn("boolean", result["message"].lower())

    def test_join_hidden_table_known_moniker(self):
        """Any user can join a hidden table if they know the moniker."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "secret-bj",
            "type": "blackjack",
            "ownermoniker": "owner1",
            "status": "open",
            "hidden": True,
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.add_player_to_table") as mock_add:
                mock_get.return_value = mock_table
                mock_add.return_value = True

                service = TableService(self.args)
                result = service.join_table(
                    moniker="secret-bj",
                    player_moniker="random_user",
                    is_sysop=False,
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["moniker"], "secret-bj")

    def test_join_hidden_table_as_sysop(self):
        """Sysops can join hidden tables without restriction."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "secret-bj",
            "type": "blackjack",
            "ownermoniker": "owner1",
            "status": "open",
            "hidden": True,
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.add_player_to_table") as mock_add:
                mock_get.return_value = mock_table
                mock_add.return_value = True

                service = TableService(self.args)
                result = service.join_table(
                    moniker="secret-bj",
                    player_moniker="thsysop",
                    is_sysop=True,
                )

                self.assertTrue(result["success"])


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestHiddenTableDAL))
    suite.addTests(loader.loadTestsFromTestCase(TestHiddenTableService))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())

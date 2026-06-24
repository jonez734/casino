#!/usr/bin/env python3
# casino/tests/test_table_maint.py
# Tests for table maintenance functions (owner/sysop permissions)

import argparse
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class MockCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self._index = 0
        self.rowcount = len(self._rows) if rows else 0

    def fetchone(self):
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
    def __init__(self, rows=None):
        self._rows = rows or []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return MagicMock(return_value=MockCursor(self._rows))


class TestTableService(unittest.TestCase):
    """Test TableService for owner/sysop permission handling."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test")

    def test_update_table_owner_allowed(self):
        """Test that owner can update table fields."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "minimumbet": 10,
            "maximumbet": 100,
            "ownermoniker": "testowner",
            "status": "open",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.update_table") as mock_update:
                mock_get.return_value = mock_table
                mock_update.return_value = {**mock_table, "minimumbet": 20}

                service = TableService(self.args)
                result = service.update_table(
                    "blackjack-test", "testowner", is_sysop=False, minimumbet=20
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["table"]["minimumbet"], 20)

    def test_update_table_sysop_allowed(self):
        """Test that sysop can update any table."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "minimumbet": 10,
            "maximumbet": 100,
            "ownermoniker": "otherowner",
            "status": "open",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.update_table") as mock_update:
                mock_get.return_value = mock_table
                mock_update.return_value = {**mock_table, "status": "closed"}

                service = TableService(self.args)
                result = service.update_table(
                    "blackjack-test", "thsysop", is_sysop=True, status="closed"
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["table"]["status"], "closed")

    def test_update_table_non_owner_denied(self):
        """Test that non-owner non-sysop cannot update table."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "testowner",
            "status": "open",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            mock_get.return_value = mock_table

            service = TableService(self.args)
            result = service.update_table(
                "blackjack-test", "randomuser", is_sysop=False, minimumbet=50
            )

            self.assertFalse(result["success"])
            self.assertIn("owner or sysop", result["message"])

    def test_update_table_status_validation(self):
        """Test that status must be 'open' or 'closed'."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "testowner",
            "status": "open",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            mock_get.return_value = mock_table

            service = TableService(self.args)
            result = service.update_table(
                "blackjack-test", "testowner", is_sysop=False, status="invalid"
            )

            self.assertFalse(result["success"])
            self.assertIn("must be", result["message"])

    def test_update_table_rename(self):
        """Test that owner can rename table."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-oldname",
            "type": "blackjack",
            "ownermoniker": "testowner",
            "status": "open",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.update_table") as mock_update:
                mock_get.return_value = mock_table
                mock_update.return_value = {**mock_table, "moniker": "blackjack-newname"}

                service = TableService(self.args)
                result = service.update_table(
                    "blackjack-oldname", "testowner", is_sysop=False, new_moniker="blackjack-newname"
                )

                self.assertTrue(result["success"])

    def test_reset_shoe_owner_allowed(self):
        """Test that owner can reset shoe."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "testowner",
            "shoe_cards": ["AS", "KS"],
            "shoe_uses": 2,
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.reset_shoe") as mock_reset:
                mock_get.return_value = mock_table
                mock_reset.return_value = True

                service = TableService(self.args)
                result = service.reset_shoe("blackjack-test", "testowner", is_sysop=False)

                self.assertTrue(result["success"])
                mock_reset.assert_called_once()

    def test_reset_shoe_sysop_allowed(self):
        """Test that sysop can reset any shoe."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "otherowner",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.reset_shoe") as mock_reset:
                mock_get.return_value = mock_table
                mock_reset.return_value = True

                service = TableService(self.args)
                result = service.reset_shoe("blackjack-test", "thsysop", is_sysop=True)

                self.assertTrue(result["success"])

    def test_reset_shoe_non_owner_denied(self):
        """Test that non-owner non-sysop cannot reset shoe."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "testowner",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            mock_get.return_value = mock_table

            service = TableService(self.args)
            result = service.reset_shoe("blackjack-test", "randomuser", is_sysop=False)

            self.assertFalse(result["success"])
            self.assertIn("owner or sysop", result["message"])

    def test_delete_table_owner_allowed(self):
        """Test that owner can delete table."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "testowner",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.delete_table") as mock_delete:
                mock_get.return_value = mock_table
                mock_delete.return_value = True

                service = TableService(self.args)
                result = service.delete_table("blackjack-test", "testowner", is_sysop=False)

                self.assertTrue(result["success"])

    def test_delete_table_sysop_allowed(self):
        """Test that sysop can delete any table."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "otherowner",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            with patch("casino.dal.table.delete_table") as mock_delete:
                mock_get.return_value = mock_table
                mock_delete.return_value = True

                service = TableService(self.args)
                result = service.delete_table("blackjack-test", "thsysop", is_sysop=True)

                self.assertTrue(result["success"])

    def test_delete_table_non_owner_denied(self):
        """Test that non-owner non-sysop cannot delete table."""
        from casino.services.table import TableService

        mock_table = {
            "moniker": "blackjack-test",
            "type": "blackjack",
            "ownermoniker": "testowner",
        }

        with patch("casino.dal.table.get_table") as mock_get:
            mock_get.return_value = mock_table

            service = TableService(self.args)
            result = service.delete_table("blackjack-test", "randomuser", is_sysop=False)

            self.assertFalse(result["success"])
            self.assertIn("owner or sysop", result["message"])


class TestTableDAL(unittest.TestCase):
    """Test table DAL functions."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test")

    def test_update_table_min_max_bet(self):
        """Test updating min/max bet via DAL."""
        from casino.dal import table as dal_table

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = {
                "moniker": "blackjack-test",
                "type": "blackjack",
                "minimumbet": 50,
                "maximumbet": 500,
                "ownermoniker": "testowner",
                "status": "open",
            }
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            with patch("casino.dal.table.get_table") as mock_get:
                mock_get.return_value = {
                    "moniker": "blackjack-test",
                    "type": "blackjack",
                    "minimumbet": 10,
                    "maximumbet": 100,
                    "ownermoniker": "testowner",
                    "status": "open",
                }

                result = dal_table.update_table(
                    self.args, "blackjack-test", minimumbet=50, maximumbet=500
                )

                self.assertIsNotNone(result)

    def test_update_table_status(self):
        """Test updating status via DAL."""
        from casino.dal import table as dal_table

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = {
                "moniker": "blackjack-test",
                "type": "blackjack",
                "status": "closed",
            }
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            with patch("casino.dal.table.get_table") as mock_get:
                mock_get.return_value = {
                    "moniker": "blackjack-test",
                    "type": "blackjack",
                    "status": "closed",
                }

                result = dal_table.update_table(
                    self.args, "blackjack-test", status="closed"
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "closed")

    def test_update_table_rename(self):
        """Test renaming table via DAL."""
        from casino.dal import table as dal_table

        with patch("casino.dal.table.database.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = {
                "moniker": "blackjack-newname",
                "type": "blackjack",
                "status": "open",
            }
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_conn

            with patch("casino.dal.table.get_table") as mock_get:
                mock_get.return_value = {
                    "moniker": "blackjack-newname",
                    "type": "blackjack",
                    "status": "open",
                }

                result = dal_table.update_table(
                    self.args, "blackjack-oldname", new_moniker="blackjack-newname"
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["moniker"], "blackjack-newname")

    def test_reset_shoe(self):
        """Test resetting shoe via DAL."""
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

            result = dal_table.reset_shoe(self.args, "blackjack-test")

            self.assertTrue(result)
            mock_cur.execute.assert_called_once()


class TestListTables(unittest.TestCase):
    """Test listing tables includes status."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test")

    def test_list_tables_includes_status(self):
        """Test that list_tables returns status field."""
        from casino.dal import table as dal_table

        mock_rows = [
            {
                "moniker": "blackjack-test1",
                "type": "blackjack",
                "minimumbet": 10,
                "maximumbet": 100,
                "ownermoniker": "owner1",
                "ownersince": None,
                "accountid": 1,
                "bank": 0,
                "earnings": 0,
                "cheat": False,
                "cheatpercent": None,
                "attrs": {},
                "shoe_cards": [],
                "shoe_uses": 0,
                "location": None,
                "status": "open",
            },
            {
                "moniker": "blackjack-test2",
                "type": "blackjack",
                "minimumbet": 20,
                "maximumbet": 200,
                "ownermoniker": "owner2",
                "ownersince": None,
                "accountid": 2,
                "bank": 0,
                "earnings": 0,
                "cheat": False,
                "cheatpercent": None,
                "attrs": {},
                "shoe_cards": [],
                "shoe_uses": 0,
                "location": None,
                "status": "closed",
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

            tables = dal_table.list_tables(self.args)

            self.assertEqual(len(tables), 2)
            self.assertEqual(tables[0]["status"], "open")
            self.assertEqual(tables[1]["status"], "closed")


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestTableService))
    suite.addTests(loader.loadTestsFromTestCase(TestTableDAL))
    suite.addTests(loader.loadTestsFromTestCase(TestListTables))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())

"""
Tests for ``casino.startup.checkcasino``.

These tests pin the module that ensures the ``casino`` schema is
owned by the dedicated ``zoid6`` role (see
``bbsengine6.backend.checkzoid6owner`` and
``bbsengine6.TODO_zoid6_role.md``):

  1. ``init`` returns True, ``buildargs`` returns None, ``access``
     returns True (the four-call contract).
  2. The ``HELPERS`` allow-list matches the loop in
     ``bbsengine6.backend.checkengine``.
  3. The owner gate short-circuits and returns False if any
     SECURITY DEFINER helper is owned by a role outside
     ``("zoid6", "postgres")``.
  4. The owner gate skips a helper that is not yet installed (no
     abort, no error).
  5. When the ``casino`` schema does not exist, ``main`` issues
     ``CREATE SCHEMA casino AUTHORIZATION zoid6``.
  6. When the ``casino`` schema exists and is owned by another
     role, ``main`` issues ``ALTER SCHEMA casino OWNER TO zoid6``.
  7. When the ``casino`` schema already exists and is owned by
     ``zoid6``, ``main`` is a no-op.
  8. ``main`` returns False if the ``ALTER`` raises.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_args():
    args = Mock()
    args.debug = False
    args.databasename = "zoid6"
    return args


def _fake_cursor_context(fetchone_value=None, raise_on_execute=None):
    """Build a mock that quacks like the ``database.cursor`` context
    manager: ``__enter__`` yields a mock cursor whose ``.fetchone()``
    returns ``fetchone_value``, ``.execute()`` either succeeds or
    raises ``raise_on_execute``, and ``__exit__`` is a no-op.
    """
    cur = Mock()
    cur.fetchone.return_value = fetchone_value
    if raise_on_execute is not None:
        cur.execute.side_effect = raise_on_execute
    else:
        cur.execute = Mock()
    cm = Mock()
    cm.__enter__ = Mock(return_value=cur)
    cm.__exit__ = Mock(return_value=False)
    return cm, cur


class TestCheckCasinoContract(unittest.TestCase):
    def setUp(self):
        from casino.startup import checkcasino

        self.mod = checkcasino

    def test_init_returns_true(self):
        self.assertTrue(self.mod.init(_make_args()))

    def test_buildargs_returns_none(self):
        self.assertIsNone(self.mod.buildargs(_make_args()))

    def test_access_returns_true(self):
        self.assertTrue(self.mod.access(_make_args(), op="main"))

    def test_schema_name_is_casino(self):
        self.assertEqual(self.mod.SCHEMA_NAME, "casino")

    def test_target_role_is_zoid6(self):
        self.assertEqual(self.mod.TARGET_ROLE, "zoid6")

    def test_allow_list_includes_zoid6_and_postgres(self):
        self.assertIn("zoid6", self.mod.ACCEPTABLE_HELPER_OWNERS)
        self.assertIn("postgres", self.mod.ACCEPTABLE_HELPER_OWNERS)

    def test_helpers_match_checkengine_list(self):
        """Adding/removing a helper here must also be reflected in
        ``bbsengine6.backend.checkengine``'s verify loop. Pin the
        two lists in lock-step to surface a drift as a test failure
        rather than a silent privilege-escalation hole."""
        import os.path
        checkengine_path = os.path.join(
            os.path.dirname(__file__),
            "../../../../bbsengine6/py/src/bbsengine6/backend/checkengine.py",
        )
        with open(checkengine_path) as fh:
            src = fh.read()
        expected = {
            "public.manage_schema_priv",
            "public.manage_database_priv",
            "public.manage_role_privs",
            "public.manage_secondary_role",
            "public.get_role_privs",
        }
        for name in expected:
            self.assertIn(name, src, f"checkengine.py missing {name!r}")
        self.assertEqual(set(self.mod.HELPERS), expected)


class TestCheckCasinoOwnerGate(unittest.TestCase):
    """The SECURITY DEFINER owner gate at the top of ``main``."""

    def setUp(self):
        from casino.startup import checkcasino

        self.mod = checkcasino
        self.args = _make_args()
        self.fake_conn = Mock()

    def test_short_circuits_when_helper_owner_mismatches(self):
        """If any installed helper has an owner outside the allow-list,
        ``main`` returns False without touching the schema."""
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=False,
             ) as verify, \
             patch.object(
                 self.mod.database, "schemaexists"
             ) as schemaexists:
            result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertFalse(result)
        self.assertEqual(verify.call_count, 1)
        schemaexists.assert_not_called()

    def test_skips_helpers_that_are_not_yet_installed(self):
        """A helper not yet installed (functionexists returns False)
        is silently skipped — no abort, no verify call."""
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=False,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
             ) as verify, \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ) as schemaexists:
            # ``fetchone`` returns a row showing the schema is owned
            # by ``zoid6`` already, so the schema block is a no-op.
            cm, cur = _fake_cursor_context(fetchone_value={"owner": "zoid6"})
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)
        verify.assert_not_called()
        schemaexists.assert_called()
        # Only the SELECT to read the current owner; no ALTER.
        self.assertEqual(cur.execute.call_count, 1)
        sql_text = cur.execute.call_args.args[0]
        self.assertIn("pg_get_userbyid", sql_text)
        self.assertNotIn("ALTER", sql_text)

    def test_continues_when_all_helpers_pass_owner_gate(self):
        """If all installed helpers pass the owner gate, ``main``
        proceeds to the schema block."""
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ):
            cm, cur = _fake_cursor_context(fetchone_value={"owner": "zoid6"})
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)


class TestCheckCasinoSchemaCreate(unittest.TestCase):
    """Schema doesn't exist → ``CREATE SCHEMA casino AUTHORIZATION zoid6``."""

    def setUp(self):
        from casino.startup import checkcasino

        self.mod = checkcasino
        self.args = _make_args()
        self.fake_conn = Mock()

    def test_creates_schema_with_authorization_zoid6(self):
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=False
             ):
            cm, cur = _fake_cursor_context()
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)
        cur.execute.assert_called_once()
        sql_text = cur.execute.call_args.args[0]
        self.assertIn("CREATE SCHEMA casino", sql_text)
        self.assertIn("AUTHORIZATION zoid6", sql_text)

    def test_returns_false_on_create_failure(self):
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=False
             ):
            cm, _cur = _fake_cursor_context(
                raise_on_execute=RuntimeError("simulated DDL failure")
            )
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertFalse(result)


class TestCheckCasinoSchemaReassign(unittest.TestCase):
    """Schema exists, owner != zoid6 → ``ALTER SCHEMA casino OWNER TO zoid6``."""

    def setUp(self):
        from casino.startup import checkcasino

        self.mod = checkcasino
        self.args = _make_args()
        self.fake_conn = Mock()

    def test_reassigns_when_owner_is_opencode(self):
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ):
            cm, cur = _fake_cursor_context(fetchone_value={"owner": "opencode"})
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)
        # First execute: SELECT owner; second execute: ALTER SCHEMA.
        self.assertEqual(cur.execute.call_count, 2)
        sql_texts = [c.args[0] for c in cur.execute.call_args_list]
        self.assertIn("ALTER SCHEMA casino OWNER TO zoid6", sql_texts)

    def test_reassigns_when_owner_is_postgres(self):
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ):
            cm, cur = _fake_cursor_context(fetchone_value={"owner": "postgres"})
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)
        sql_texts = [c.args[0] for c in cur.execute.call_args_list]
        self.assertIn("ALTER SCHEMA casino OWNER TO zoid6", sql_texts)

    def test_returns_false_when_alter_raises(self):
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ):
            # First SELECT returns opencode. Second ALTER raises.
            cur = Mock()
            cur.fetchone.return_value = {"owner": "opencode"}
            cur.execute.side_effect = [
                None,  # SELECT succeeds
                RuntimeError("simulated ALTER failure"),  # ALTER raises
            ]
            cm = Mock()
            cm.__enter__ = Mock(return_value=cur)
            cm.__exit__ = Mock(return_value=False)
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertFalse(result)


class TestCheckCasinoSchemaNoop(unittest.TestCase):
    """Schema exists and owner is already zoid6 → no ALTER."""

    def setUp(self):
        from casino.startup import checkcasino

        self.mod = checkcasino
        self.args = _make_args()
        self.fake_conn = Mock()

    def test_noop_when_owner_is_zoid6_dict_row(self):
        """``database.cursor`` returns dict rows by default; handle
        that form correctly."""
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ):
            cm, cur = _fake_cursor_context(fetchone_value={"owner": "zoid6"})
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)
        # Only one execute: the SELECT. No ALTER.
        self.assertEqual(cur.execute.call_count, 1)
        sql_text = cur.execute.call_args.args[0]
        self.assertNotIn("ALTER", sql_text)

    def test_noop_when_owner_is_zoid6_tuple_row(self):
        """If ``database.cursor`` is configured with a tuple row
        factory, the helper must still find the owner at index 0."""
        with patch.object(
            self.mod.database,
            "functionexists",
            return_value=True,
        ), \
             patch.object(
                 self.mod.database,
                 "verify_function_owner",
                 return_value=True,
             ), \
             patch.object(
                 self.mod.database, "schemaexists", return_value=True
             ):
            cm, cur = _fake_cursor_context(fetchone_value=("zoid6",))
            with patch.object(self.mod.database, "cursor", return_value=cm):
                result = self.mod.main(self.args, conn=self.fake_conn)

        self.assertTrue(result)
        self.assertEqual(cur.execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()

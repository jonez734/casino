"""round-view's sign-in calls the callable named by bed.json ``auth.authenticate``, resolved at startup.

A good value is used. A value that does not resolve against bbsengine6's contract stub fails at the viewer's startup,
with the key and the spec named, not at the first sign-in.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from bbsengine6 import module as be6_module
from casino.tk import viewer_login

import bed


def _bed_json():
    return Path(bed.__file__).resolve().parent / "data" / "bed.json"


class TestConfiguredAuthenticate(unittest.TestCase):
    def test_the_shipped_bed_value_is_what_round_view_resolves(self):
        spec = json.loads(_bed_json().read_text(encoding="utf-8"))["auth"]["authenticate"]
        fn = viewer_login.resolve_authenticate(spec)
        self.assertIs(fn, be6_module.resolve_callable(spec, be6_module._stub_authenticate))

    def test_a_bad_spec_fails_at_startup_with_the_key_named(self):
        with self.assertRaises(ValueError) as ctx:
            viewer_login.resolve_authenticate("no_such_module_xyz:authenticate")
        self.assertIn("auth.authenticate", str(ctx.exception))
        self.assertIn("no_such_module_xyz:authenticate", str(ctx.exception))

    def test_a_callable_that_breaks_the_contract_fails_at_startup(self):
        with patch.object(viewer_login, "_configured_spec", return_value="casino.auth:authenticate"):
            with self.assertRaises(TypeError) as ctx:
                viewer_login.resolve_authenticate("casino.auth:authenticate")
        self.assertIn("casino.auth:authenticate", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

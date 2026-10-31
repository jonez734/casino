"""``--debug`` is an int that defaults to 1. The auth load report prints at level 1+.

The report is not printed on import. It runs from ``main()`` after parsing, so
``args.debug`` decides whether it appears.
"""

import argparse
from unittest.mock import patch

import pytest

from casino import auth, lib

pytestmark = pytest.mark.unit


def _parse(argv):
    return lib.buildargs().parse_known_args(argv)[0]


def test_debug_defaults_to_one():
    assert _parse([]).debug == 1


def test_bare_debug_means_one():
    assert _parse(["--debug"]).debug == 1


def test_debug_takes_an_integer_level():
    assert _parse(["--debug", "2"]).debug == 2
    assert _parse(["--debug", "0"]).debug == 0


def test_report_prints_at_level_one_and_above():
    with patch.object(auth._bbs_io, "echo") as echo:
        auth.report_loaded_from(argparse.Namespace(debug=1))
        auth.report_loaded_from(argparse.Namespace(debug=2))
    assert echo.call_count == 2
    assert "casino.auth loaded from" in echo.call_args.args[0]


def test_report_is_silent_at_level_zero():
    with patch.object(auth._bbs_io, "echo") as echo:
        auth.report_loaded_from(argparse.Namespace(debug=0))
    echo.assert_not_called()


def test_report_is_silent_without_the_flag():
    with patch.object(auth._bbs_io, "echo") as echo:
        auth.report_loaded_from(argparse.Namespace())
    echo.assert_not_called()


def test_importing_auth_prints_nothing():
    import importlib
    import io as stdio
    from contextlib import redirect_stdout

    buf = stdio.StringIO()
    with redirect_stdout(buf), patch("bbsengine6.io.echo") as echo:
        importlib.reload(auth)
    echo.assert_not_called()

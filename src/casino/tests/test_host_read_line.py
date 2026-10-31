"""The host seam carries the free-text menu line.

Hosted, a ``read_menu`` line is read by the hosting program's reader so its terminal
owns the input. Standalone, or hosted with no reader, ``io.inputstring`` reads it.
"""

from unittest.mock import patch

import pytest

from casino import host

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone_after():
    host.unregister_menu()
    yield
    host.unregister_menu()


def test_standalone_reads_through_io_inputstring():
    with patch("casino.host.io.inputstring", return_value="hit") as ins:
        assert host.read_line("> ", verify="v") == "hit"
    ins.assert_called_once()


def test_hosted_reads_through_the_hosting_reader():
    seen = {}

    def reader(prompt, **kw):
        seen["prompt"] = prompt
        seen.update(kw)
        return "table list"

    host.register_line_reader(reader)
    host._hosted = True
    with patch("casino.host.io.inputstring", side_effect=AssertionError("io must not be used")):
        assert host.read_line("> ", verify="v") == "table list"
    assert seen["prompt"] == "> "
    assert seen["verify"] == "v"


def test_hosted_without_a_reader_falls_back_to_io():
    host.register_line_reader(None)
    host._hosted = True
    with patch("casino.host.io.inputstring", return_value="q") as ins:
        assert host.read_line("> ") == "q"
    ins.assert_called_once()


def test_unregister_clears_the_reader():
    host.register_line_reader(lambda *a, **k: "x")
    host._hosted = True
    host.unregister_menu()
    assert host._line_reader is None
    assert host.is_hosted() is False

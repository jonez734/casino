"""The viewer's token file name: round-view.<moniker>.<tty-or-notty>.<hash>.token, always with the hash."""

import hashlib
import re
from unittest.mock import patch

import pytest

from casino.tk import token_name


pytestmark = pytest.mark.unit

SHAPE = re.compile(r"^round-view\.[a-z0-9_-]+\.[A-Za-z0-9_-]+\.[0-9a-f]{8}\.token$")


def test_with_a_tty_the_name_carries_the_tty_and_the_hash():
    with patch.object(token_name, "_tty_name", return_value="pts_4"):
        name = token_name.token_file_name("jam")
    expected = hashlib.sha256(b"jam|pts_4").hexdigest()[:8]
    assert name == f"round-view.jam.pts_4.{expected}.token"
    assert SHAPE.match(name)


def test_with_no_tty_the_name_says_notty_and_hashes_the_pid():
    with patch.object(token_name, "_tty_name", return_value=""):
        name = token_name.token_file_name("jam", pid=4242)
    expected = hashlib.sha256(b"jam|pid4242").hexdigest()[:8]
    assert name == f"round-view.jam.notty.{expected}.token"


def test_two_processes_with_no_tty_get_different_files():
    with patch.object(token_name, "_tty_name", return_value=""):
        a = token_name.token_file_name("jam", pid=1)
        b = token_name.token_file_name("jam", pid=2)
    assert a != b


def test_the_same_terminal_gets_the_same_file_each_run():
    with patch.object(token_name, "_tty_name", return_value="pts_4"):
        assert token_name.token_file_name("jam") == token_name.token_file_name("jam")


def test_case_folds_so_jam_and_Jam_share_one_file():
    with patch.object(token_name, "_tty_name", return_value="pts_4"):
        assert token_name.token_file_name("Jam") == token_name.token_file_name("jam")


def test_two_players_on_two_terminals_do_not_collide():
    with patch.object(token_name, "_tty_name", return_value="pts_4"):
        a = token_name.token_file_name("jam")
    with patch.object(token_name, "_tty_name", return_value="pts_7"):
        b = token_name.token_file_name("jam")
    assert a != b


@pytest.mark.parametrize("bad", ["../etc", "jam/x", "jam.x", "", "j a m"])
def test_a_moniker_that_is_not_a_safe_filename_part_is_refused(bad):
    with pytest.raises(ValueError):
        token_name.token_file_name(bad)


def test_the_path_is_inside_the_directory(tmp_path):
    with patch.object(token_name, "_tty_name", return_value="pts_4"):
        path = token_name.token_file_path(str(tmp_path), "jam")
    assert path.startswith(str(tmp_path) + "/")

"""round-view logs in when there is no usable token file for the player, and never writes a token it did not get from a login."""

import os
from unittest.mock import patch

import pytest

from casino.tk import token_name
from casino.tk import viewer_login


pytestmark = pytest.mark.unit


def test_a_stored_token_skips_the_prompt(tmp_path):
    path = token_name.token_file_path(str(tmp_path), "jam")
    with open(path, "w") as fh:
        fh.write("tok-existing")
    os.chmod(path, 0o600)
    with patch.object(viewer_login, "_prompt") as prompt:
        token = viewer_login.ensure_token(str(tmp_path), "jam", is_usable=lambda t: True)
    prompt.assert_not_called()
    assert token == "tok-existing"


def test_no_file_prompts_and_writes_the_token_it_was_given(tmp_path):
    with patch.object(viewer_login, "_prompt", return_value=("jam", "pw")) as prompt, \
         patch.object(viewer_login, "_login", return_value="tok-new") as login:
        token = viewer_login.ensure_token(str(tmp_path), "jam", is_usable=lambda t: True)
    prompt.assert_called_once()
    login.assert_called_once_with("jam", "pw")
    assert token == "tok-new"
    path = token_name.token_file_path(str(tmp_path), "jam")
    with open(path) as fh:
        assert fh.read().strip() == "tok-new"
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_a_rejected_token_prompts_again_and_overwrites(tmp_path):
    path = token_name.token_file_path(str(tmp_path), "jam")
    with open(path, "w") as fh:
        fh.write("tok-stale")
    os.chmod(path, 0o600)  # as the real writer leaves it: owner-only
    with patch.object(viewer_login, "_prompt", return_value=("jam", "pw")), \
         patch.object(viewer_login, "_login", return_value="tok-fresh"):
        token = viewer_login.ensure_token(str(tmp_path), "jam", is_usable=lambda t: t == "tok-fresh")
    assert token == "tok-fresh"
    with open(path) as fh:
        assert fh.read().strip() == "tok-fresh"


def test_a_failed_login_writes_nothing(tmp_path):
    with patch.object(viewer_login, "_prompt", return_value=("jam", "wrong")), \
         patch.object(viewer_login, "_login", return_value=""):
        token = viewer_login.ensure_token(str(tmp_path), "jam", is_usable=lambda t: False)
    assert token == ""
    assert not os.path.exists(token_name.token_file_path(str(tmp_path), "jam"))


def test_the_moniker_at_the_prompt_names_the_file(tmp_path):
    with patch.object(viewer_login, "_prompt", return_value=("Jam", "pw")), \
         patch.object(viewer_login, "_login", return_value="tok"):
        viewer_login.ensure_token(str(tmp_path), "", is_usable=lambda t: True)
    assert os.path.exists(token_name.token_file_path(str(tmp_path), "jam"))

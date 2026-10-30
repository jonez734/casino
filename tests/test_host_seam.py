"""Stage 8: casino's menu seam chooses LO when hosted, io.inputchoice when standalone.

Covers: standalone uses io.inputchoice with the same arguments; hosted calls the registered
menu with the same arguments and returns its answer; hosted with no menu raises
CasinoHostMissing; unregister returns to standalone.
"""

from unittest.mock import patch

import pytest

from casino import host


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone():
    host.unregister_menu()
    yield
    host.unregister_menu()


def test_standalone_uses_inputchoice_with_same_arguments():
    with patch.object(host.io, "inputchoice", return_value="T") as ic:
        out = host.choose("pick: ", "t,q", default="q", help="help")
    assert out == "T"
    ic.assert_called_once_with("pick: ", "t,q", default="q", help="help")


def test_standalone_is_not_hosted():
    assert host.is_hosted() is False


def test_hosted_calls_the_registered_menu():
    menu = lambda prompt, options, default="", help=None: "P"
    host.register_menu(menu)
    with patch.object(host.io, "inputchoice") as ic:
        out = host.choose("pick: ", "p,q", default="q", help="help")
    assert out == "P"
    ic.assert_not_called()


def test_hosted_passes_prompt_default_and_help_to_the_menu():
    """Hosted menus get the prompt, default, and help unchanged. The options arrive as a
    registry, not a string (see test_hosted_menu_receives_a_registry_of_the_option_letters)."""
    seen = {}

    def menu(prompt, registry, default="", help=None):
        seen.update(prompt=prompt, default=default, help=help)
        return "q"

    host.register_menu(menu)
    host.choose("pick: ", "p,q", default="q", help="help")
    assert seen == {"prompt": "pick: ", "default": "q", "help": "help"}


def test_hosted_is_hosted():
    host.register_menu(lambda *a, **k: "q")
    assert host.is_hosted() is True


def test_hosted_without_menu_raises_rather_than_falling_back():
    host._hosted = True
    host._menu = None
    try:
        with patch.object(host.io, "inputchoice") as ic:
            with pytest.raises(host.CasinoHostMissing):
                host.choose("pick: ", "q", default="q")
        ic.assert_not_called()
    finally:
        host.unregister_menu()


def test_unregister_returns_to_standalone():
    host.register_menu(lambda *a, **k: "P")
    host.unregister_menu()
    assert host.is_hosted() is False
    with patch.object(host.io, "inputchoice", return_value="Q") as ic:
        assert host.choose("pick: ", "q", default="q") == "Q"
    ic.assert_called_once()


def test_hosted_menu_receives_a_registry_of_the_option_letters():
    """The option string 'p,q' becomes a registry whose keys are 'p' and 'q'."""
    seen = {}

    def menu(prompt, registry, default="", help=None):
        seen["keys"] = sorted(registry.keys())
        return "q"

    host.register_menu(menu)
    host.choose("pick: ", "p,q", default="q")
    assert seen["keys"] == ["p", "q"]


def test_option_letters_are_stripped_and_empty_entries_dropped():
    seen = {}

    def menu(prompt, registry, default="", help=None):
        seen["keys"] = sorted(registry.keys())
        return "q"

    host.register_menu(menu)
    host.choose("pick: ", " p , q ,", default="q")
    assert seen["keys"] == ["p", "q"]


def test_init_with_a_host_registers_its_menu():
    """casino.init routes menus through the host's choose when a host is passed."""
    import casino

    menu = lambda prompt, registry, default="", help=None: "q"
    fake_host = type("H", (), {"choose": staticmethod(menu)})()
    with patch.object(casino, "register_module"), \
         patch.object(casino.lib, "runmodule", create=True), \
         patch("casino.here.install", create=True):
        casino.init(None, host=fake_host)
    assert host.is_hosted() is True
    assert host._menu is menu


def test_init_without_a_host_stays_standalone():
    import casino

    with patch.object(casino, "register_module"), \
         patch("casino.here.install", create=True):
        casino.init(None)
    assert host.is_hosted() is False


def test_bare_letter_run_is_one_key_per_character():
    """'hp' means h or p, as io.inputchoice reads it, not a single key 'hp'."""
    seen = {}

    def menu(prompt, registry, default="", help=None):
        seen["keys"] = sorted(registry.keys())
        return "h"

    host.register_menu(menu)
    host.choose("pick: ", "hp", default="h")
    assert seen["keys"] == ["h", "p"]

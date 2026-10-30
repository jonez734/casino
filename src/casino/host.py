"""The seam between casino and the program that hosts it.

Casino runs in two modes:

- Hosted: letteredolive starts casino in-process. LO registers its menu function with
  ``register_menu``, and casino's menus are read through it, so LO owns the terminal input.
- Standalone: casino runs from its own command line. No menu is registered, and menus use
  ``io.inputchoice``.

Casino imports nothing from letteredolive. The dependency points one way: LO calls
``register_menu`` before it runs casino.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from bbsengine6 import io
from bbsengine6.registry import Registry


class CasinoHostMissing(RuntimeError):
    """Casino was started as hosted, and no menu function was registered."""


_menu: Optional[Callable[..., str]] = None
_hosted: bool = False


def register_menu(choose_fn: Callable[..., str]) -> None:
    """Route casino's menus through ``choose_fn``. Called by the hosting program."""
    global _menu, _hosted
    _menu = choose_fn
    _hosted = True


def unregister_menu() -> None:
    """Return to standalone menus. Called when the hosting program is done."""
    global _menu, _hosted
    _menu = None
    _hosted = False


def is_hosted() -> bool:
    return _hosted


def choose(prompt: str, options: str, default: str = "", help: Any = None) -> Optional[str]:
    """Read one menu choice.

    ``options`` is the comma-separated list of valid letters, as ``io.inputchoice`` takes it.

    Hosted: the letters are turned into a ``Registry`` (one entry per letter) and passed to
    the registered menu, which validates against it. Standalone: ``io.inputchoice`` is
    called with the string unchanged. Raises ``CasinoHostMissing`` when hosted and no menu
    is registered, rather than falling back silently.
    """
    if _hosted:
        if _menu is None:
            raise CasinoHostMissing("casino is hosted but no menu function is registered")
        return _menu(prompt, _registry_for(options), default=default, help=help)
    return io.inputchoice(prompt, options, default=default, help=help)


def _registry_for(options: str) -> Registry:
    """A registry whose keys are the letters in ``options``, as typed by the menu."""
    registry = Registry()
    for letter in options.split(","):
        letter = letter.strip()
        if letter:
            registry.add(letter, letter)
    return registry

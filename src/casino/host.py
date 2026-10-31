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
_line_reader: Optional[Callable[..., str]] = None
_hosted: bool = False


def register_menu(choose_fn: Callable[..., str]) -> None:
    """Route casino's menus through ``choose_fn``. Called by the hosting program."""
    global _menu, _hosted
    _menu = choose_fn
    _hosted = True


def register_line_reader(read_fn: Optional[Callable[..., str]]) -> None:
    """Route ``read_menu`` lines through the hosting program's reader. ``None`` keeps
    ``io.inputstring``. Called by the hosting program with the menu seam."""
    global _line_reader
    _line_reader = read_fn


def unregister_menu() -> None:
    """Return to standalone menus. Called when the hosting program is done."""
    global _menu, _hosted, _line_reader
    _menu = None
    _hosted = False
    _line_reader = None


def is_hosted() -> bool:
    return _hosted


def read_line(prompt: str, **kwargs: Any) -> str:
    """Read one free-text line for a ``read_menu`` menu.

    Hosted: the hosting program's line reader reads it, so LO owns the terminal input.
    Standalone, or hosted without a line reader: ``io.inputstring`` reads it. ``kwargs``
    are the ``inputstring`` arguments (``verify``, ``completer``, ``help``).
    """
    if _hosted and _line_reader is not None:
        return _line_reader(prompt, **kwargs)
    return io.inputstring(prompt, "", noneok=True, **kwargs)


def choose(
    prompt: str, options: str, default: Optional[str] = "", help: Any = None, **kwargs: Any
) -> Optional[str]:
    """Read one menu choice.

    ``options`` is the letter list, as ``io.inputchoice`` takes it: comma-separated, or a bare
    run of letters. Extra keyword arguments (for example ``clearline``) are passed to
    ``io.inputchoice`` when standalone. Hosted, LO's menu does not take them, so they are
    dropped.

    Hosted: the letters are turned into a ``Registry`` (one entry per letter) and passed to
    the registered menu, which validates against it. Standalone: ``io.inputchoice`` is
    called with the string unchanged. Raises ``CasinoHostMissing`` when hosted and no menu
    is registered, rather than falling back silently.
    """
    if _hosted:
        if _menu is None:
            raise CasinoHostMissing("casino is hosted but no menu function is registered")
        return _menu(prompt, _registry_for(options), default=default, help=help)
    return io.inputchoice(prompt, options, default=default, help=help, **kwargs)


def _registry_for(options: str) -> Registry:
    """A registry whose keys are the valid answers in ``options``.

    Two forms are used by callers: comma-separated letters (``"s,u,l,q"``) and a bare run of
    letters (``"hp"``). Commas split tokens; a string with no commas is read one character per
    key, as ``io.inputchoice`` reads it.
    """
    registry = Registry()
    if "," in options:
        keys = [token.strip() for token in options.split(",")]
    else:
        keys = list(options.strip())
    for key in keys:
        if key:
            registry.add(key, key)
    return registry

"""Tk user interface for casino.

Requires the ``tk`` extra (Pillow) and Python's tkinter. The core casino package does not import
this module, so casino itself needs neither.

Card art is not shipped with casino. It is read from the directory named by the
``CASINO_CARD_ART`` environment variable, which holds the card images (for example
``ace_of_spades.png``). See :func:`card_art_root`.
"""

from __future__ import annotations

import os

CARD_ART_ENV = "CASINO_CARD_ART"


def card_art_root() -> str:
    """The directory holding the card images, from ``CASINO_CARD_ART``.

    Raises ``RuntimeError`` with the variable name when it is unset or not a directory, so a
    missing card package fails with a message rather than a broken image.
    """
    root = os.environ.get(CARD_ART_ENV, "")
    if not root:
        raise RuntimeError(
            f"the Tk UI needs the card graphics: set {CARD_ART_ENV} to the directory "
            "that holds them (casino does not ship card art)"
        )
    if not os.path.isdir(root):
        raise RuntimeError(f"{CARD_ART_ENV}={root!r} is not a directory")
    return root

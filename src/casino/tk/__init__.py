"""Tk user interface for casino.

Requires the ``tk`` extra (Pillow) and Python's tkinter. The core casino package does not import
this module, so casino itself needs neither.

Card images are not shipped with casino. They come from the playingcarddata package (the bicycle
set by default); ``CASINO_CARD_ART`` can name a directory to override them. See
:mod:`casino.tk.card_images`.
"""

from __future__ import annotations

import os

CARD_ART_ENV = "CASINO_CARD_ART"

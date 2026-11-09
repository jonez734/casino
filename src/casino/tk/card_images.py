"""Card images for the Tk UI, from the playingcarddata package.

The naming and the set come from playingcarddata, so casino and asimov resolve the same file for
the same card. ``CASINO_CARD_ART``, when set to a directory, overrides the package's images (for
example to try a different deck); the card names are the same either way.
"""

from __future__ import annotations

import os

import playingcarddata as pcd

CARD_ART_ENV = "CASINO_CARD_ART"

#: The card back and plain card, by their file names in every playingcarddata set.
CARD_BACK = pcd.CARD_BACK
CARD_BLANK = pcd.CARD_BLANK

#: casino's Card stores the suit as a letter; playingcarddata names suits in full.
SUIT_FROM_LETTER = {"H": "hearts", "D": "diamonds", "C": "clubs", "S": "spades"}


def card_filename(rank: str, suit: str) -> str:
    """The playingcarddata file name for a card (for example ``ace_of_spades.png``)."""
    return pcd.card_filename(rank, suit)


def image_path(filename: str, set_name: str | None = None) -> str:
    """The full path to a card image.

    Uses ``CASINO_CARD_ART`` when it names a directory that holds the file; otherwise the image in
    the playingcarddata set (default ``bicycle``, or the casino config's ``playingcard.set_name``).
    """
    override = os.environ.get(CARD_ART_ENV, "")
    if override and os.path.isfile(os.path.join(override, filename)):
        return os.path.join(override, filename)
    return os.path.join(pcd.set_dir(set_name), filename)

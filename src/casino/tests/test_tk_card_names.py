"""The Tk card names resolve to the playingcarddata images, for every card, the back and the blank."""

import os
from types import SimpleNamespace

import pytest

from casino.tk import card_images
from casino.tk.cards import tkCard

pytestmark = pytest.mark.unit


def _card(pips, suit, facedown=False):
    card = tkCard.__new__(tkCard)
    card.pips = pips
    card.suit = suit
    card.facedown = facedown
    card.shorthand = f"{pips}{suit}" if pips else ""
    return card


@pytest.mark.parametrize("pips", ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"])
@pytest.mark.parametrize("suit", ["H", "D", "C", "S"])
def test_every_card_maps_to_a_packaged_image(pips, suit):
    name = _card(pips, suit).getartpath()
    assert os.path.isfile(card_images.image_path(name)), name


def test_card_back_is_the_packaged_back():
    name = _card("A", "S", facedown=True).getartpath()
    assert name == card_images.CARD_BACK
    assert os.path.isfile(card_images.image_path(name))


def test_blank_card_is_the_packaged_blank():
    name = _card(None, None).getartpath()
    assert name == card_images.CARD_BLANK
    assert os.path.isfile(card_images.image_path(name))

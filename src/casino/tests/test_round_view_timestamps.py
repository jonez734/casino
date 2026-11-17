"""Every line the round view shows is prefixed with the time it was shown, as HH:MM:SS."""

import datetime

import pytest

from casino.tk import roundview


pytestmark = pytest.mark.unit


def test_a_line_is_stamped_with_the_time_it_is_shown():
    fixed = datetime.datetime(2026, 11, 17, 14, 5, 9)
    assert roundview.stamp_line("Your hand: 9H 3C [12]", clock=lambda: fixed) == "14:05:09  Your hand: 9H 3C [12]"


def test_the_stamp_is_hours_minutes_seconds_only():
    fixed = datetime.datetime(2026, 1, 2, 23, 59, 1)
    assert roundview.stamp_line("x", clock=lambda: fixed).startswith("23:59:01  ")


def test_an_empty_line_is_still_stamped():
    fixed = datetime.datetime(2026, 11, 17, 9, 0, 0)
    assert roundview.stamp_line("", clock=lambda: fixed) == "09:00:00  "

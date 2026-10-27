#!/usr/bin/env python3
# casino/tests/test_router_accepts_config_kwarg.py
# zoid6's MessageRouter forwards config= to each sub-router along with the auth wiring. If the casino
# MessageRouter rejects config=, zoid6 falls back to RouterClass(args) with no secret, token store, or
# instance ID, and every write op is refused in door mode. The router must accept config=.
import inspect

import pytest

from casino.api import handler as handler_mod


@pytest.mark.unit
def test_casino_message_router_accepts_the_config_kwarg():
    params = inspect.signature(handler_mod.MessageRouter.__init__).parameters
    assert "config" in params, "casino MessageRouter must accept config= from the zoid6 router"


@pytest.mark.unit
def test_casino_message_router_still_receives_the_auth_wiring():
    params = inspect.signature(handler_mod.MessageRouter.__init__).parameters
    for name in ("secret", "token_store", "instance_id"):
        assert name in params, name

"""casino supplies @here: the group for the sender's current table."""

from unittest.mock import patch

import pytest

from casino import here as casino_here

ARGS = object()


@pytest.mark.unit
def test_resolver_returns_table_group_for_seated_sender():
    from bbsengine6.message import service as svc
    with patch.object(svc, "set_here_resolver"):
        casino_here.install(ARGS)
    with patch.object(casino_here, "current_table_moniker", return_value="jam"):
        assert casino_here.resolve_here("alice") == "table:jam"


@pytest.mark.unit
def test_resolver_returns_none_when_not_seated():
    with patch.object(casino_here, "current_table_moniker", return_value=None):
        assert casino_here.resolve_here("alice") is None


@pytest.mark.unit
def test_resolver_returns_none_without_sender():
    assert casino_here.resolve_here(None) is None


@pytest.mark.unit
def test_install_registers_with_bbsengine6():
    from bbsengine6.message import service as svc

    with patch.object(svc, "set_here_resolver") as reg:
        casino_here.install(ARGS)
    reg.assert_called_once_with(casino_here.resolve_here)

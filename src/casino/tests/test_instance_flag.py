"""--instance is a global casino option, and the entry refuses before dispatch when the bed name differs."""

import argparse
from unittest.mock import patch

import pytest

from casino import _routing


@pytest.mark.unit
def test_instance_is_a_casino_routing_option():
    p = argparse.ArgumentParser()
    _routing.build_client_args(p)
    assert p.parse_args(["--instance", "zoid6"]).instance == "zoid6"


@pytest.mark.unit
def test_entry_refuses_before_dispatch_when_name_check_fails():
    import casino.__main__ as entry
    args = argparse.Namespace(instance="wrong")
    with patch.object(entry.lib, "buildargs") as build, \
         patch.object(entry._routing, "select_backend", return_value="bed"), \
         patch("bed.tools.auth._check_instance_name", return_value=False), \
         patch.object(entry, "_run_bed") as dispatch:
        build.return_value.parse_known_args.return_value = (args, [])
        code = entry.main(["--instance", "wrong"])
    assert code == 1
    dispatch.assert_not_called()

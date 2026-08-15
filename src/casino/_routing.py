# casino/_routing.py
# Default-backend selector for the merged ``casino`` entry point.
#
# Two responsibilities:
#
# - Register the ``--bed-*`` client flags + the ``--direct`` opt-out on a
#   shared argparse parent so the merged CLI exposes the same wiring
#   knobs as :mod:`bed.tools`. Mirrors the convention in
#   ``bed.tools._routing`` so casino's standalone entry behaves like
#   every other bed client tool (default = bed daemon, ``--direct``
#   opts out to local Postgres).
#
# - Pick the backend at startup: ``"bed"`` (the WebSocket) by default,
#   ``"direct"`` (the local DB through ``bbsengine6.database``) when
#   the operator passes ``--direct``. If ``--direct`` is not set and
#   the bed daemon is unreachable on the configured host/port, raise
#   :class:`bed.tools._routing.BedNotReachable` so the merged CLI
#   exits non-zero with a clear message rather than silently splitting
#   traffic. Reuses :class:`bed.tools._routing.BedNotReachable` so the
#   bundled one-line operator-facing message is shared with the rest
#   of the bed tool family.
#
# The dispatcher (``casino.__main__``) catches
# :class:`bed.tools._routing.BedNotReachable` and exits non-zero.

from __future__ import annotations

import argparse
from typing import Literal

from bed.client.probe import probe_bed
from bed.tools._routing import BedNotReachable

Backend = Literal["bed", "direct"]


def build_client_args(parentparser: argparse.ArgumentParser) -> None:
    """Add the ``--bed-*`` + ``--direct`` flags used by the merged CLI."""
    group = parentparser.add_argument_group("bed client options")
    group.add_argument(
        "--bed-host",
        dest="bed_host",
        default="localhost",
        help="bed WebSocket host (default: localhost)",
    )
    group.add_argument(
        "--bed-port",
        dest="bed_port",
        type=int,
        default=8765,
        help="bed WebSocket port (default: 8765)",
    )
    group.add_argument(
        "--bed-path",
        dest="bed_path",
        default="/",
        help="bed URL path (default: /)",
    )
    group.add_argument(
        "--bed-call-timeout",
        dest="bed_call_timeout",
        type=float,
        default=5.0,
        help="bed RPC timeout in seconds (default: 5.0)",
    )
    group.add_argument(
        "--bed-probe-timeout",
        dest="bed_probe_timeout",
        type=float,
        default=0.25,
        help="bed TCP probe timeout in seconds (default: 0.25)",
    )
    group.add_argument(
        "--direct",
        dest="direct",
        action="store_true",
        default=False,
        help=(
            "Talk to the local database directly via bbsengine6 "
            "instead of routing through the bed daemon. Use when "
            "bed is not running."
        ),
    )


def select_backend(args) -> Backend:
    """Pick the backend for ``args``.

    Returns ``"direct"`` when ``--direct`` is set, regardless of bed
    reachability (the probe is skipped). Returns ``"bed"`` when bed is
    reachable on the configured host/port. Raises
    :class:`bed.tools._routing.BedNotReachable` when bed is
    unreachable and ``--direct`` was not requested.
    """
    if getattr(args, "direct", False):
        return "direct"
    if probe_bed(args):
        return "bed"
    raise BedNotReachable(
        getattr(args, "bed_host", "localhost"),
        int(getattr(args, "bed_port", 8765)),
    )

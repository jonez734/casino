# commands/_auth.py
# Shared client-gate helpers for ``commands/<x>/lib.py`` modules.
#
# Every casino subcommand (bank, slots, table, etc.) needs the same
# defense-in-depth check before it sends a wire op: a registered
# client object must be authenticated and have a non-empty moniker
# before we hand it to the per-op access policy. ``get_client()``
# only returns a registered client after a successful connect, so
# ``client is None`` already covers the never-connected case; these
# helpers cover the edge cases where the registry holds a half-built
# client (auth aborted, token rejected, disconnect in flight).
#
# Imported as ``from ._auth import _require_authenticated_client`` by
# every command module that drives a wire op through the WS client.

from __future__ import annotations

from typing import Any, Optional

from bbsengine6 import io


def _require_authenticated_client(client: Any, op: str) -> Optional[Any]:
    """Refuse to drive a wire op without a fully-authenticated client.

    Returns the client unchanged when all three conditions hold:

      * ``client`` is not ``None``
      * ``client.authenticated`` is truthy
      * ``client.moniker`` is a non-empty string

    Otherwise prints a single-line error and returns ``None``. The
    caller short-circuits on ``None``. Independent of (and
    complementary to) the ``bbsengine6.casino.access`` /
    ``bbsengine6.bank.access`` policy gate the wire op itself runs
    through: if the local CLI is missing the auth handshake, the
    server-side gate would deny anyway, but we'd rather short-circuit
    so the CLI doesn't carry the half-built client all the way to
    the wire.
    """
    if client is None:
        io.echo(
            f"Operation '{op}' requires an authenticated session. "
            f"Use Connect first.",
            level="error",
        )
        return None
    if not getattr(client, "authenticated", False):
        io.echo(
            f"Operation '{op}' requires an authenticated session. "
            f"Authentication did not complete.",
            level="error",
        )
        return None
    if not (getattr(client, "moniker", "") or "").strip():
        io.echo(
            f"Operation '{op}' requires an authenticated session. "
            f"Client has no moniker.",
            level="error",
        )
        return None
    return client

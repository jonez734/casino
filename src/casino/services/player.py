# casino/services/player.py
# Player service - authentication and profile management
#
# Casino has its own auth on top of the BBS member layer (``bbsengine6.member``)
# so many concurrent members can play casino at once. Each BBS member can
# own many casino player records (``casino.__player``); the player record
# holds casino-specific state (``lastplayed``, ``attrs``, ``stats``)
# keyed by ``moniker citext NOT NULL PK`` with ``membermoniker`` as a
# nullable FK to ``engine.__member(moniker)``. The legacy 1:1 shape
# (``moniker = membermoniker``) is preserved on the lazy-materialize
# path so existing callers see no behavioural change; multi-player-per-
# member is a follow-up that adds distinct ``moniker`` values.
#
# Lifecycle:
#
# - The casino player row is **lazily** materialized the first time a
#   member touches casino. There is no explicit ``casino init <moniker>``
#   step. Both entry paths converge on a single helper,
#   :func:`ensure_casino_player`, so a row created by one path is visible
#   to the other on the next read.
#
# - When ``audit=True`` (the door-mode default), an auto-created row emits
#   one debug-level ``io.echo`` so a sysop running ``casino --debug`` can
#   see who was auto-materialized. WS-client auth and tests pass
#   ``audit=False`` to keep the wire and test output silent.
#
# See ``casino/docs/AUTH.md`` ("Member vs casino player") and
# ``casino/SPEC.md`` §2 ("Member vs casino player") for the rationale.

from __future__ import annotations

from typing import Any, Optional

from bbsengine6 import database, io, member

from casino.dal import player as dal_player


def ensure_casino_player(
    args: Any,
    moniker: str,
    *,
    pool: Any = None,
    audit: bool = False,
) -> dict[str, Any]:
    """Idempotently ensure a ``casino.__player`` row exists for ``moniker``.

    On the legacy 1:1 lazy-materialize path, ``moniker`` is also the
    membermoniker (``ensure_casino_player(args, 'jam')` INSERTs
    ``moniker='jam', membermoniker='jam'``); callers that want a
    distinct player moniker per member pass it explicitly. Returns the
    row (existing or newly created). The returned dict has keys:
    ``membermoniker``, ``moniker``, ``location``, ``lastplayed``,
    ``attrs``.

    When ``audit`` is True and the row was newly created, emits one
    ``io.echo(..., level="debug")`` so a sysop running with debug
    logging can audit who was auto-materialized. The audit echo is
    silent by default (and in tests).

    The caller passes ``pool`` to reuse an existing connection pool
    (CONN_POOL_PATTERN); when ``pool`` is None, the helper falls back
    to ``database.getpool(args, ...)``.
    """
    existing = dal_player.get_player_by_moniker(args, moniker)
    if existing is not None:
        return existing

    if audit:
        io.echo(
            f"casino.services.player.ensure_casino_player: "
            f"auto-creating casino.__player row for {moniker}",
            level="debug",
        )
    return dal_player.get_or_create_player(args, moniker)


class PlayerService:
    """Service for player authentication and management."""

    def __init__(self, args: Any):
        self.args = args

    def _pool(self) -> Any:
        """Return the connection pool to use for member credential checks.

        bbsengine6.member requires the caller to own the pool
        (CONN_POOL_PATTERN). bed puts a pool on ``args.pool`` at startup;
        reuse it when present, otherwise fall back to the cached
        ``database.getpool``.
        """
        pool = getattr(self.args, "pool", None)
        if pool is not None:
            return pool
        return database.getpool(self.args, database=self.args.databasename)

    def authenticate(self, moniker: str, password: str) -> dict[str, Any]:
        """
        Authenticate a player via BBS member credentials.

        Returns:
            Dict with success, moniker, balance, message
        """
        pool = self._pool()
        # Verify member exists
        if not member.verifyMemberFound(
            self.args, moniker, column="moniker", pool=pool
        ):
            return {
                "success": False,
                "moniker": "",
                "balance": 0,
                "message": "Member not found",
            }

        # Check if member has a password set
        has_pwd = member.has_password(self.args, moniker, pool=pool)

        # If member has a password, verify it
        if has_pwd:
            result = member.checkpassword(self.args, password, moniker, pool=pool)
            if result is None or result is False:
                return {
                    "success": False,
                    "moniker": moniker,
                    "balance": 0,
                    "message": "Invalid password",
                }

        # Idempotently materialize the casino player record. WS-client
        # auth path goes through here on every successful login; the
        # helper is a no-op read once the row exists, and a single
        # INSERT + debug-level audit echo on the first login. Door mode
        # also calls :func:`ensure_casino_player` directly from
        # ``lib.CasinoPlayer.__init__``, so the row materialized by
        # either path is visible to the other.
        ensure_casino_player(self.args, moniker, pool=pool, audit=False)

        # Get balance
        balance = dal_player.get_player_balance(self.args, moniker)

        return {
            "success": True,
            "moniker": moniker,
            "balance": balance,
            "message": "Authentication successful",
        }

    def get_balance(self, moniker: str) -> int:
        """Get player's current balance."""
        return dal_player.get_player_balance(self.args, moniker)

    def update_lastplayed(self, moniker: str) -> None:
        """Update player's last played timestamp."""
        dal_player.update_player_lastplayed(self.args, moniker)

    def get_profile(self, moniker: str) -> Optional[dict[str, Any]]:
        """Get player profile."""
        return dal_player.get_player_by_moniker(self.args, moniker)

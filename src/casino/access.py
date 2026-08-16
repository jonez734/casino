# casino/access.py
# Authorization policy for casino WebSocket operations.
#
# Owns the per-op authorization policy for every casino WS message
# type. The casino WS handler in casino/api/handler.py delegates each
# per-op decision to :func:`access` so the policy lives in one place
# and the wire-shape / token / session gates stay in the handler.
#
# Mirrors the bbsengine6.bank pattern: a module-level access() function
# takes ``args``, ``op`` (domain verb), and ``session`` / ``message``
# kwargs, and returns True iff the session may perform ``op``.
#
# Recognized op values:
#   "list_tables"     -- list lobby tables (public)
#   "create_table"    -- create a new table (caller becomes owner)
#   "update_table"    -- mutate a table (owner or sysop)
#   "join_table"      -- take a seat at a table
#   "leave_table"     -- leave the seat at a table
#   "watch_table"     -- spectate a table
#   "stop_watching"   -- stop spectating a table
#   "kick_player"     -- remove a player from a table (owner/sysop)
#   "bet"             -- place a bet at a table
#   "hit"/"stand"/"double"/"split"/"surrender"
#                      -- blackjack hand actions
#   "chat_table"      -- in-table chat
#   "chat_global"     -- lobby chat
#   "emote"           -- in-character message (table-scoped if seated)
#   "slot_spin"       -- pull the lever on a slot table
#   "slot_paytable"   -- read a slot table's payout table
#   "slot_history"    -- read a player's recent spins (self or sysop)
#   "slot_table_history" -- read a table's recent spins (seated player
#                           or sysop; mirrors slot_spin / slot_paytable)
#   "yahtzee_quick_play"/"yahtzee_roll"/"yahtzee_reroll"/"yahtzee_score"
#                      -- yahtzee hand actions
#   "tictactoe_quick_play"/"tictactoe_move"/"tictactoe_resign"/"tictactoe_join"
#                      -- tic-tac-toe actions
#   "whoami"          -- read the authenticated casino player record
#   "player_balance"  -- read casino.player balance (self or sysop)
#   "player_profile"  -- read casino.player row (self or sysop)

from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

__all__ = ["access"]


def _moniker_eq(a: Optional[str], b: Optional[str]) -> bool:
    """Case-insensitive moniker comparison after strip."""
    if not a or not b:
        return False
    return a.strip().lower() == b.strip().lower()


def _get_session(kwargs: Dict[str, Any]) -> Optional[Any]:
    return kwargs.get("session")


def _get_message(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    msg = kwargs.get("message")
    return msg if isinstance(msg, dict) else {}


def _get_claims(message: Dict[str, Any]) -> Dict[str, Any]:
    """Return the decoded claims sub-dict, or empty dict if absent/malformed.

    The bed handler decodes the HMAC-signed token before calling
    access() and stuffs the resulting claims under message["claims"].
    access() never reads the raw token.
    """
    claims = message.get("claims")
    return claims if isinstance(claims, dict) else {}


def _auth_moniker(kwargs: Dict[str, Any]) -> Optional[str]:
    """Return the claim-derived moniker, falling back to session."""
    message = _get_message(kwargs)
    claims = _get_claims(message)
    if claims.get("moniker"):
        return claims["moniker"]
    session = _get_session(kwargs)
    return getattr(session, "moniker", None)


def _auth_is_sysop(kwargs: Dict[str, Any]) -> bool:
    """Return the claim-derived is_sysop, falling back to session."""
    message = _get_message(kwargs)
    claims = _get_claims(message)
    if "is_sysop" in claims:
        return bool(claims["is_sysop"])
    session = _get_session(kwargs)
    return bool(getattr(session, "is_sysop", False))


def _at_table(kwargs: Dict[str, Any], target: str) -> bool:
    """True when the session's bound table matches ``target`` (or the
    session is seated at any table when ``target`` is empty)."""
    session = _get_session(kwargs)
    if session is None:
        return False
    bound = getattr(session, "table_moniker", None)
    if not bound:
        return False
    if not target:
        return True
    return _moniker_eq(bound, target)


def _is_owner(kwargs: Dict[str, Any], table_moniker: str) -> bool:
    """True when the session is the owner of the table.

    The casino router is responsible for resolving the table owner from
    the DB and stashing it on the message under ``message["owner"]``.
    A session whose claim-derived moniker matches that owner wins.
    """
    message = _get_message(kwargs)
    owner = (message.get("owner") or "").strip()
    if not owner:
        return False
    return _moniker_eq(_auth_moniker(kwargs), owner)


def access(args: argparse.Namespace, op: str, /, **kwargs: Any) -> bool:
    """Authorize ``op`` for the given session/message pair.

    Returns True if the session is allowed to perform ``op`` on the
    target described by ``message``; False otherwise. The caller
    decides how to surface the denial (forbidden envelope, CLI error,
    etc.).

    Convention: ``op`` is a domain verb (the operation the caller
    wants to perform), not the wire-protocol message type. The
    casino WS handler maintains its own ``message_type -> op``
    mapping and calls this function with the domain verb.

    Required kwargs (both optional, both default to "deny"):
      session : bed.api.session.SessionState (or any object with
                ``.moniker: str``, ``.is_sysop: bool`` and
                ``.table_moniker: Optional[str]`` attributes), or
                ``None`` for an unbound websocket.
      message : dict, the incoming wire-shaped payload. If the bed
                handler verified a bearer token for this op, the
                decoded claims live under ``message["claims"]``;
                access() uses the claim-derived ``moniker`` /
                ``is_sysop`` instead of the in-memory session
                attributes because they come from a
                cryptographically verified source. The casino router
                is responsible for resolving the table owner from
                the DB and stashing it on the message under
                ``message["owner"]`` for ``update_table`` /
                ``kick_player`` checks.

    The function does NOT perform input validation (moniker present,
    amount > 0, etc.). That is the caller's job and lives next to
    the wire-envelope shape checks. Mixing validation into access()
    would couple it to wire-protocol codes.
    """
    session = _get_session(kwargs)

    # At module-load time (bbsengine6.module.check calls us with op="run"
    # and no extra kwargs), there is no session yet. We allow the module
    # to load for anyone; the per-op rules below only fire when the
    # caller passes a ``session`` kwarg.
    if "session" not in kwargs:
        return True

    if op == "list_tables":
        return True

    # Runtime call: session kwarg was explicitly passed. ``None`` means
    # the websocket is unbound, which is always a denial (every casino
    # op other than ``list_tables`` requires an authenticated session).
    if session is None:
        return False

    auth_sysop = _auth_is_sysop(kwargs)
    auth_moniker = _auth_moniker(kwargs)

    if op == "create_table":
        return bool(auth_moniker)

    if op in ("update_table", "kick_player"):
        if auth_sysop:
            return True
        target = (_get_message(kwargs).get("table_moniker") or "").strip()
        if not target:
            return False
        return _is_owner(kwargs, target)

    if op in ("join_table", "leave_table", "watch_table", "stop_watching"):
        return bool(auth_moniker)

    if op in ("bet", "hit", "stand", "double", "split", "surrender"):
        target = (_get_message(kwargs).get("table_moniker") or "").strip()
        if not auth_moniker:
            return False
        return _at_table(kwargs, target)

    if op in ("chat_table", "chat_global", "emote"):
        return bool(auth_moniker)

    if op in ("slot_spin", "slot_paytable", "slot_table_history"):
        target = (_get_message(kwargs).get("table_moniker") or "").strip()
        if not auth_moniker:
            return False
        return _at_table(kwargs, target)

    if op == "slot_history":
        target = (_get_message(kwargs).get("moniker") or "").strip()
        if not target:
            return False
        if auth_sysop:
            return True
        return _moniker_eq(auth_moniker, target)

    if op in (
        "yahtzee_quick_play",
        "yahtzee_roll",
        "yahtzee_reroll",
        "yahtzee_score",
        "tictactoe_quick_play",
        "tictactoe_move",
        "tictactoe_resign",
        "tictactoe_join",
    ):
        target = (_get_message(kwargs).get("table_moniker") or "").strip()
        if not auth_moniker:
            return False
        # quick_play creates a fresh table, so no seat-at check.
        if op.endswith("quick_play"):
            return True
        return _at_table(kwargs, target)

    if op == "whoami":
        # Any authenticated user can read their own casino.player record.
        return bool(auth_moniker)

    if op in ("player_balance", "player_profile"):
        # Self-or-sysop: a player can read their own casino.player row,
        # a sysop can read anyone's. Mirrors the slot_history rule above.
        target = (_get_message(kwargs).get("moniker") or "").strip()
        if not auth_moniker or not target:
            return False
        if auth_sysop:
            return True
        return _moniker_eq(auth_moniker, target)

    return False

# casino/services/slots.py
# Slot service for the BED: spin, history, paytable lookup.
#
# Atomic transaction model
# ------------------------
# A single spin is a single atomic transaction: the bank move
# (bet debit + payout credit), the casino.__slot_spin audit row,
# and the player stats updates all commit together or roll back together.
# This diverges from blackjack's per-step model (debit on bet, credit
# on resolution) because slots has no inter-player settlement window.
# Disconnect mid-spin is a non-event: the transaction either commits
# or doesn't happen, so there is no in-flight bet to recover.
#
# Settlement + auth token
# -----------------------
# The spin settles through ``engine.casino_settle_spin`` (sql/casino_settle_spin_functions.sql), a
# casino-owned SECURITY DEFINER function. It does the bank move, writes the casino.__slot_spin audit
# row, and bumps the player's stats in one transaction. The acting moniker comes from the verified
# token row in engine.__bed_token; the request names no player. The function is granted to
# bed_zoid6, the login role casino's connections use (casino/dal/conn.py keeps the login role).
#
# The bearer token reaches this module on ``state.auth_service_token``; its SHA-256 digest is
# what the function checks. Door-mode and unit-test callers without a token are refused before any
# SQL runs.
#
# The call from the casino WS handler goes through ``casino.api.handler.SlotServiceHandler``. The
# token is injected on every wire call by ``CasinoClient.send``, and the WS handler validates it
# before ``handle_spin`` runs.

from __future__ import annotations
from casino.dal import conn as casino_conn

import uuid
from typing import Any, Dict, Optional

from bbsengine6 import database, io

from casino.dal import slots as dal_slots
from casino.dal import table as dal_table
from casino.slots.dealer import SlotDealer
from casino.slots.lib import (
    DEFAULT_SYMBOLS,
    RNG,
    Paytable,
    default_reels,
)

# Per-table dealer cache. Key: table_moniker. Value: SlotDealer.
# A dealer is built lazily from the table's reel/paytable config and
# pinned for the life of the table.
_dealers: dict[str, SlotDealer] = {}


def _resolve_rtp_floor_ceil() -> tuple[float, float]:
    from casino.slots.lib import RTP_CEIL, RTP_FLOOR
    return RTP_FLOOR, RTP_CEIL


def _build_paytable_from_config(config: dict[str, Any]) -> Paytable:
    """Build a Paytable from the table's SlotsConfig dict.

    For v1, the only config that affects the Paytable is
    ``config.paytable_override``. Everything else (reel set, target RTP)
    is informational / validation; the default reel strips + paytable
    are used unless an override is supplied.

    The override accepts two formats so it can survive a round trip
    through the database (PostgreSQL JSONB does not allow tuple keys):

    - **list-of-dicts** (DB-friendly): ``[{"symbols": ["CHERRY"],
      "multiplier": 99}]``. This is the recommended format for any
      override that needs to be stored in ``attrs.paytable_override``.
    - **dict with list/tuple keys** (in-memory legacy):
      ``{("CHERRY",): 99}``. Useful for callers that construct the
      config in-process without round-tripping through the DB.
    """
    override = config.get("paytable_override")
    if override is None:
        return Paytable()
    parsed: dict[tuple[str, ...], int] = {}
    if isinstance(override, list):
        for entry in override:
            if not isinstance(entry, dict):
                io.echo(f"slots: paytable_override entry not a dict: {entry!r}", level="error")
                raise ValueError(f"paytable_override entries must be dicts, got {entry!r}")
            symbols = entry.get("symbols")
            multiplier = entry.get("multiplier")
            if not isinstance(symbols, list):
                io.echo(f"slots: paytable_override entry symbols not a list: {symbols!r}", level="error")
                raise ValueError(f"paytable_override 'symbols' must be a list, got {symbols!r}")
            if not all(isinstance(s, str) and s for s in symbols):
                io.echo(f"slots: paytable_override bad symbols: {symbols!r}", level="error")
                raise ValueError(f"paytable_override 'symbols' entries must be non-empty strings, got {symbols!r}")
            if not isinstance(multiplier, int) or multiplier < 0:
                io.echo(f"slots: paytable_override bad multiplier {multiplier!r}", level="error")
                raise ValueError(f"paytable_override 'multiplier' must be a non-negative int, got {multiplier!r}")
            parsed[tuple(symbols)] = multiplier
        return Paytable(parsed)
    if not isinstance(override, dict):
        io.echo(f"slots: paytable_override rejected: not a dict or list (got {type(override).__name__})", level="error")
        raise ValueError("paytable_override must be a list of {symbols, multiplier} dicts or a dict of {symbol_tuple: multiplier}")
    for key, mult in override.items():
        if not isinstance(key, (list, tuple)):
            io.echo(f"slots: paytable_override rejected: key not list/tuple: {key!r}", level="error")
            raise ValueError(f"paytable key must be a list/tuple, got {key!r}")
        if not all(isinstance(s, str) and s for s in key):
            io.echo(f"slots: paytable_override rejected: bad key entries: {key!r}", level="error")
            raise ValueError(f"paytable key entries must be non-empty strings, got {key!r}")
        if not isinstance(mult, int) or mult < 0:
            io.echo(f"slots: paytable_override rejected: bad multiplier {mult!r} for key {key!r}", level="error")
            raise ValueError(f"paytable multiplier must be a non-negative int, got {mult!r}")
        parsed[tuple(key)] = mult
    return Paytable(parsed)


def _build_dealer_for_table(args: Any, table_moniker: str) -> SlotDealer | None:
    table = dal_table.get_table(args, table_moniker)
    if not table:
        return None
    if table.get("type") != "slots":
        return None
    config = table.get("attrs")
    if not isinstance(config, dict):
        config = {}
    paytable = _build_paytable_from_config(config)
    rng = RNG()
    reels = default_reels(DEFAULT_SYMBOLS, rng)
    return SlotDealer(reels=reels, paytable=paytable, rng=rng)


def get_dealer(args: Any, table_moniker: str) -> SlotDealer | None:
    """Return the cached dealer for a table, building it on first access."""
    dealer = _dealers.get(table_moniker)
    if dealer is not None:
        return dealer
    io.echo(f"slots: dealer cache miss table={table_moniker} building", level="info")
    dealer = _build_dealer_for_table(args, table_moniker)
    if dealer is not None:
        _dealers[table_moniker] = dealer
    return dealer


def invalidate_dealer(table_moniker: str) -> None:
    """Drop a cached dealer (call this on update_table / paytable change)."""
    if _dealers.pop(table_moniker, None) is not None:
        io.echo(f"slots: invalidate_dealer table={table_moniker}", level="info")


def _get_player_credits(args: Any, moniker: str) -> int:
    with casino_conn.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(database.query("SELECT balance FROM bank.__account WHERE moniker = :moniker", moniker=moniker))
        row = cur.fetchone()
        return int(row["balance"]) if row else 0


def handle_spin(
    args: Any,
    table_moniker: str,
    player_moniker: str,
    bet: int,
    *,
    message: Optional[Dict[str, Any]] = None,
    state: Optional[Any] = None,
) -> dict[str, Any]:
    """End-to-end spin: validate, debit, spin, credit, record, stats.

    Returns ``{"success": True, "spin": {...}}`` on success or
    ``{"success": False, "code": "<reason>", "message": "..."}`` on any
    precondition failure. All side effects happen in a single atomic
    transaction.

    Settlement is one call to ``engine.casino_settle_spin``. The acting moniker
    and the token check come from ``state.auth_service_token`` inside the database.
    A call with no token is refused before any SQL runs.

    Callers without a session token (door mode, unit tests that do not supply
    ``state``) are refused before settlement, because only a live token can move money.
    """
    correlation_id = uuid.uuid4().hex
    if not isinstance(bet, int) or isinstance(bet, bool) or bet <= 0:
        io.echo(f"slots: invalid_bet member={player_moniker} table={table_moniker} bet={bet!r} corr={correlation_id}", level="warning")
        return {"success": False, "code": "invalid_bet", "message": "Bet must be a positive integer"}

    table = dal_table.get_table(args, table_moniker)
    if not table:
        io.echo(f"slots: table_not_found member={player_moniker} table={table_moniker} corr={correlation_id}", level="warning")
        return {"success": False, "code": "table_not_found", "message": f"Table {table_moniker} not found"}
    if table.get("type") != "slots":
        io.echo(f"slots: wrong_game_type member={player_moniker} table={table_moniker} corr={correlation_id}", level="warning")
        return {"success": False, "code": "wrong_game_type", "message": f"Table {table_moniker} is not a slots table"}

    min_bet = int(table.get("minimumbet") or 1)
    max_bet = int(table.get("maximumbet") or 1000)
    if bet < min_bet:
        io.echo(f"slots: bet_below_min member={player_moniker} table={table_moniker} bet={bet} min={min_bet} corr={correlation_id}", level="warning")
        return {"success": False, "code": "bet_below_min", "message": f"Minimum bet is {min_bet}"}
    if bet > max_bet:
        io.echo(f"slots: bet_above_max member={player_moniker} table={table_moniker} bet={bet} max={max_bet} corr={correlation_id}", level="warning")
        return {"success": False, "code": "bet_above_max", "message": f"Maximum bet is {max_bet}"}

    dealer = get_dealer(args, table_moniker)
    if dealer is None:
        io.echo(f"slots: dealer_build_failed table={table_moniker} corr={correlation_id}", level="error")
        return {"success": False, "code": "service_error", "message": "Failed to build dealer"}

    io.echo(f"slots: {player_moniker} betting {bet} at {table_moniker} corr={correlation_id}", level="info")

    # Run the RNG outside the transaction (it has no side effects and we
    # want the spin to be deterministic from the result, not from any DB
    # state). The bank + audit + stats are all in one transaction below.
    result = dealer.play(bet=bet)

    net = result.net  # payout - bet; may be negative

    # The token is re-verified inside engine.casino_settle_spin (engine.__bed_token), so a token revoked
    # since the WS open cannot move money. No separate bank-policy check runs here.

    # One casino-owned SECURITY DEFINER op settles the spin: the bank move, the casino.__slot_spin
    # audit row, and the player's stats commit together (sql/casino_settle_spin_functions.sql). The
    # acting moniker comes from the verified token row inside the database, never from this request.
    reels_json = [[s.name for s in col] for col in result.reels]
    wins_json = [w.to_dict() for w in result.wins]
    try:
        token = getattr(state, "auth_service_token", None) or ""
        if not token:
            io.echo(f"slots: spin refused, no bearer token member={player_moniker} corr={correlation_id}", level="error")
            return {"success": False, "code": "forbidden", "message": "No session token for this spin"}
        from bed.store.token_store import token_hash

        with casino_conn.connect(args) as conn, database.cursor(conn) as cur:
            cur.execute(
                "SELECT engine.casino_settle_spin(%s, %s::jsonb)",
                (
                    token_hash(token),
                    database.Jsonb({
                        "table_moniker": table_moniker,
                        "bet": bet,
                        "payout": result.payout,
                        "net": net,
                        "reels": reels_json,
                        "wins": wins_json,
                        "correlation_id": correlation_id,
                    }),
                ),
            )
            row = cur.fetchone()
        settled = row[0] if row else None
        if isinstance(settled, str):
            import json as _json

            settled = _json.loads(settled)
        settled = settled or {"success": False, "code": "service_error", "message": "settlement returned nothing"}
    except Exception as e:
        io.echo(f"slots: spin failed member={player_moniker} table={table_moniker} corr={correlation_id}: {e}", level="error")
        return {"success": False, "code": "service_error", "message": str(e)}

    if not settled.get("success"):
        code = settled.get("code") or "service_error"
        msg = settled.get("message") or "Settlement failed"
        io.echo(f"slots: settle_refused member={player_moniker} code={code} corr={correlation_id}: {msg}", level="warning")
        return {"success": False, "code": code, "message": msg}

    spin_id = int(settled["spin_id"])
    new_balance = int(settled["new_balance"])
    io.echo(f"slots: spin ok spin_id={spin_id} member={player_moniker} table={table_moniker} bet={bet} payout={result.payout} net={net} corr={correlation_id}", level="info")
    return {
        "success": True,
        "spin": {
            "id": spin_id,
            "table_moniker": table_moniker,
            "bet": bet,
            "payout": result.payout,
            "net": net,
            "new_balance": new_balance,
            "reels": reels_json,
            "center_row": [s.name for s in result.center_row],
            "wins": wins_json,
        },
    }


def handle_get_paytable(args: Any, table_moniker: str) -> dict[str, Any]:
    table = dal_table.get_table(args, table_moniker)
    if not table:
        return {"success": False, "code": "table_not_found"}
    if table.get("type") != "slots":
        return {"success": False, "code": "wrong_game_type"}
    dealer = get_dealer(args, table_moniker)
    if dealer is None:
        return {"success": False, "code": "service_error"}
    return {
        "success": True,
        "moniker": table_moniker,
        "payouts": [
            {"symbols": list(k), "multiplier": v}
            for k, v in sorted(dealer.paytable.items(), key=lambda kv: -kv[1])
        ],
    }


def handle_get_history(
    args: Any,
    player_moniker: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return dal_slots.get_spin_history(args, player_moniker, limit=limit)


def handle_get_table_history(
    args: Any,
    table_moniker: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return dal_slots.get_table_history(args, table_moniker, limit=limit)

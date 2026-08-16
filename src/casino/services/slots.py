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
# Bank service + auth token
# -------------------------
# The bank mutation routes through ``bbsengine6.bank.BankService``
# (the same bank service ``bed.api.bank.BankService`` wraps) so the
# spin's ledger write uses the project's bank-account bookkeeping
# (atomic SQL, ``bank.__transaction`` audit row, etc.) and goes
# through the same code path as every other bed bank op. When the
# spin handler is invoked from the bed WS handler with an auth
# context (``message`` carrying validated token ``claims`` and
# ``state`` carrying the bound session), the bank op is gated by
# ``bbsengine6.bank.access`` so the claim-derived moniker /
# ``is_sysop`` authorize the debit/credit. This mirrors the
# defense-in-depth check ``bed.api.bank.BankService._check_access``
# runs on every wire op, so a token revoked since WS open cannot
# drive a slots bank move even if the casino slot-spin policy
# already admitted the request.
#
# The call from the casino WS handler goes through the bed
# WebSocket (``casino.api.handler.SlotServiceHandler``); the
# ``token`` field is already injected on every wire call by
# ``CasinoClient.send`` (token-file flow) and the WS handler
# validates it before ``handle_spin`` runs. ``handle_spin``
# receives the resulting ``state`` + ``message["claims"]`` as
# ``state`` and ``message`` kwargs and feeds them to the bank
# access policy.

from __future__ import annotations

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
    with database.connect(args) as conn, database.cursor(conn) as cur:
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

    When invoked from the bed WS handler (``message`` and ``state``
    are passed through), the bank mutation is gated by
    ``bbsengine6.bank.access`` so the claim-derived moniker /
    ``is_sysop`` authorize the debit/credit. The wire call already
    carries the bearer token (injected by ``CasinoClient.send`` on
    the client side, validated by ``casino.api._auth.check_access``
    on the server side); the bank policy reads ``message["claims"]``
    rather than the in-memory session attributes so the second
    authorization step matches the cryptographically verified
    source.

    Door-mode callers and direct unit-test callers leave ``message``
    and ``state`` at their default ``None`` and the bank gate is
    skipped; the slot-spin policy has already admitted the request.
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

    # Per-call defense-in-depth: re-verify the bearer-token claims
    # against the bank access policy when an auth context is present.
    # Mirrors bed.api.bank.BankService._check_access: the slot spin's
    # bank move is gated by the same claim-derived authorization the
    # bank's own add/remove handlers run, so a token revoked since WS
    # open cannot drive a slots bank move even if the casino slot-spin
    # policy admitted the request. Skipped when message/state are
    # absent (door mode / unit tests where the slot-spin policy is
    # the sole gate).
    if message is not None and state is not None and net != 0:
        from bbsengine6.bank import access as _bank_access

        bank_op = "add" if net > 0 else "remove"
        bank_msg: Dict[str, Any] = {
            "moniker": player_moniker,
            "amount": int(abs(net)),
            "claims": dict(message.get("claims") or {}),
        }
        if not _bank_access(
            args, bank_op, session=state, message=bank_msg
        ):
            io.echo(
                f"slots: bank_access_denied member={player_moniker} "
                f"op={bank_op} amount={bank_msg['amount']} "
                f"corr={correlation_id}",
                level="warning",
            )
            return {
                "success": False,
                "code": "forbidden",
                "message": "Bank operation not permitted for this session",
            }

    # In an atomic transaction: move the net delta into the player
    # account via bbsengine6.bank.BankService (the bank service bed
    # wraps), write the casino spin row, bump stats. If anything
    # fails, the whole spin is rolled back and the player keeps
    # their credits.
    reels_json = [[s.name for s in col] for col in result.reels]
    wins_json = [w.to_dict() for w in result.wins]
    spin_id: int | None = None
    new_balance: int | None = None
    try:
        from bbsengine6.bank import BankService as _BankService

        with database.connect(args) as conn:
            # Route the bank move through bbsengine6.bank.BankService so
            # the SQL is atomic (no read-then-write TOCTOU) and the
            # bank.__transaction audit row is written next to the
            # casino.__slot_spin audit row below. ``conn=conn`` keeps
            # the move inside the spin's atomic transaction.
            bank = _BankService(args)
            if net > 0:
                bank_result = bank.add_funds(
                    player_moniker,
                    int(net),
                    transaction_type="slots_payout",
                    description=(
                        f"Slots spin payout at {table_moniker} "
                        f"(spin corr={correlation_id})"
                    ),
                    member_moniker=player_moniker,
                    conn=conn,
                )
            elif net < 0:
                bank_result = bank.remove_funds(
                    player_moniker,
                    int(-net),
                    transaction_type="slots_bet",
                    description=(
                        f"Slots spin debit at {table_moniker} "
                        f"(spin corr={correlation_id})"
                    ),
                    member_moniker=player_moniker,
                    conn=conn,
                )
            else:
                # net == 0: push, no bank move. Read balance for the
                # response so the client sees the unchanged figure.
                bank_result = {
                    "success": True,
                    "new_balance": bank.get_balance(player_moniker),
                }
            if not bank_result.get("success"):
                msg = bank_result.get("message", "") or ""
                if (
                    "Insufficient funds" in msg
                    or "Account not found" in msg
                    or "balance" in msg.lower()
                ):
                    io.echo(
                        f"slots: insufficient_funds member={player_moniker} "
                        f"bet={bet} corr={correlation_id}: {msg}",
                        level="warning",
                    )
                    return {
                        "success": False,
                        "code": "insufficient_funds",
                        "message": msg or f"Balance below bet {bet}",
                    }
                io.echo(
                    f"slots: bank_op_failed member={player_moniker} "
                    f"op={'add' if net > 0 else 'remove'} "
                    f"corr={correlation_id}: {msg}",
                    level="error",
                )
                return {
                    "success": False,
                    "code": "service_error",
                    "message": msg or "Bank operation failed",
                }
            new_balance = int(bank_result.get("new_balance", 0))

            with database.cursor(conn) as cur:
                # Audit row
                cur.execute(
                    database.query(
                        """INSERT INTO $casino.__slot_spin
                           (table_moniker, player_moniker, bet, payout, reels, wins)
                           VALUES (:table_moniker, :player_moniker, :bet, :payout, :reels, :wins)
                           RETURNING id""",
                        table_moniker=table_moniker,
                        player_moniker=player_moniker,
                        bet=bet,
                        payout=result.payout,
                        reels=database.Jsonb(reels_json),
                        wins=database.Jsonb(wins_json),
                    )
                )
                spin_id_row = cur.fetchone()
                spin_id = int(spin_id_row["id"])
                # Stats
                cur.execute(
                    database.query(
                        """UPDATE $casino.__player
                           SET stats = stats || jsonb_build_object(
                               'slots.spins', COALESCE((stats->>'slots.spins')::int, 0) + 1,
                               'slots.wins', COALESCE((stats->>'slots.wins')::int, 0) + :is_win,
                               'slots.net',  COALESCE((stats->>'slots.net')::int, 0) + :net_delta
                           )
                           WHERE membermoniker = :moniker""",
                        is_win=1 if result.payout > 0 else 0,
                        net_delta=net,
                        moniker=player_moniker,
                    )
                )
                if result.payout > 0:
                    cur.execute(
                        database.query(
                            """UPDATE $casino.__player
                               SET stats = stats || jsonb_build_object(
                                   'slots.biggest_win',
                                   GREATEST(COALESCE((stats->>'slots.biggest_win')::int, 0), :payout)
                               )
                               WHERE membermoniker = :moniker""",
                            payout=result.payout,
                            moniker=player_moniker,
                        )
                    )
                    io.echo(f"slots: biggest_win updated member={player_moniker} payout={result.payout} corr={correlation_id}", level="info")
        # Success
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
    except Exception as e:
        io.echo(f"slots: spin failed member={player_moniker} table={table_moniker} corr={correlation_id}: {e}", level="error")
        return {"success": False, "code": "service_error", "message": str(e)}


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

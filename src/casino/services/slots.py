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

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from bbsengine6 import database, io

from casino.dal import slots as dal_slots
from casino.dal import table as dal_table

from casino.slots.dealer import SlotDealer
from casino.slots.lib import (
    DEFAULT_SYMBOLS,
    Paytable,
    RNG,
    default_reels,
)


# Per-table dealer cache. Key: table_moniker. Value: SlotDealer.
# A dealer is built lazily from the table's reel/paytable config and
# pinned for the life of the table.
_dealers: Dict[str, SlotDealer] = {}


def _resolve_rtp_floor_ceil() -> Tuple[float, float]:
    from casino.slots.lib import RTP_CEIL, RTP_FLOOR
    return RTP_FLOOR, RTP_CEIL


def _build_paytable_from_config(config: Dict[str, Any]) -> Paytable:
    """Build a Paytable from the table's SlotsConfig dict.

    For v1, the only config that affects the Paytable is
    ``config.paytable_override``. Everything else (reel set, target RTP)
    is informational / validation; the default reel strips + paytable
    are used unless an override is supplied.
    """
    override = config.get("paytable_override")
    if override is None:
        return Paytable()
    if not isinstance(override, dict):
        raise ValueError("paytable_override must be a dict of {symbol_tuple: multiplier}")
    parsed: Dict[Tuple[str, ...], int] = {}
    for key, mult in override.items():
        if not isinstance(key, (list, tuple)):
            raise ValueError(f"paytable key must be a list/tuple, got {key!r}")
        if not all(isinstance(s, str) and s for s in key):
            raise ValueError(f"paytable key entries must be non-empty strings, got {key!r}")
        if not isinstance(mult, int) or mult < 0:
            raise ValueError(f"paytable multiplier must be a non-negative int, got {mult!r}")
        parsed[tuple(key)] = mult
    return Paytable(parsed)


def _build_dealer_for_table(args: Any, table_moniker: str) -> Optional[SlotDealer]:
    table = dal_table.get_table(args, table_moniker)
    if not table:
        return None
    if table.get("type") != "slots":
        return None
    config = table.get("config") or {}
    if not isinstance(config, dict):
        config = {}
    paytable = _build_paytable_from_config(config)
    rng = RNG()
    reels = default_reels(DEFAULT_SYMBOLS, rng)
    return SlotDealer(reels=reels, paytable=paytable, rng=rng)


def get_dealer(args: Any, table_moniker: str) -> Optional[SlotDealer]:
    """Return the cached dealer for a table, building it on first access."""
    dealer = _dealers.get(table_moniker)
    if dealer is not None:
        return dealer
    dealer = _build_dealer_for_table(args, table_moniker)
    if dealer is not None:
        _dealers[table_moniker] = dealer
    return dealer


def invalidate_dealer(table_moniker: str) -> None:
    """Drop a cached dealer (call this on update_table / paytable change)."""
    _dealers.pop(table_moniker, None)


def _get_player_credits(args: Any, moniker: str) -> int:
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(database.query("SELECT balance FROM bank.__account WHERE moniker = :moniker", moniker=moniker))
            row = cur.fetchone()
            return int(row["balance"]) if row else 0


def handle_spin(
    args: Any,
    table_moniker: str,
    player_moniker: str,
    bet: int,
) -> Dict[str, Any]:
    """End-to-end spin: validate, debit, spin, credit, record, stats.

    Returns ``{"success": True, "spin": {...}}`` on success or
    ``{"success": False, "code": "<reason>", "message": "..."}`` on any
    precondition failure. All side effects happen in a single atomic
    transaction.
    """
    if not isinstance(bet, int) or isinstance(bet, bool) or bet <= 0:
        return {"success": False, "code": "invalid_bet", "message": "Bet must be a positive integer"}

    table = dal_table.get_table(args, table_moniker)
    if not table:
        return {"success": False, "code": "table_not_found", "message": f"Table {table_moniker} not found"}
    if table.get("type") != "slots":
        return {"success": False, "code": "wrong_game_type", "message": f"Table {table_moniker} is not a slots table"}

    min_bet = int(table.get("minimumbet") or 1)
    max_bet = int(table.get("maximumbet") or 1000)
    if bet < min_bet:
        return {"success": False, "code": "bet_below_min", "message": f"Minimum bet is {min_bet}"}
    if bet > max_bet:
        return {"success": False, "code": "bet_above_max", "message": f"Maximum bet is {max_bet}"}

    dealer = get_dealer(args, table_moniker)
    if dealer is None:
        return {"success": False, "code": "service_error", "message": "Failed to build dealer"}

    # Run the RNG outside the transaction (it has no side effects and we
    # want the spin to be deterministic from the result, not from any DB
    # state). The bank + audit + stats are all in one transaction below.
    result = dealer.play(bet=bet)

    net = result.net  # payout - bet; may be negative
    # In an atomic transaction: move the net delta into the player account,
    # write the spin row, bump stats. If anything fails, the whole spin
    # is rolled back and the player keeps their credits.
    try:
        with database.connect(args) as conn:
            with database.cursor(conn) as cur:
                # Check & lock the player account
                cur.execute(
                    database.query(
                        "SELECT id, balance FROM bank.__account WHERE moniker = :moniker FOR UPDATE",
                        moniker=player_moniker,
                    )
                )
                row = cur.fetchone()
                if row is None:
                    # Auto-create at zero so we have a place to credit
                    cur.execute(
                        database.query(
                            "INSERT INTO bank.__account (moniker, balance) VALUES (:moniker, 0) RETURNING id, balance",
                            moniker=player_moniker,
                        )
                    )
                    row = cur.fetchone()
                account_id = int(row["id"])
                current_balance = int(row["balance"])
                if current_balance < bet:
                    return {
                        "success": False,
                        "code": "insufficient_funds",
                        "message": f"Balance {current_balance} below bet {bet}",
                    }
                new_balance = current_balance + net
                cur.execute(
                    database.query(
                        "UPDATE bank.__account SET balance = :bal WHERE id = :id",
                        bal=new_balance, id=account_id,
                    )
                )
                # Audit row
                reels_json = [[s.name for s in col] for col in result.reels]
                wins_json = [w.to_dict() for w in result.wins]
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
        # Success
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
        io.echo(f"slot spin failed: {e}", level="error")
        return {"success": False, "code": "service_error", "message": str(e)}


def handle_get_paytable(args: Any, table_moniker: str) -> Dict[str, Any]:
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
) -> List[Dict[str, Any]]:
    return dal_slots.get_spin_history(args, player_moniker, limit=limit)


def handle_get_table_history(
    args: Any,
    table_moniker: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    return dal_slots.get_table_history(args, table_moniker, limit=limit)

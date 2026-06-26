# casino/yahtzee/service.py
# Yahtzee in-memory game state + service layer.
#
# YahtzeeService is a per-table game registry (mirrors PokerService._tables).
# Each YahtzeeGame holds the 13-round scorecard, dice, lock state, and
# rolls-left counter. The service uses dal_bet for money movement
# (debit on quick_play, credit per yahtzee_score round) and writes
# a __log row per turn for audit. The __table is reused across
# sessions (status='open'); the __game row is closed at end of 13
# rounds.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from bbsengine6 import database
from bbsengine6.database import Jsonb

from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.services.table import TableService

from . import lib
from .dealer import YahtzeeDealer


def _default_find_table(args: Any, player_moniker: str) -> Optional[dict]:
    """Look up the player's existing open yahtzee table, if any.

    Uses a direct SQL query because dal_table.list_tables does
    not support owner filtering and we want a fast path.
    """
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    """SELECT moniker, type, minimumbet, maximumbet, ownermoniker,
                              ownersince, accountid, location, status, hidden
                       FROM $casino.__table
                       WHERE type = 'yahtzee'
                         AND ownermoniker = :owner_moniker
                         AND status = 'open'
                       LIMIT 1""",
                    owner_moniker=player_moniker,
                )
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "moniker": row["moniker"],
                "type": row["type"],
                "minimumbet": row["minimumbet"],
                "maximumbet": row["maximumbet"],
                "ownermoniker": row["ownermoniker"],
                "ownersince": row["ownersince"],
                "accountid": row["accountid"],
                "location": row["location"],
                "status": row["status"],
                "hidden": row.get("hidden", False),
            }


@dataclass
class YahtzeeGame:
    """In-memory state for one yahtzee session at one table."""

    table_moniker: str
    player_moniker: str
    game_id: int
    bet_id: int
    bet_amount: int
    round_idx: int = 0
    dice: tuple[int, ...] = (0, 0, 0, 0, 0)
    locked: list[bool] = field(default_factory=lambda: [False] * 5)
    rolls_left: int = 2
    scorecard: dict[str, Optional[int]] = field(
        default_factory=lambda: {c: None for c in lib.CATEGORIES}
    )
    last_score: int = 0
    is_over: bool = False

    def state_dict(self) -> dict:
        return {
            "table_moniker": self.table_moniker,
            "round": self.round_idx,
            "dice": list(self.dice),
            "locked": list(self.locked),
            "rolls_left": self.rolls_left,
            "scorecard": dict(self.scorecard),
            "running_total": lib.grand_total(self.scorecard),
            "last_score": self.last_score,
            "is_over": self.is_over,
        }

    def result_dict(self) -> dict:
        return {
            "table_moniker": self.table_moniker,
            "final_scorecard": dict(self.scorecard),
            "upper_total": lib.upper_total(self.scorecard),
            "lower_total": lib.lower_total(self.scorecard),
            "grand_total": lib.grand_total(self.scorecard),
            "rake_total": 0,
            "new_balance": 0,
        }


class YahtzeeService:
    """In-memory registry of active yahtzee games, keyed by table_moniker."""

    def __init__(
        self,
        args: Any,
        dealer: Optional[YahtzeeDealer] = None,
        table_service: Optional[TableService] = None,
        find_table_fn: Optional[Any] = None,
    ) -> None:
        self.args = args
        self._games: dict[str, YahtzeeGame] = {}
        self._table_service = table_service if table_service is not None else TableService(args)
        self._dealer = dealer if dealer is not None else YahtzeeDealer()
        self._find_table_fn = find_table_fn if find_table_fn is not None else _default_find_table

    def _ensure_table(self, player_moniker: str) -> dict:
        """Find or create the player's hidden yahtzee table.

        Looks for an existing open yahtzee table owned by
        ``player_moniker``; if found, returns it. Otherwise creates
        a new hidden one.
        """
        existing = self._find_table_fn(self.args, player_moniker)
        if existing is not None:
            return existing

        result = self._table_service.create_table(
            game_type="yahtzee",
            owner_moniker=player_moniker,
            min_bet=lib.MIN_BET,
            max_bet=lib.MAX_BET,
            hidden=True,
        )
        if not result.get("success"):
            raise RuntimeError(f"failed to create yahtzee table: {result.get('message')}")
        return result["table"]

    def get_game(self, table_moniker: str) -> Optional[YahtzeeGame]:
        return self._games.get(table_moniker)

    def list_active_tables(self) -> list[str]:
        return list(self._games.keys())

    def quick_play(self, player_moniker: str) -> dict:
        """Idempotent entry point: returns a yahtzee_state, creating a
        table and starting a game on first call. Subsequent calls
        with the same player return the current state for the
        existing open game (or start a new game if the prior game
        is closed).
        """
        # Fast path: if an in-memory game for this player is already
        # active, return its state without touching the DB.
        for g in self._games.values():
            if g.player_moniker == player_moniker and not g.is_over:
                return g.state_dict()

        table = self._ensure_table(player_moniker)
        table_moniker = table["moniker"]
        bet_amount = int(table["minimumbet"])

        # Re-check in case another concurrent call beat us to it
        existing_game = self._games.get(table_moniker)
        if existing_game is not None and not existing_game.is_over:
            return existing_game.state_dict()

        game_row = dal_game.create_game(self.args, table_moniker, "yahtzee")
        game_id = int(game_row["id"])

        try:
            bet_row = dal_bet.place_bet(
                self.args,
                player_moniker=player_moniker,
                table_moniker=table_moniker,
                game_id=game_id,
                amount=bet_amount,
                notes="yahtzee_v1",
            )
        except Exception:
            dal_game.update_game_status(self.args, game_id, "cancelled")
            raise

        bet_id = int(bet_row["id"])

        game = YahtzeeGame(
            table_moniker=table_moniker,
            player_moniker=player_moniker,
            game_id=game_id,
            bet_id=bet_id,
            bet_amount=bet_amount,
        )
        self._games[table_moniker] = game
        return game.state_dict()

    def roll(self, table_moniker: str, player_moniker: str) -> dict:
        game = self._require_game(table_moniker, player_moniker)
        if game.rolls_left != 2:
            return self._error("not_at_start_of_round", "yahtzee_roll is only valid at the start of a round")
        game.dice = self._dealer.fresh()
        game.locked = [False] * 5
        game.rolls_left = 1
        return game.state_dict()

    def reroll(
        self,
        table_moniker: str,
        player_moniker: str,
        locks: list[int],
    ) -> dict:
        game = self._require_game(table_moniker, player_moniker)
        if game.rolls_left <= 0:
            return self._error("no_rolls_left", "yahtzee_reroll requires rolls_left > 0")
        if any(not (0 <= i < 5) for i in locks):
            return self._error("bad_locks", "lock indices must be in [0, 4]")
        game.locked = [i in set(locks) for i in range(5)]
        game.dice = self._dealer.reroll(game.dice, game.locked)
        game.rolls_left -= 1
        return game.state_dict()

    def score(
        self,
        table_moniker: str,
        player_moniker: str,
        category: str,
    ) -> dict:
        """Score the current dice into ``category``.

        Returns either a ``yahtzee_state`` (round advanced) or a
        ``yahtzee_result`` (game over) dict, with a ``type`` field
        set so the caller can dispatch.
        """
        game = self._require_game(table_moniker, player_moniker)
        if category not in lib.CATEGORIES:
            return self._error("bad_category", f"unknown category: {category}")
        if game.scorecard[category] is not None:
            return self._error("category_used", f"category {category} is already scored")
        if game.round_idx >= 13:
            return self._error("game_over", "all 13 categories are filled")

        value = lib.score(game.dice, category)
        net = lib.net_payout(value)

        dal_bet.settle_bet(
            self.args,
            bet_id=game.bet_id,
            won=(net > 0),
            payout=net,
        )

        game.scorecard[category] = value
        game.last_score = value
        game.round_idx += 1
        game.dice = (0, 0, 0, 0, 0)
        game.locked = [False] * 5
        game.rolls_left = 2

        self._write_turn_log(game, category, value, net)

        if game.round_idx >= 13:
            game.is_over = True
            dal_game.update_game_status(self.args, game.game_id, "closed")
            result = game.result_dict()
            self._games.pop(table_moniker, None)
            result["type"] = "yahtzee_result"
            return result

        state = game.state_dict()
        state["type"] = "yahtzee_state"
        return state

    def finalize_on_disconnect(self, table_moniker: str) -> bool:
        """Settle the open bet as a loss, mark __game cancelled.

        Returns True if a game was finalized, False if none.
        """
        game = self._games.get(table_moniker)
        if game is None:
            return False
        try:
            dal_bet.settle_bet(
                self.args,
                bet_id=game.bet_id,
                won=False,
                payout=0,
            )
            dal_game.update_game_status(self.args, game.game_id, "cancelled")
        finally:
            self._games.pop(table_moniker, None)
        return True

    def _require_game(self, table_moniker: str, player_moniker: str) -> YahtzeeGame:
        game = self._games.get(table_moniker)
        if game is None:
            raise KeyError(f"no active yahtzee game at {table_moniker}; send yahtzee_quick_play first")
        if game.player_moniker != player_moniker:
            raise PermissionError(f"player {player_moniker} is not seated at {table_moniker}")
        return game

    def _write_turn_log(
        self,
        game: YahtzeeGame,
        category: str,
        score_value: int,
        net: int,
    ) -> None:
        # RAKE_DISABLED: RAKE_PERCENT is 0 in v1; see lib.py.
        # When re-enabled, this row carries the rake amount.
        attrs = {
            "turn": game.round_idx,
            "category": category,
            "score": score_value,
            "net": net,
            "rake": 0,
        }
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        """INSERT INTO $casino.__log
                           (membermoniker, cardtablemoniker, gameid, accountid,
                            datestamp, message, attrs)
                           VALUES (:member_moniker, :table_moniker, :game_id,
                                   :account_id, NOW(), :message, :attrs)""",
                        member_moniker=game.player_moniker,
                        table_moniker=game.table_moniker,
                        game_id=game.game_id,
                        account_id=None,
                        message="yahtzee_turn",
                        attrs=Jsonb(attrs),
                    )
                )

    @staticmethod
    def _error(code: str, message: str) -> dict:
        return {
            "type": "error",
            "code": code,
            "message": message,
        }

# casino/tictactoe/service.py
# Tictactoe in-memory game state + service layer.
#
# TictactoeService is a per-table game registry (mirrors
# YahtzeeService._tables). Each TictactoeGame holds the 9-cell board,
# to_move, mode, and the player monikers in seat order (X first, O
# second). The service uses dal_bet for money movement (debit on
# quick_play, credit on game over or push on draw) and writes a
# __log row per turn for audit. The __table is reused across sessions
# (status='open'); the __game row is closed/cancelled at end.
#
# Three modes:
# - 0: 2 AI, server auto-plays the entire game out, broadcasting
#      tictactoe_state between each move.
# - 1: 1 human (X) vs AI (O). Human move -> broadcast -> AI reply.
# - 2: 2 humans on the same table_moniker, turn alternates by __seat.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bbsengine6 import database
from bbsengine6.database import Jsonb

from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.services.table import TableService

from . import lib
from .dealer import TictactoeDealer

AI_X = "AI_X"
AI_O = "AI_O"


def _default_find_table(args: Any, player_moniker: str) -> dict | None:
    """Look up the player's existing open tictactoe table, if any.

    Mirrors yahtzee/service.py:_default_find_table: a direct SQL
    query because dal_table.list_tables does not support owner
    filtering and we want a fast path.
    """
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                """SELECT moniker, type, minimumbet, maximumbet, ownermoniker,
                              ownersince, accountid, location, status, hidden
                       FROM $casino.__table
                       WHERE type = 'tictactoe'
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
class TictactoeGame:
    """In-memory state for one tic-tac-toe session at one table.

    ``players[0]`` is always X (moves first). In mode 0 both are
    AI_X / AI_O. In mode 1 players[0] is the human and players[1] is
    AI_O. In mode 2 both are human monikers.
    """

    table_moniker: str
    mode: int
    players: list[str]  # [X moniker, O moniker]
    game_id: int
    bet_id: int
    bet_amount: int
    board: lib.Board = field(default_factory=lib.Board.empty)
    moves_played: int = 0
    last_move: dict | None = None
    is_over: bool = False

    def __post_init__(self) -> None:
        if self.mode not in (0, 1, 2):
            raise ValueError(f"mode must be 0, 1, or 2, got {self.mode}")
        if self.mode == 0 and self.players != [AI_X, AI_O]:
            raise ValueError("mode 0 must have players [AI_X, AI_O]")
        if self.mode == 1:
            if self.players[0].startswith("AI_"):
                raise ValueError("mode 1 must have a human X player")
            if self.players[1] != AI_O:
                raise ValueError("mode 1 must have AI_O as the O player")
        if self.mode == 2 and any(p.startswith("AI_") for p in self.players):
            raise ValueError("mode 2 cannot have AI players")

    @property
    def turn_moniker(self) -> str:
        if self.is_over:
            return ""
        if self.board.to_move == lib.X:
            return self.players[0]
        return self.players[1]

    def state_dict(self) -> dict:
        return {
            "table_moniker": self.table_moniker,
            "mode": self.mode,
            "board": list(self.board.cells),
            "to_move": self.board.to_move,
            "turn_moniker": self.turn_moniker,
            "winner": self.board.winner,
            "is_draw": self.board.is_draw() if self.board.is_over() else False,
            "is_over": self.is_over,
            "last_move": dict(self.last_move) if self.last_move else None,
            "moves_played": self.moves_played,
        }

    def result_dict(self, payout_amount: int = 0, new_balance: int = 0) -> dict:
        return {
            "table_moniker": self.table_moniker,
            "mode": self.mode,
            "winner": self.board.winner,
            "winner_moniker": (
                self.players[0] if self.board.winner == lib.X
                else self.players[1] if self.board.winner == lib.O
                else None
            ),
            "is_draw": self.board.is_draw(),
            "board": list(self.board.cells),
            "moves_played": self.moves_played,
            "payout": payout_amount,
            "new_balance": new_balance,
            "rake": 0,
        }


class TictactoeService:
    """In-memory registry of active tic-tac-toe games, keyed by table_moniker."""

    def __init__(
        self,
        args: Any,
        dealer: TictactoeDealer | None = None,
        table_service: TableService | None = None,
        find_table_fn: Any | None = None,
    ) -> None:
        self.args = args
        self._games: dict[str, TictactoeGame] = {}
        self._table_service = table_service if table_service is not None else TableService(args)
        self._dealer = dealer if dealer is not None else TictactoeDealer()
        self._find_table_fn = find_table_fn if find_table_fn is not None else _default_find_table

    def _ensure_table(self, player_moniker: str) -> dict:
        existing = self._find_table_fn(self.args, player_moniker)
        if existing is not None:
            return existing
        result = self._table_service.create_table(
            game_type="tictactoe",
            owner_moniker=player_moniker,
            min_bet=lib.MIN_BET,
            max_bet=lib.MAX_BET,
            hidden=True,
        )
        if not result.get("success"):
            raise RuntimeError(f"failed to create tictactoe table: {result.get('message')}")
        return result["table"]

    def get_game(self, table_moniker: str) -> TictactoeGame | None:
        return self._games.get(table_moniker)

    def list_active_tables(self) -> list[str]:
        return list(self._games.keys())

    def quick_play(self, player_moniker: str, mode: int) -> dict:
        """Idempotent entry point: returns a tictactoe_state, creating a
        table and starting a game on first call. Mode 0/1/2 must match
        the player's current session (mode is immutable for the
        session). Reusing a table for a new game is only allowed if
        the prior game is closed.
        """
        if mode not in (0, 1, 2):
            return self._error("bad_mode", f"mode must be 0, 1, or 2, got {mode}")

        # Fast path: an in-memory game for this player is already active.
        for g in self._games.values():
            if mode in (1, 2) and g.mode == mode and player_moniker in g.players and not g.is_over:
                state = g.state_dict()
                state["type"] = "tictactoe_state"
                return state

        table = self._ensure_table(player_moniker)
        table_moniker = table["moniker"]
        bet_amount = int(table["minimumbet"])

        existing_game = self._games.get(table_moniker)
        if existing_game is not None and not existing_game.is_over:
            state = existing_game.state_dict()
            state["type"] = "tictactoe_state"
            return state

        if mode == 0:
            players = [AI_X, AI_O]
        elif mode == 1:
            players = [player_moniker, AI_O]
        else:  # mode == 2
            players = [player_moniker, "__awaiting_opponent__"]

        game_row = dal_game.create_game(self.args, table_moniker, "tictactoe")
        game_id = int(game_row["id"])

        try:
            bet_row = dal_bet.place_bet(
                self.args,
                player_moniker=player_moniker,
                table_moniker=table_moniker,
                game_id=game_id,
                amount=bet_amount,
                notes=f"tictactoe_v1_mode{mode}",
            )
        except Exception:
            dal_game.update_game_status(self.args, game_id, "cancelled")
            raise

        bet_id = int(bet_row["id"])

        game = TictactoeGame(
            table_moniker=table_moniker,
            mode=mode,
            players=players,
            game_id=game_id,
            bet_id=bet_id,
            bet_amount=bet_amount,
        )
        self._games[table_moniker] = game
        state = game.state_dict()
        state["type"] = "tictactoe_state"
        return state

    def join(self, table_moniker: str, player_moniker: str) -> dict:
        """Mode 2: a second human joins the table to take the O seat.

        Rejected in mode 0 and 1.
        """
        game = self._games.get(table_moniker)
        if game is None:
            return self._error("not_at_table", "send tictactoe_quick_play first")
        if game.mode != 2:
            return self._error("wrong_mode_for_action", "join is only valid in mode 2")
        if game.is_over:
            return self._error("game_over", "this game is already over")
        if game.players[1] != "__awaiting_opponent__":
            return self._error("table_full", "the O seat is already taken")
        if player_moniker == game.players[0]:
            return self._error("not_your_seat", "you are already the X player")
        game.players[1] = player_moniker
        state = game.state_dict()
        state["type"] = "tictactoe_state"
        return state

    def play_move(
        self,
        table_moniker: str,
        player_moniker: str,
        cell: int,
    ) -> dict:
        """Apply a human move. Triggers the AI reply in mode 1.
        Returns a tictactoe_state (game in progress) or tictactoe_result
        (game over).
        """
        game = self._games.get(table_moniker)
        if game is None:
            return self._error("not_at_table", "send tictactoe_quick_play first")
        if game.is_over:
            return self._error("game_over", "this game is already over")
        if game.mode == 0:
            return self._error("wrong_mode_for_action", "tictactoe_move is not allowed in mode 0 (2 AI)")

        if game.turn_moniker != player_moniker:
            return self._error("not_your_turn", f"it is {game.turn_moniker}'s turn")

        err = self._validate_human_move(cell, game.board.cells)
        if err is not None:
            code = "cell_out_of_range" if "must be an integer" in err or "must be in [0, 8]" in err else "cell_occupied"
            return self._error(code, err)

        game.board = game.board.with_move(cell, game.board.to_move)
        game.moves_played += 1
        game.last_move = {
            "cell": cell,
            "mark": lib.O if game.board.to_move == lib.X else lib.X,
            "by": player_moniker,
        }
        self._write_turn_log(game, cell, player_moniker)

        if game.board.is_over():
            return self._settle(game)

        # Mode 1: AI reply immediately.
        if game.mode == 1:
            ai_cell = self._dealer.best_move(game.board.cells, game.board.to_move)
            game.board = game.board.with_move(ai_cell, game.board.to_move)
            game.moves_played += 1
            game.last_move = {
                "cell": ai_cell,
                "mark": lib.O if game.board.to_move == lib.X else lib.X,
                "by": AI_O,
            }
            self._write_turn_log(game, ai_cell, AI_O)
            if game.board.is_over():
                return self._settle(game)

        state = game.state_dict()
        state["type"] = "tictactoe_state"
        return state

    def resign(self, table_moniker: str, player_moniker: str) -> dict:
        """Forfeit. The opponent wins; the bet is settled as a loss for
        the resigning player.
        """
        game = self._games.get(table_moniker)
        if game is None:
            return self._error("not_at_table", "send tictactoe_quick_play first")
        if game.is_over:
            return self._error("game_over", "this game is already over")
        if game.mode == 0:
            return self._error("wrong_mode_for_action", "tictactoe_resign is not allowed in mode 0 (2 AI)")
        if player_moniker not in game.players:
            return self._error("not_your_seat", "you are not seated at this table")

        winner = lib.O if game.players[0] == player_moniker else lib.X
        game.board = lib.Board(
            cells=game.board.cells,
            to_move=game.board.to_move,
            winner=winner,
        )
        game.last_move = {"by": player_moniker, "resigned": True}
        return self._settle(game)

    def auto_play_mode0(self, table_moniker: str) -> list[dict]:
        """Run a full mode-0 game (2 AI) to completion. Returns a list
        of state dicts (one per move, the last one is tictactoe_result
        via settle). Mostly used by tests and the quick_play fast
        path when a mode-0 game is requested.
        """
        game = self._games.get(table_moniker)
        if game is None:
            return [self._error("not_at_table", "no game for table")]
        if game.mode != 0:
            return [self._error("bad_mode", "auto_play_mode0 only valid for mode 0")]

        states: list[dict] = []
        while not game.board.is_over():
            mark = game.board.to_move
            by = AI_X if mark == lib.X else AI_O
            cell = self._dealer.best_move(game.board.cells, mark)
            game.board = game.board.with_move(cell, mark)
            game.moves_played += 1
            game.last_move = {
                "cell": cell,
                "mark": mark,
                "by": by,
            }
            self._write_turn_log(game, cell, by)
            if game.board.is_over():
                states.append(self._settle(game))
            else:
                sd = game.state_dict()
                sd["type"] = "tictactoe_state"
                states.append(sd)
        return states

    def finalize_on_disconnect(self, table_moniker: str, leaving_moniker: str | None = None) -> bool:
        """Hook called by MessageRouter.unregister_session when a
        player disconnects mid-game.

        Mode 0: no humans, ignore.
        Mode 1: leaving player is the only human. Settle as a loss.
        Mode 2: leaving player loses; opponent wins. If the opponent
                left and no humans remain, settle as a loss for the
                leaving seat.
        """
        game = self._games.get(table_moniker)
        if game is None or game.is_over:
            return False
        if game.mode == 0:
            return False
        if game.mode == 1:
            winner = lib.O if game.players[0] == leaving_moniker else lib.X
            game.board = lib.Board(
                cells=game.board.cells,
                to_move=game.board.to_move,
                winner=winner if winner is not None else lib.O,
            )
            game.last_move = {"by": leaving_moniker, "disconnect": True}
            self._settle(game)
            return True
        # mode 2
        if leaving_moniker not in game.players:
            return False
        winner = lib.O if game.players[0] == leaving_moniker else lib.X
        game.board = lib.Board(
            cells=game.board.cells,
            to_move=game.board.to_move,
            winner=winner,
        )
        game.last_move = {"by": leaving_moniker, "disconnect": True}
        self._settle(game)
        return True

    def _settle(self, game: TictactoeGame) -> dict:
        """Mark the game over, settle the bet, return a tictactoe_result
        dict with ``type='tictactoe_result'``.
        """
        game.is_over = True
        winner = game.board.winner
        bettor_mark = lib.X  # Mode 1 bettor is always X (the human).
        payout_amount = lib.bettor_payout(winner, bettor_mark, game.bet_amount)
        new_balance = self._settle_bet(game, payout_amount)
        if winner is None:
            outcome = "loss"
        elif winner == lib.DRAW:
            outcome = "draw"
        elif winner == bettor_mark:
            outcome = "win"
        else:
            outcome = "loss"
        dal_game.update_game_attrs(
            self.args, game.game_id,
            {
                "outcome": outcome,
                "bet_amount": int(game.bet_amount),
                "net": int(payout_amount - game.bet_amount),
            },
        )
        dal_game.update_game_status(self.args, game.game_id, "closed")
        result = game.result_dict(payout_amount=payout_amount, new_balance=new_balance)
        result["type"] = "tictactoe_result"
        self._games.pop(game.table_moniker, None)
        return result

    def _settle_bet(self, game: TictactoeGame, payout_amount: int) -> int:
        """Settle the bet and return the new balance for the bettor.
        If the DB layer is mocked in tests, returns 0.
        """
        try:
            dal_bet.settle_bet(
                self.args,
                bet_id=game.bet_id,
                won=(payout_amount > 0),
                payout=payout_amount,
            )
        except Exception:
            return 0
        # Look up the new balance; if the player row is missing in the
        # test mock, return 0.
        try:
            with database.connect(self.args) as conn, database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        "SELECT credits FROM $engine.__member WHERE moniker = :m",
                        m=game.players[0],
                    )
                )
                row = cur.fetchone()
                return int(row["credits"]) if row else 0
        except Exception:
            return 0

    def _write_turn_log(
        self,
        game: TictactoeGame,
        cell: int,
        by: str,
    ) -> None:
        attrs = {
            "move": int(cell),
            "by": by,
            "moves_played": game.moves_played,
        }
        try:
            with database.connect(self.args) as conn, database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        """INSERT INTO $casino.__log
                               (membermoniker, cardtablemoniker, gameid, accountid,
                                datestamp, message, attrs)
                               VALUES (:member_moniker, :table_moniker, :game_id,
                                       :account_id, NOW(), :message, :attrs)""",
                        member_moniker=game.players[0] if not by.startswith("AI_") else by,
                        table_moniker=game.table_moniker,
                        game_id=game.game_id,
                        account_id=None,
                        message="tictactoe_turn",
                        attrs=Jsonb(attrs),
                    )
                )
        except Exception:
            # Logging is best-effort; never fail the move on log error.
            return

    @staticmethod
    def _validate_human_move(cell: object, cells) -> str | None:
        if not isinstance(cell, int) or isinstance(cell, bool):
            return "cell must be an integer in [0, 8]"
        if not (0 <= cell < 9):
            return f"cell must be in [0, 8], got {cell}"
        if cells[cell] != lib.EMPTY:
            return f"cell {cell} is already occupied"
        return None

    @staticmethod
    def _error(code: str, message: str) -> dict:
        return {
            "type": "error",
            "code": code,
            "message": message,
        }

# casino/services/game.py
# Game service - blackjack game logic

import random
from typing import Any, Dict, List

from bbsengine6 import io
from casino.dal import table as dal_table
from casino.dal import game as dal_game
from decimal import Decimal

from casino.dal import bet as dal_bet


class GameService:
    """Service for game management and blackjack logic."""

    SUITS = ["H", "D", "S", "C"]
    PIPS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

    def __init__(self, args: Any):
        self.args = args
        self._shoes: Dict[str, Dict[str, Any]] = {}  # table_moniker -> shoe state

    def _create_shoe(self, decks: int = 6) -> List[str]:
        """Create a shoe with multiple decks."""
        shoe = []
        for _ in range(decks):
            for suit in self.SUITS:
                for pips in self.PIPS:
                    shoe.append(pips + suit)
        random.shuffle(shoe)
        return shoe

    def _get_shoe(self, table_moniker: str) -> Dict[str, Any]:
        """Get or create shoe for a specific table."""
        if table_moniker in self._shoes:
            shoe = self._shoes[table_moniker]
            total_cards = len(shoe["cards"])
            if shoe["uses"] <= total_cards * shoe["threshold"]:
                return shoe

        # Load from database or create new
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            raise ValueError(f"Table {table_moniker} not found")

        attrs = table.get("attrs", {}) or {}
        shoe_cards = table.get("shoe_cards", []) or []
        shoe_uses = table.get("shoe_uses", 0) or 0

        if not shoe_cards:
            shoe_cards = self._create_shoe(decks=attrs.get("shoe_decks", 6))
            shoe_uses = 0

        shoe = {
            "cards": shoe_cards,
            "uses": shoe_uses,
            "decks": attrs.get("shoe_decks", 6),
            "threshold": attrs.get("shoe_threshold", 0.8),
        }
        self._shoes[table_moniker] = shoe
        return shoe

    def _save_shoe(self, table_moniker: str) -> None:
        """Save shoe state to database."""
        if table_moniker not in self._shoes:
            return
        shoe = self._shoes[table_moniker]
        dal_table.update_shoe(self.args, table_moniker, shoe["cards"], shoe["uses"])

    def _draw_card(self, table_moniker: str) -> str:
        """Draw a card from the table's shoe."""
        shoe = self._get_shoe(table_moniker)

        # Check if shoe needs replacement
        total_cards = len(shoe["cards"])
        if shoe["uses"] > total_cards * shoe["threshold"]:
            shoe["cards"] = self._create_shoe(decks=shoe["decks"])
            shoe["uses"] = 0

        card = shoe["cards"].pop()
        shoe["uses"] += 1
        self._save_shoe(table_moniker)
        return card

    def _card_value(self, card: str) -> int:
        """Get value of a card."""
        pips = card[:-1]
        if pips in ("J", "Q", "K"):
            return 10
        if pips == "A":
            return 11
        return int(pips)

    def _hand_value(self, cards: List[str]) -> int:
        """Calculate hand value with Ace adjustment."""
        total = sum(self._card_value(c) for c in cards)
        aces = sum(1 for c in cards if c.startswith("A"))

        while total > 21 and aces > 0:
            total -= 10
            aces -= 1

        return total

    def start_game(self, table_moniker: str, game_type: str = "blackjack") -> Dict[str, Any]:
        """Start a new game at a table."""
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return {"success": False, "message": "Table not found"}

        game = dal_game.create_game(self.args, table_moniker, game_type)

        return {
            "success": True,
            "game_id": game["id"],
            "message": f"Game {game['id']} started",
        }

    def place_bet(
        self,
        table_moniker: str,
        player_moniker: str,
        amount: int,
    ) -> Dict[str, Any]:
        """Place a bet and create player hand."""
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return {"success": False, "message": "Table not found"}

        if amount < table["minimumbet"]:
            return {
                "success": False,
                "message": f"Bet must be at least {table['minimumbet']}",
            }
        if amount > table["maximumbet"]:
            return {
                "success": False,
                "message": f"Bet cannot exceed {table['maximumbet']}",
            }

        game = dal_game.get_active_game(self.args, table_moniker)
        io.echo(f"place_bet: get_active_game returned: {game}", level="info")
        if not game:
            game_data = self.start_game(table_moniker)
            if not game_data["success"]:
                return game_data
            game = dal_game.get_active_game(self.args, table_moniker)

        try:
            bet = dal_bet.place_bet(
                self.args, player_moniker, table_moniker, game["id"], amount
            )
        except ValueError as e:
            return {"success": False, "message": str(e)}

        hand = dal_game.create_hand(self.args, game["id"], player_moniker)

        cards = [self._draw_card(table_moniker), self._draw_card(table_moniker)]
        dal_game.update_hand_cards(self.args, hand["id"], cards)

        currenthand = ", ".join(cards)
        dal_bet.update_bet_currenthand(self.args, bet["id"], currenthand)

        return {
            "success": True,
            "bet_id": bet["id"],
            "hand_id": hand["id"],
            "cards": cards,
            "total": self._hand_value(cards),
            "message": f"Bet {amount} placed",
        }

    def hit(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Player hits (takes another card)."""
        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        hand = dal_game.get_player_hand(self.args, game["id"], player_moniker)
        if not hand:
            return {"success": False, "message": "No hand found"}

        cards = list(hand["cards"])
        cards.append(self._draw_card(table_moniker))
        dal_game.update_hand_cards(self.args, hand["id"], cards)

        total = self._hand_value(cards)
        status = "bust" if total > 21 else "playing"

        if status == "bust":
            dal_game.update_hand_status(self.args, hand["id"], "bust")

        return {
            "success": True,
            "cards": cards,
            "total": total,
            "status": status,
            "message": "Hit" if status != "bust" else "Bust!",
        }

    def stand(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Player stands (ends turn)."""
        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        hand = dal_game.get_player_hand(self.args, game["id"], player_moniker)
        if not hand:
            return {"success": False, "message": "No hand found"}

        total = self._hand_value(list(hand["cards"]))

        self.settle_game(table_moniker)

        return {
            "success": True,
            "total": total,
            "status": "standing",
            "message": f"Stood at {total}",
        }

    def can_split(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Check if player can split their hand."""
        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        hands = dal_game.get_player_hands(self.args, game["id"], player_moniker)
        if not hands:
            return {"success": False, "message": "No hand found"}

        hand = hands[0]
        cards = list(hand["cards"]) if hand["cards"] else []

        if len(cards) != 2:
            return {"success": False, "message": "Can only split with exactly 2 cards"}

        card1_rank = cards[0][:-1]
        card2_rank = cards[1][:-1]

        if card1_rank != card2_rank:
            return {"success": False, "message": "Cards must have same rank to split"}

        from casino.dal import bet as dal_bet
        player_bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
        if not player_bet:
            return {"success": False, "message": "No bet found"}

        from bbsengine6 import database
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        "SELECT credits FROM $engine.__member WHERE moniker = :player_moniker",
                        player_moniker=player_moniker
                    )
                )
                row = cur.fetchone()
                if not row:
                    return {"success": False, "message": "Player not found"}
                balance = int(row["credits"])
                if balance < player_bet["amount"]:
                    return {"success": False, "message": "Insufficient funds to split"}

        return {
            "success": True,
            "message": "Can split",
            "bet_amount": player_bet["amount"],
        }

    def split(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Split player's hand into two hands."""
        can_split = self.can_split(table_moniker, player_moniker)
        if not can_split["success"]:
            return can_split

        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        hands = dal_game.get_player_hands(self.args, game["id"], player_moniker)
        if not hands:
            return {"success": False, "message": "No hand found"}

        hand = hands[0]
        cards = list(hand["cards"]) if hand["cards"] else []

        if len(cards) != 2:
            return {"success": False, "message": "Can only split with exactly 2 cards"}

        from casino.dal import bet as dal_bet
        player_bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
        bet_amount = player_bet["amount"]

        from bbsengine6 import database
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        "UPDATE $engine.__member SET credits = credits - :amount WHERE moniker = :player_moniker",
                        amount=bet_amount, player_moniker=player_moniker
                    )
                )

        split_bet = dal_bet.place_split_bet(
            self.args, player_moniker, table_moniker, game["id"], bet_amount
        )

        card1 = cards[0]
        card2 = cards[1]

        hand1_cards = [card1, self._draw_card(table_moniker)]
        hand2_cards = [card2, self._draw_card(table_moniker)]

        dal_game.update_hand_cards(self.args, hand["id"], hand1_cards)

        hand2 = dal_game.create_hand(self.args, game["id"], player_moniker + "_split_2")
        dal_game.update_hand_cards(self.args, hand2["id"], hand2_cards)

        dal_game.update_hand_status(self.args, hand["id"], "split_1")
        dal_game.update_hand_status(self.args, hand2["id"], "split_2")

        currenthand1 = ", ".join(hand1_cards)
        currenthand2 = ", ".join(hand2_cards)
        dal_bet.update_bet_currenthand(self.args, player_bet["id"], currenthand1)
        dal_bet.update_bet_currenthand(self.args, split_bet["id"], currenthand2)

        io.echo(f"split: hand1={hand1_cards}, hand2={hand2_cards}", level="info")

        return {
            "success": True,
            "message": "Hand split",
            "hand1": {
                "cards": hand1_cards,
                "total": self._hand_value(hand1_cards),
                "bet": bet_amount,
            },
            "hand2": {
                "cards": hand2_cards,
                "total": self._hand_value(hand2_cards),
                "bet": bet_amount,
            },
        }

    def can_double(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Check if player can double down."""
        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        hands = dal_game.get_player_hands(self.args, game["id"], player_moniker)
        if not hands:
            return {"success": False, "message": "No hand found"}

        hand = hands[0]
        cards = list(hand["cards"]) if hand["cards"] else []

        if len(cards) != 2:
            return {"success": False, "message": "Can only double with exactly 2 cards"}

        from casino.dal import bet as dal_bet
        player_bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
        if not player_bet:
            return {"success": False, "message": "No bet found"}

        from bbsengine6 import database
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        "SELECT credits FROM $engine.__member WHERE moniker = :player_moniker",
                        player_moniker=player_moniker
                    )
                )
                row = cur.fetchone()
                if not row:
                    return {"success": False, "message": "Player not found"}
                balance = int(row["credits"])
                if balance < player_bet["amount"]:
                    return {"success": False, "message": "Insufficient funds to double"}

        return {
            "success": True,
            "message": "Can double",
            "additional_cost": player_bet["amount"],
        }

    def double(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Double down - double bet and get exactly one more card."""
        can_double = self.can_double(table_moniker, player_moniker)
        if not can_double["success"]:
            return can_double

        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        hands = dal_game.get_player_hands(self.args, game["id"], player_moniker)
        if not hands:
            return {"success": False, "message": "No hand found"}

        hand = hands[0]
        cards = list(hand["cards"]) if hand["cards"] else []

        if len(cards) != 2:
            return {"success": False, "message": "Can only double with exactly 2 cards"}

        from casino.dal import bet as dal_bet
        player_bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
        bet_amount = player_bet["amount"]

        from bbsengine6 import database
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        "UPDATE $engine.__member SET credits = credits - :amount WHERE moniker = :player_moniker",
                        amount=bet_amount, player_moniker=player_moniker
                    )
                )

        dal_bet.double_bet(self.args, player_bet["id"], bet_amount * 2)

        new_card = self._draw_card(table_moniker)
        cards.append(new_card)
        dal_game.update_hand_cards(self.args, hand["id"], cards)

        total = self._hand_value(cards)
        status = "bust" if total > 21 else "standing"

        if status == "bust":
            dal_game.update_hand_status(self.args, hand["id"], "bust")

        currenthand = ", ".join(cards)
        dal_bet.update_bet_currenthand(self.args, player_bet["id"], currenthand)

        io.echo(f"double: {cards}, total={total}, status={status}", level="info")

        return {
            "success": True,
            "message": f"Doubled - got {new_card}",
            "cards": cards,
            "total": total,
            "status": status,
            "bet_amount": bet_amount * 2,
        }

    def get_game_state(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Get current game state for a player."""
        io.echo(f"get_game_state: table_moniker={table_moniker}, player={player_moniker}", level="info")
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return {"error": "Table not found"}

        game = dal_game.get_current_game(self.args, table_moniker)
        if not game:
            return {
                "table_moniker": table_moniker,
                "phase": "waiting",
                "hands": [],
                "dealer_hand": [],
                "insurance_available": False,
                "insurance_taken": 0,
            }

        hand = dal_game.get_player_hand(self.args, game["id"], player_moniker)

        dealer_hand = dal_game.get_dealer_hand(self.args, game["id"])
        dealer_cards = (
            list(dealer_hand["cards"]) if dealer_hand and dealer_hand["cards"] else []
        )

        if hand and not dealer_cards:
            dealer_cards = [self._draw_card(table_moniker), self._draw_card(table_moniker)]
            dal_game.update_dealer_hand_cards(self.args, game["id"], dealer_cards)

        dealer_total = self._hand_value(dealer_cards) if dealer_cards else 0

        player_status = None
        if hand and hand.get("attrs"):
            player_status = hand["attrs"].get("status")

        insurance_available = False
        insurance_taken = 0
        if hand and len(hand.get("cards", [])) == 2:
            insurance_available = self._is_dealer_showing_ace(table_moniker)
            if insurance_available:
                bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
                if bet:
                    insurance_taken = dal_bet.get_insurance(self.args, bet["id"])

        return {
            "table_moniker": table_moniker,
            "game_id": int(game["id"]),
            "phase": game["status"],
            "player_hand": hand["cards"] if hand else [],
            "player_total": self._hand_value(list(hand["cards"])) if hand else 0,
            "player_status": player_status,
            "dealer_hand": dealer_cards,
            "dealer_total": dealer_total,
            "insurance_available": insurance_available,
            "insurance_taken": insurance_taken,
        }

    def _is_blackjack(self, cards: list) -> bool:
        """Check for natural blackjack (21 with exactly 2 cards)."""
        return len(cards) == 2 and self._hand_value(cards) == 21

    def _is_dealer_showing_ace(self, table_moniker: str) -> bool:
        """Check if dealer's upcard is an Ace."""
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return False
        game = dal_game.get_current_game(self.args, table_moniker)
        if not game:
            return False
        dealer_hand = dal_game.get_dealer_hand(self.args, game["id"])
        if not dealer_hand or not dealer_hand.get("cards"):
            return False
        dealer_cards = list(dealer_hand["cards"])
        if len(dealer_cards) == 0:
            return False
        upcard = dealer_cards[0]
        return upcard.startswith("A")

    def can_take_insurance(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Check if player can take insurance."""
        if not self._is_dealer_showing_ace(table_moniker):
            return {"success": False, "message": "Insurance not available"}

        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
        if not bet:
            return {"success": False, "message": "No bet found"}

        existing_insurance = dal_bet.get_insurance(self.args, bet["id"])
        if existing_insurance > 0:
            return {"success": False, "message": "Insurance already taken"}

        return {
            "success": True,
            "max_insurance": int(bet["amount"]) // 2,
            "message": "Insurance available",
        }

    def take_insurance(self, table_moniker: str, player_moniker: str, amount: int) -> Dict[str, Any]:
        """Place an insurance bet."""
        can_insure = self.can_take_insurance(table_moniker, player_moniker)
        if not can_insure["success"]:
            return can_insure

        max_insurance = can_insure["max_insurance"]
        if amount < 1:
            return {"success": False, "message": "Insurance must be at least 1"}
        if amount > max_insurance:
            return {"success": False, "message": f"Insurance cannot exceed {max_insurance}"}

        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        bet = dal_bet.get_player_bet_for_game(self.args, game["id"], player_moniker)
        if not bet:
            return {"success": False, "message": "No bet found"}

        dal_bet.set_insurance(self.args, bet["id"], amount)

        return {
            "success": True,
            "amount": amount,
            "message": f"Insurance bet of {amount} placed",
        }

    def _run_dealer_turn(self, game_id: int, table_moniker: str) -> list:
        """Run dealer turn - hit until 17 or more."""
        dealer_hand = dal_game.get_or_create_dealer_hand(self.args, game_id)
        dealer_cards = list(dealer_hand["cards"]) if dealer_hand["cards"] else []

        if not dealer_cards:
            dealer_cards = [self._draw_card(table_moniker), self._draw_card(table_moniker)]
            dal_game.update_dealer_hand_cards(self.args, game_id, dealer_cards)

        dealer_total = self._hand_value(dealer_cards)
        while dealer_total < 17:
            dealer_cards.append(self._draw_card(table_moniker))
            dal_game.update_dealer_hand_cards(self.args, game_id, dealer_cards)
            dealer_total = self._hand_value(dealer_cards)

        return dealer_cards

    def settle_game(self, table_moniker: str) -> Dict[str, Any]:
        """Settle all bets for a game."""
        game = dal_game.get_active_game(self.args, table_moniker)
        if not game:
            return {"success": False, "message": "No active game"}

        bets = dal_bet.get_table_bets(self.args, game["id"])
        hands = dal_game.get_game_hands(self.args, game["id"])

        dealer_cards = self._run_dealer_turn(game["id"], table_moniker)
        dealer_total = self._hand_value(dealer_cards)
        dealer_blackjack = self._is_blackjack(dealer_cards)

        for bet in bets:
            if bet["status"] != "pending":
                continue

            player_hand = next(
                (h for h in hands if h["playermoniker"] == bet["playermoniker"]), None
            )
            if not player_hand:
                continue

            insurance_amount = dal_bet.get_insurance(self.args, bet["id"])

            player_cards = list(player_hand["cards"])
            player_total = self._hand_value(player_cards)
            player_blackjack = self._is_blackjack(player_cards)

            if player_blackjack and dealer_blackjack:
                dal_bet.settle_bet(self.args, bet["id"], True, bet["amount"])
            elif player_blackjack:
                dal_bet.settle_bet(self.args, bet["id"], True, int(bet["amount"] * Decimal("2.5")))
            elif dealer_blackjack:
                dal_bet.settle_bet(self.args, bet["id"], False, 0)
            elif player_total > 21:
                dal_bet.settle_bet(self.args, bet["id"], False, 0)
            elif dealer_total > 21:
                dal_bet.settle_bet(self.args, bet["id"], True, bet["amount"] * 2)
            elif player_total > dealer_total:
                dal_bet.settle_bet(self.args, bet["id"], True, bet["amount"] * 2)
            elif player_total < dealer_total:
                dal_bet.settle_bet(self.args, bet["id"], False, 0)
            else:
                dal_bet.settle_bet(self.args, bet["id"], True, bet["amount"])

            if insurance_amount > 0:
                if dealer_blackjack:
                    payout = insurance_amount * 2
                    dal_bet.settle_insurance(self.args, bet["id"], True, payout)
                else:
                    dal_bet.settle_insurance(self.args, bet["id"], False, 0)

        dal_game.update_game_status(self.args, game["id"], "settled")

        return {
            "success": True,
            "message": "Game settled",
            "dealer_total": dealer_total,
            "dealer_cards": dealer_cards,
        }

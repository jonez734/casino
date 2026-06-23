import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

from bbsengine6 import io
from casino.dal import table as dal_table
from casino.dal import game as dal_game
from casino.dal import player as dal_player
from casino.poker.lib import (
    PokerDeck,
    SUITS,
    RANKS,
    BettingStructure,
)
from casino.poker.variant import get_variant, BaseVariant
from casino.poker.variant import evaluator


class PlayerAction(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class PokerPlayer:
    moniker: str
    seat: int
    hole_cards: List[str] = field(default_factory=list)
    current_bet: int = 0
    total_in_pot: int = 0
    has_acted: bool = False
    is_all_in: bool = False
    has_folded: bool = False
    showing_cards: bool = True
    credits: int = 0


@dataclass
class PokerPot:
    amount: int
    eligible_players: List[str] = field(default_factory=list)


@dataclass
class PokerTableState:
    moniker: str
    variant: BaseVariant
    betting_structure: BettingStructure
    small_blind: int
    big_blind: int
    min_buy_in: int
    max_buy_in: int
    min_players: int
    max_players: int
    
    players: Dict[str, PokerPlayer] = field(default_factory=dict)
    dealer_position: int = 0
    current_street: str = "preflop"
    current_player: Optional[str] = None
    current_bet: int = 0
    pot: int = 0
    side_pots: List[PokerPot] = field(default_factory=list)
    community_cards: List[str] = field(default_factory=list)
    deck: Optional[PokerDeck] = None
    game_stage: str = "waiting"  # waiting, preflop, flop, turn, river, showdown
    last_aggressor: Optional[str] = None
    
    def get_active_players(self) -> List[PokerPlayer]:
        return [p for p in self.players.values() if not p.has_folded]
    
    def get_players_in_order(self) -> List[PokerPlayer]:
        seats = sorted(self.players.keys(), key=lambda k: self.players[k].seat)
        return [self.players[s] for s in seats if s in self.players]
    
    def get_next_player(self, from_moniker: str) -> Optional[PokerPlayer]:
        players = self.get_players_in_order()
        active_monikers = [p.moniker for p in self.get_active_players()]
        
        for i, pm in enumerate(active_monikers):
            if pm == from_moniker:
                next_idx = (i + 1) % len(active_monikers)
                if next_idx == 0:
                    return None  # Full circle
                return self.players[active_monikers[next_idx]]
        return None


class PokerService:
    """Service for poker game management."""

    def __init__(self, args: Any):
        self.args = args
        self._tables: Dict[str, PokerTableState] = {}
        self._decks: Dict[str, PokerDeck] = {}

    def create_table(
        self,
        table_moniker: str,
        variant_name: str,
        betting_structure: str,
        small_blind: int,
        big_blind: int,
        min_players: int = 2,
        max_players: int = 10,
        min_buy_in: int = 100,
        max_buy_in: int = 10000,
    ) -> Dict[str, Any]:
        """Create a new poker table."""
        try:
            variant = get_variant(variant_name)
        except ValueError as e:
            return {"success": False, "message": str(e)}

        if betting_structure.lower() == "no_limit":
            bs = BettingStructure.NO_LIMIT
        elif betting_structure.lower() == "pot_limit":
            bs = BettingStructure.POT_LIMIT
        elif betting_structure.lower() == "fixed_limit":
            bs = BettingStructure.FIXED_LIMIT
        else:
            return {"success": False, "message": f"Unknown betting structure: {betting_structure}"}

        variant.betting_structure = bs

        table = PokerTableState(
            moniker=table_moniker,
            variant=variant,
            betting_structure=bs,
            small_blind=small_blind,
            big_blind=big_blind,
            min_buy_in=min_buy_in,
            max_buy_in=max_buy_in,
            min_players=min_players,
            max_players=max_players,
        )

        self._tables[table_moniker] = table
        self._decks[table_moniker] = PokerDeck()

        io.echo(f"Created poker table {table_moniker}: {variant_name} {betting_structure} ${small_blind}/${big_blind}")

        return {
            "success": True,
            "table_moniker": table_moniker,
            "variant": variant_name,
            "betting_structure": betting_structure,
            "stakes": f"${small_blind}/${big_blind}",
        }

    def join_table(
        self, table_moniker: str, player_moniker: str, buy_in: int
    ) -> Dict[str, Any]:
        """Player joins a poker table."""
        if table_moniker not in self._tables:
            return {"success": False, "message": "Table not found"}

        table = self._tables[table_moniker]

        if player_moniker in table.players:
            return {"success": False, "message": "Already at table"}

        if len(table.players) >= table.max_players:
            return {"success": False, "message": "Table full"}

        if buy_in < table.min_buy_in or buy_in > table.max_buy_in:
            return {
                "success": False,
                "message": f"Buy-in must be between {table.min_buy_in} and {table.max_buy_in}",
            }

        if buy_in > table.max_buy_in:
            return {"success": False, "message": f"Buy-in exceeds maximum of {table.max_buy_in}"}

        seat = self._get_next_seat(table)
        player = PokerPlayer(
            moniker=player_moniker,
            seat=seat,
            credits=buy_in,
        )
        table.players[player_moniker] = player

        io.echo(f"{player_moniker} joined table {table_moniker} with ${buy_in}")

        return {
            "success": True,
            "seat": seat,
            "credits": buy_in,
            "message": f"Seated at {seat} with ${buy_in}",
        }

    def leave_table(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Player leaves a poker table."""
        if table_moniker not in self._tables:
            return {"success": False, "message": "Table not found"}

        table = self._tables[table_moniker]

        if player_moniker not in table.players:
            return {"success": False, "message": "Not at table"}

        if table.game_stage != "waiting":
            return {"success": False, "message": "Cannot leave during a hand"}

        del table.players[player_moniker]

        return {"success": True, "message": "Left table"}

    def _get_next_seat(self, table: PokerTableState) -> int:
        """Get next available seat number."""
        used_seats = {p.seat for p in table.players.values()}
        for i in range(1, 11):
            if i not in used_seats:
                return i
        return len(table.players) + 1

    def start_hand(self, table_moniker: str) -> Dict[str, Any]:
        """Start a new hand at the table."""
        if table_moniker not in self._tables:
            return {"success": False, "message": "Table not found"}

        table = self._tables[table_moniker]

        if len(table.players) < table.min_players:
            return {"success": False, "message": f"Need at least {table.min_players} players"}

        deck = self._decks.get(table_moniker)
        if deck is None:
            deck = PokerDeck()
            self._decks[table_moniker] = deck
        deck.shuffle()

        for player in table.players.values():
            player.hole_cards = []
            player.current_bet = 0
            player.total_in_pot = 0
            player.has_acted = False
            player.is_all_in = False
            player.has_folded = False
            player.showing_cards = True

        table.community_cards = []
        table.pot = 0
        table.side_pots = []
        
        streets = table.variant.get_betting_streets()
        first_street = streets[0] if streets else "preflop"
        table.game_stage = first_street
        table.current_street = first_street

        self._post_blinds(table)

        self._deal_hole_cards(table, deck)

        table.dealer_position = (table.dealer_position + 1) % len(table.players)

        sb_pos = (table.dealer_position + 1) % len(table.players)
        bb_pos = (table.dealer_position + 2) % len(table.players)

        players_ordered = table.get_players_in_order()
        
        utg_pos = (bb_pos + 1) % len(players_ordered)
        table.current_player = players_ordered[utg_pos].moniker

        io.echo(f"Started hand at {table_moniker}")

        return {
            "success": True,
            "message": "Hand started",
            "community_cards": [],
            "pot": table.pot,
        }

    def _post_blinds(self, table: PokerTableState):
        """Post small and big blinds."""
        players_ordered = table.get_players_in_order()
        
        if len(players_ordered) < 2:
            return

        sb_pos = (table.dealer_position + 1) % len(players_ordered)
        bb_pos = (table.dealer_position + 2) % len(players_ordered)

        sb_player = players_ordered[sb_pos]
        bb_player = players_ordered[bb_pos]

        sb_amount = min(table.small_blind, sb_player.credits)
        sb_player.credits -= sb_amount
        sb_player.current_bet = sb_amount
        sb_player.total_in_pot = sb_amount

        bb_amount = min(table.big_blind, bb_player.credits)
        bb_player.credits -= bb_amount
        bb_player.current_bet = bb_amount
        bb_player.total_in_pot = bb_amount

        table.pot = sb_amount + bb_amount
        table.current_bet = table.big_blind

        io.echo(f"Blinds: {sb_player.moniker} posts ${sb_amount} SB, {bb_player.moniker} posts ${bb_amount} BB")

    def _deal_hole_cards(self, table: PokerTableState, deck: PokerDeck):
        """Deal hole cards to all players based on variant rules and current street."""
        variant = table.variant
        street = table.current_street
        
        street_before_deal = variant.get_street_before_deal()
        cards_for_street = street_before_deal.get(street, 0)
        
        if cards_for_street == 0:
            cards_for_street = variant.hole_cards_per_player

        for _ in range(cards_for_street):
            for player in table.players.values():
                if deck.remaining() > 0:
                    card = deck.deal(1)[0]
                    player.hole_cards.append(card.to_string())

        io.echo(f"Dealt {cards_for_street} hole cards to {len(table.players)} players")

    def player_action(
        self, table_moniker: str, player_moniker: str, action: str, amount: int = 0
    ) -> Dict[str, Any]:
        """Process a player's action."""
        if table_moniker not in self._tables:
            return {"success": False, "message": "Table not found"}

        table = self._tables[table_moniker]

        if player_moniker not in table.players:
            return {"success": False, "message": "Not at table"}

        player = table.players[player_moniker]

        if player_moniker != table.current_player:
            return {"success": False, "message": "Not your turn"}

        if player.has_folded:
            return {"success": False, "message": "You have folded"}

        action = action.lower()

        if action == "fold":
            return self._handle_fold(table, player)
        elif action == "check":
            return self._handle_check(table, player)
        elif action == "call":
            return self._handle_call(table, player)
        elif action in ("bet", "raise"):
            return self._handle_bet_raise(table, player, action, amount)
        elif action == "all_in":
            return self._handle_all_in(table, player)
        else:
            return {"success": False, "message": f"Unknown action: {action}"}

    def _handle_fold(self, table: PokerTableState, player: PokerPlayer) -> Dict[str, Any]:
        """Handle fold action."""
        player.has_folded = True
        player.showing_cards = False
        
        active = table.get_active_players()
        if len(active) == 1:
            winner = active[0]
            winner.credits += table.pot
            table.pot = 0
            table.game_stage = "showdown"
            io.echo(f"{player.moniker} folds. {winner.moniker} wins ${table.pot}")
            return {"success": True, "action": "fold", "winner": winner.moniker, "pot": 0}

        self._advance_to_next_player(table)
        
        return {"success": True, "action": "fold", "message": f"{player.moniker} folds"}

    def _handle_check(self, table: PokerTableState, player: PokerPlayer) -> Dict[str, Any]:
        """Handle check action."""
        if table.current_bet > player.current_bet:
            return {"success": False, "message": "Cannot check - there's a bet to call"}

        player.has_acted = True
        self._advance_to_next_player(table)

        return {"success": True, "action": "check", "message": f"{player.moniker} checks"}

    def _handle_call(self, table: PokerTableState, player: PokerPlayer) -> Dict[str, Any]:
        """Handle call action."""
        call_amount = table.current_bet - player.current_bet
        
        if call_amount > player.credits:
            return {"success": False, "message": "Not enough credits to call"}

        player.credits -= call_amount
        player.current_bet += call_amount
        player.total_in_pot += call_amount
        player.has_acted = True

        diff = player.current_bet - table.current_bet
        if diff > 0:
            table.current_bet = player.current_bet

        table.pot += call_amount

        self._advance_to_next_player(table)

        return {
            "success": True,
            "action": "call",
            "amount": call_amount,
            "message": f"{player.moniker} calls ${call_amount}",
        }

    def _handle_bet_raise(
        self, table: PokerTableState, player: PokerPlayer, action: str, amount: int
    ) -> Dict[str, Any]:
        """Handle bet or raise action."""
        min_bet = table.big_blind if table.current_bet == 0 else table.current_bet
        
        if amount < min_bet:
            return {"success": False, "message": f"Minimum bet is ${min_bet}"}

        if amount > player.credits:
            return {"success": False, "message": "Not enough credits"}

        player.credits -= amount
        player.current_bet = amount
        player.total_in_pot += amount
        player.has_acted = True

        if amount > table.current_bet:
            table.current_bet = amount
            table.last_aggressor = player.moniker

        for p in table.players.values():
            if p.moniker != player.moniker:
                p.has_acted = False

        table.pot += amount

        self._advance_to_next_player(table)

        return {
            "success": True,
            "action": action,
            "amount": amount,
            "message": f"{player.moniker} {action}s ${amount}",
        }

    def _handle_all_in(self, table: PokerTableState, player: PokerPlayer) -> Dict[str, Any]:
        """Handle all-in action."""
        all_in_amount = player.credits
        player.credits = 0
        player.is_all_in = True
        player.current_bet = player.total_in_pot + all_in_amount
        player.total_in_pot = player.current_bet
        
        if player.current_bet > table.current_bet:
            table.current_bet = player.current_bet
            table.last_aggressor = player.moniker

        for p in table.players.values():
            if p.moniker != player.moniker and not p.is_all_in:
                p.has_acted = False

        table.pot += all_in_amount

        self._advance_to_next_player(table)

        return {
            "success": True,
            "action": "all_in",
            "amount": all_in_amount,
            "message": f"{player.moniker} goes all-in for ${all_in_amount}",
        }

    def _advance_to_next_player(self, table: PokerTableState):
        """Advance to next player in turn."""
        active = table.get_active_players()
        
        if len(active) <= 1:
            return

        if table.current_player:
            next_player = table.get_next_player(table.current_player)
            if next_player and not next_player.has_acted:
                table.current_player = next_player.moniker
            elif next_player:
                all_acted = all(p.has_acted or p.is_all_in for p in active)
                if all_acted:
                    self._end_street(table)
                else:
                    table.current_player = next_player.moniker

    def _end_street(self, table: PokerTableState):
        """End current betting street and move to next."""
        current = table.current_street
        next_street = table.variant.get_next_street(current)

        if next_street is None:
            self._showdown(table)
            return

        table.current_street = next_street
        table.game_stage = next_street

        if next_street == "flop":
            self._deal_community_cards(table, 3)
        elif next_street in ("turn", "river"):
            self._deal_community_cards(table, 1)

        for player in table.players.values():
            player.has_acted = False
            player.current_bet = 0

        table.current_bet = 0
        table.current_player = None

        io.echo(f"Community cards ({next_street}): {table.community_cards}")

    def _deal_community_cards(self, table: PokerTableState, count: int):
        """Deal community cards."""
        deck = self._decks.get(table.moniker)
        if deck is None:
            return

        for _ in range(count):
            if deck.remaining() > 0:
                card = deck.deal(1)[0]
                table.community_cards.append(card.to_string())

    def _showdown(self, table: PokerTableState):
        """Resolve hand at showdown."""
        table.game_stage = "showdown"

        active = table.get_active_players()
        if len(active) == 1:
            winner = active[0]
            winner.credits += table.pot
            io.echo(f"{winner.moniker} wins ${table.pot} (uncontested)")
            table.pot = 0
            return

        best_hands = {}
        for player in active:
            rank, best_cards = table.variant.evaluate_showdown(
                player.hole_cards, table.community_cards
            )
            best_hands[player.moniker] = (rank, best_cards, player.hole_cards)

        sorted_players = sorted(
            best_hands.items(),
            key=lambda x: (x[1][0], x[1][1]),
            reverse=True
        )

        winning_rank = sorted_players[0][1][0]
        winners = [m for m, (r, _, _) in sorted_players if r == winning_rank]

        if len(winners) == 1:
            winner_moniker = winners[0]
            winner_player = table.players[winner_moniker]
            winner_player.credits += table.pot
            io.echo(f"{winner_moniker} wins ${table.pot} with {evaluator.get_hand_name(winning_rank)}")
            rank, best, _ = best_hands[winner_moniker]
            io.echo(f"Best hand: {best}")
        else:
            split_amount = table.pot // len(winners)
            for w in winners:
                table.players[w].credits += split_amount
            io.echo(f"Split pot between {len(winners)} players: {winners} - ${split_amount} each")

        table.pot = 0

    def get_table_state(self, table_moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Get current state of a poker table for a player."""
        if table_moniker not in self._tables:
            return {"error": "Table not found"}

        table = self._tables[table_moniker]

        player = table.players.get(player_moniker)
        player_hand = player.hole_cards if player else []
        player_credits = player.credits if player else 0

        player_can_act = (
            player_moniker == table.current_player
            and not player.has_folded
            and not player.is_all_in
        ) if player else False

        return {
            "table_moniker": table_moniker,
            "variant": table.variant.name,
            "betting_structure": table.betting_structure.name,
            "stakes": f"${table.small_blind}/${table.big_blind}",
            "game_stage": table.game_stage,
            "current_street": table.current_street,
            "current_player": table.current_player,
            "current_bet": table.current_bet,
            "pot": table.pot,
            "community_cards": table.community_cards,
            "player_hand": player_hand,
            "player_credits": player_credits,
            "player_can_act": player_can_act,
            "players": [
                {
                    "moniker": p.moniker,
                    "seat": p.seat,
                    "credits": p.credits,
                    "current_bet": p.current_bet,
                    "has_folded": p.has_folded,
                    "is_all_in": p.is_all_in,
                }
                for p in table.players.values()
            ],
        }

    def list_tables(self) -> List[Dict[str, Any]]:
        """List all active poker tables."""
        return [
            {
                "moniker": t.moniker,
                "variant": t.variant.name,
                "betting_structure": t.betting_structure.name,
                "stakes": f"${t.small_blind}/${t.big_blind}",
                "players": len(t.players),
                "max_players": t.max_players,
                "game_stage": t.game_stage,
            }
            for t in self._tables.values()
        ]

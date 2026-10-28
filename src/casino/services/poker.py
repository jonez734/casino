from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from bbsengine6 import io

from casino.poker import (
    BaseVariant,
    BettingStructure,
    get_variant,
)
from casino.dal import poker_state
from casino.dal import shoe as shoe_store
from casino.dal import table as dal_table
from casino.shoe import Shoe
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
    hole_cards: list[str] = field(default_factory=list)
    current_bet: int = 0
    total_in_pot: int = 0
    has_acted: bool = False
    is_all_in: bool = False
    has_folded: bool = False
    showing_cards: bool = True
    credits: int = 0
    is_bot: bool = False


@dataclass
class PokerPot:
    amount: int
    eligible_players: list[str] = field(default_factory=list)


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

    players: dict[str, PokerPlayer] = field(default_factory=dict)
    dealer_position: int = 0
    current_street: str = "preflop"
    current_player: Optional[str] = None
    turn_seconds: int = 0
    clock_penalty: str = "skip"
    turn_deadline: Optional[Any] = None
    current_bet: int = 0
    pot: int = 0
    side_pots: list[PokerPot] = field(default_factory=list)
    community_cards: list[str] = field(default_factory=list)
    deck: Optional[Shoe] = None
    game_stage: str = "waiting"  # waiting, preflop, flop, turn, river, showdown
    last_aggressor: Optional[str] = None
    # Outcome of the most recent hand (set at showdown or fold), so a player's reply can show it.
    last_result: Optional[dict[str, Any]] = None

    def get_active_players(self) -> list[PokerPlayer]:
        return [p for p in self.players.values() if not p.has_folded]

    def get_players_in_order(self) -> list[PokerPlayer]:
        seats = sorted(self.players.keys(), key=lambda k: self.players[k].seat)
        return [self.players[s] for s in seats if s in self.players]

    def get_next_player(self, from_moniker: str) -> Optional[PokerPlayer]:
        """The next active seat after ``from_moniker`` in seat order, wrapping around.

        ``from_moniker`` may have just folded; it is found in the full seat order, not only among
        the active seats, so the turn can always move on from a seat that has left the hand.
        """
        ordered = self.get_players_in_order()
        if from_moniker not in self.players:
            return None
        start = next(i for i, p in enumerate(ordered) if p.moniker == from_moniker)
        for step in range(1, len(ordered) + 1):
            candidate = ordered[(start + step) % len(ordered)]
            if candidate.moniker == from_moniker:
                return None
            if not candidate.has_folded:
                return candidate
        return None


class PokerService:
    """Service for poker game management."""

    # Every card game draws from a shoe (casino.shoe), even with one deck. Reshuffle once this
    # fraction of the shoe has been drawn, the same rule blackjack uses.
    SHOE_DECKS = 1
    SHOE_THRESHOLD = 0.8

    def __init__(self, args: Any):
        self.args = args
        self._tables: dict[str, PokerTableState] = {}
        self._decks: dict[str, Shoe] = {}

    def _table(self, table_moniker: str) -> Optional[PokerTableState]:
        """The table in memory, or restored from casino.__poker_state after a restart."""
        table = self._tables.get(table_moniker)
        if table is not None:
            return table
        doc = poker_state.load(self.args, table_moniker)
        if doc is None:
            return None
        table, shoe = poker_state.state_to_table(doc)
        self._tables[table_moniker] = table
        if shoe is not None:
            self._decks[table_moniker] = shoe
        return table

    def _draw(self, table: PokerTableState, shoe: Shoe, *, burn: bool = False) -> str:
        """Draw one card from the table's shoe, audit it when --audit is set.

        A burn is recorded as kind 'burn'; a dealt card as 'draw'. A reshuffle is recorded
        before the card that triggered it.
        """
        reshuffles = shoe.reshuffles
        card = shoe.draw()
        if shoe.reshuffles != reshuffles:
            shoe_store.record_event(self.args, table.moniker, kind="reshuffle", shoe=shoe)
        kind = "burn" if burn else "draw"
        shoe_store.record_event(self.args, table.moniker, kind=kind, shoe=shoe, card=card)
        return card

    def _save(self, table_moniker: str) -> None:
        """Persist the whole table (and its shoe) after a change, so a restart resumes the game."""
        table = self._tables.get(table_moniker)
        if table is None:
            return
        poker_state.save(self.args, table_moniker, table, self._decks.get(table_moniker))

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
    ) -> dict[str, Any]:
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

        dal_table.ensure_poker_table_row(
            self.args, table_moniker, min_bet=small_blind, max_bet=big_blind * 100, pool=None,
        )
        self._tables[table_moniker] = table
        self._decks[table_moniker] = Shoe(decks=self.SHOE_DECKS, threshold=self.SHOE_THRESHOLD)

        io.echo(f"Created poker table {table_moniker}: {variant_name} {betting_structure} ${small_blind}/${big_blind}")

        self._save(table.moniker)
        return {
            "success": True,
            "table_moniker": table_moniker,
            "variant": variant_name,
            "betting_structure": betting_structure,
            "stakes": f"${small_blind}/${big_blind}",
        }

    def join_table(
        self, table_moniker: str, player_moniker: str, buy_in: int
    ) -> dict[str, Any]:
        """Player joins a poker table."""
        table = self._table(table_moniker)
        if table is None:
            return {"success": False, "message": "Table not found"}

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

        self._save(table.moniker)
        return {
            "success": True,
            "seat": seat,
            "credits": buy_in,
            "message": f"Seated at {seat} with ${buy_in}",
        }

    def leave_table(self, table_moniker: str, player_moniker: str) -> dict[str, Any]:
        """Player leaves a poker table."""
        table = self._table(table_moniker)
        if table is None:
            return {"success": False, "message": "Table not found"}

        if player_moniker not in table.players:
            return {"success": False, "message": "Not at table"}

        if table.game_stage != "waiting":
            return {"success": False, "message": "Cannot leave during a hand"}

        del table.players[player_moniker]

        self._save(table.moniker)
        return {"success": True, "message": "Left table"}

    def _get_next_seat(self, table: PokerTableState) -> int:
        """Get next available seat number."""
        used_seats = {p.seat for p in table.players.values()}
        for i in range(1, 11):
            if i not in used_seats:
                return i
        return len(table.players) + 1

    def start_hand(self, table_moniker: str) -> dict[str, Any]:
        """Start a new hand at the table."""
        table = self._table(table_moniker)
        if table is None:
            return {"success": False, "message": "Table not found"}

        if len(table.players) < table.min_players:
            return {"success": False, "message": f"Need at least {table.min_players} players"}

        shoe = self._decks.get(table_moniker)
        if shoe is None:
            shoe = Shoe(decks=self.SHOE_DECKS, threshold=self.SHOE_THRESHOLD)
            self._decks[table_moniker] = shoe

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

        self._deal_hole_cards(table, shoe)

        table.dealer_position = (table.dealer_position + 1) % len(table.players)

        (table.dealer_position + 1) % len(table.players)
        bb_pos = (table.dealer_position + 2) % len(table.players)

        players_ordered = table.get_players_in_order()

        utg_pos = (bb_pos + 1) % len(players_ordered)
        self._set_turn(table, players_ordered[utg_pos].moniker)

        io.echo(f"Started hand at {table_moniker}")

        self._save(table.moniker)
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

    def _deal_hole_cards(self, table: PokerTableState, deck: Shoe):
        """Deal hole cards to all players based on variant rules and current street."""
        variant = table.variant
        street = table.current_street

        street_before_deal = variant.get_street_before_deal()
        cards_for_street = street_before_deal.get(street, 0)

        if cards_for_street == 0:
            cards_for_street = variant.hole_cards_per_player

        for _ in range(cards_for_street):
            for player in table.players.values():
                player.hole_cards.append(self._draw(table, deck))

        io.echo(f"Dealt {cards_for_street} hole cards to {len(table.players)} players")

    def _deal_street_cards(self, table: PokerTableState, deck: Shoe):
        """Deal cards for the current street (community cards or additional hole cards)."""
        variant = table.variant
        street = table.current_street

        community_per_street = variant.get_community_cards_per_street()
        hole_per_street = variant.get_street_before_deal()

        comm_cards = community_per_street.get(street, 0)
        hole_cards = hole_per_street.get(street, 0)

        if comm_cards > 0:
            for _ in range(comm_cards):
                self._draw(table, deck, burn=True)
                table.community_cards.append(self._draw(table, deck))
            io.echo(f"Dealt {comm_cards} community cards: {table.community_cards}")

        if hole_cards > 0:
            for _ in range(hole_cards):
                for player in table.players.values():
                    if not player.has_folded:
                        player.hole_cards.append(self._draw(table, deck))
            io.echo(f"Dealt {hole_cards} hole cards to active players")

    def player_action(
        self, table_moniker: str, player_moniker: str, action: str, amount: int = 0
    ) -> dict[str, Any]:
        """Process a player's action."""
        table = self._table(table_moniker)
        if table is None:
            return {"success": False, "message": "Table not found"}

        if player_moniker not in table.players:
            return {"success": False, "message": "Not at table"}

        player = table.players[player_moniker]

        # The clock runs before anything else: if the seat's turn has expired, its penalty is
        # applied and the late action is refused, never applied.
        expiry = self._enforce_turn_clock(table)
        if expiry is not None:
            return {"success": False, "message": "Your turn clock expired", "expired": expiry}

        if player_moniker != table.current_player:
            return {"success": False, "message": "Not your turn"}

        if player.has_folded:
            return {"success": False, "message": "You have folded"}

        action = action.lower()

        handlers = {
            "fold": lambda: self._handle_fold(table, player),
            "check": lambda: self._handle_check(table, player),
            "call": lambda: self._handle_call(table, player),
            "all_in": lambda: self._handle_all_in(table, player),
        }
        if action in ("bet", "raise"):
            result = self._handle_bet_raise(table, player, action, amount)
        elif action in handlers:
            result = handlers[action]()
        else:
            return {"success": False, "message": f"Unknown action: {action}"}

        # Persist the result of the action only once it has happened. A refused action changes
        # nothing, so there is nothing to save.
        if result.get("success"):
            self._save(table.moniker)
        return result

    def _handle_fold(self, table: PokerTableState, player: PokerPlayer) -> dict[str, Any]:
        """Handle fold action."""
        player.has_folded = True
        player.showing_cards = False

        active = table.get_active_players()
        if len(active) == 1:
            winner = active[0]
            won = table.pot
            winner.credits += won
            table.pot = 0
            table.game_stage = "showdown"
            io.echo(f"{player.moniker} folds. {winner.moniker} wins ${won}")
            table.last_result = {
                "kind": "uncontested",
                "winners": [winner.moniker],
                "pot": won,
                "shares": {winner.moniker: won},
                "hand_name": None,
                "hands": {},
                "community_cards": list(table.community_cards),
            }
            return {"success": True, "action": "fold", "winner": winner.moniker, "pot": won}

        self._advance_to_next_player(table)

        return {"success": True, "action": "fold", "message": f"{player.moniker} folds"}

    def _handle_check(self, table: PokerTableState, player: PokerPlayer) -> dict[str, Any]:
        """Handle check action."""
        if table.current_bet > player.current_bet:
            return {"success": False, "message": "Cannot check - there's a bet to call"}

        player.has_acted = True
        self._advance_to_next_player(table)

        return {"success": True, "action": "check", "message": f"{player.moniker} checks"}

    def _handle_call(self, table: PokerTableState, player: PokerPlayer) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        """Handle bet or raise action."""
        # ``amount`` is the total this player has in on the street ("raise to"). The chips they
        # already put in count toward it, so only the difference is charged.
        if table.current_bet == 0:
            min_total = table.big_blind
        else:
            min_total = table.current_bet + table.big_blind

        if amount < min_total:
            return {"success": False, "message": f"Minimum {action} is ${min_total} total"}

        delta = amount - player.current_bet
        if delta > player.credits:
            return {"success": False, "message": "Not enough credits"}

        player.credits -= delta
        player.current_bet = amount
        player.total_in_pot += delta
        player.has_acted = True

        if amount > table.current_bet:
            table.current_bet = amount
            table.last_aggressor = player.moniker

        for p in table.players.values():
            if p.moniker != player.moniker:
                p.has_acted = False

        table.pot += delta

        self._advance_to_next_player(table)

        return {
            "success": True,
            "action": action,
            "amount": amount,
            "message": f"{player.moniker} {action}s ${amount}",
        }

    def _handle_all_in(self, table: PokerTableState, player: PokerPlayer) -> dict[str, Any]:
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

    def _set_turn(self, table: PokerTableState, moniker: Optional[str]) -> None:
        """Give the turn to a seat and start its clock (human seats only)."""
        from casino.services import poker_clock as _pc
        table.current_player = moniker
        seat = table.players.get(moniker) if moniker else None
        if seat is not None and _pc.clocked(seat):
            from casino.services import clock as _clock
            table.turn_deadline = _clock.reload_deadline(table.turn_seconds)
        else:
            table.turn_deadline = None

    def _enforce_turn_clock(self, table: PokerTableState) -> Optional[dict[str, Any]]:
        """If the current seat's clock has run out, apply its penalty and pass the turn.

        Called before every action, so an expired seat's late action is never applied. Returns
        the expiry summary when a penalty was applied, else None.
        """
        from casino.services import poker_clock as _pc
        from casino.services import clock as _clock
        if not table.current_player or not _clock.is_expired(table.turn_deadline):
            return None
        seat = table.players.get(table.current_player)
        if seat is None:
            return None
        facing_bet = table.current_bet > seat.current_bet
        expiry = _pc.apply_expiry(table, seat, facing_bet=facing_bet)
        active = table.get_active_players()
        if expiry["action"] == "fold" and len(active) == 1:
            # The same resolution as a fold: the last seat takes the pot and the hand ends.
            winner = active[0]
            winner.credits += table.pot
            table.pot = 0
            table.game_stage = "showdown"
            expiry["winner"] = winner.moniker
            return expiry
        self._advance_to_next_player(table)
        return expiry

    def _advance_to_next_player(self, table: PokerTableState):
        """Advance to next player in turn."""
        active = table.get_active_players()

        if len(active) <= 1:
            return

        if table.current_player:
            next_player = table.get_next_player(table.current_player)
            if next_player and not next_player.has_acted:
                self._set_turn(table, next_player.moniker)
            elif next_player:
                all_acted = all(p.has_acted or p.is_all_in for p in active)
                if all_acted:
                    self._end_street(table)
                else:
                    self._set_turn(table, next_player.moniker)

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

        io.echo(f"Community cards ({next_street}): {table.community_cards}")

        # Postflop action opens with the first live seat after the button. If nobody can act
        # (everyone left is all-in), run the remaining streets out to showdown.
        ordered = table.get_players_in_order()
        button_idx = table.dealer_position % len(ordered)
        first = None
        for step in range(1, len(ordered) + 1):
            candidate = ordered[(button_idx + step) % len(ordered)]
            if not candidate.has_folded and not candidate.is_all_in:
                first = candidate
                break

        if first is None:
            self._set_turn(table, None)
            self._end_street(table)
            return

        self._set_turn(table, first.moniker)

    def _deal_community_cards(self, table: PokerTableState, count: int):
        """Deal community cards."""
        deck = self._decks.get(table.moniker)
        if deck is None:
            return

        for _ in range(count):
            self._draw(table, deck, burn=True)
            table.community_cards.append(self._draw(table, deck))

    def _showdown(self, table: PokerTableState):
        """Resolve hand at showdown."""
        table.game_stage = "showdown"

        active = table.get_active_players()
        pot = table.pot
        if len(active) == 1:
            winner = active[0]
            winner.credits += pot
            io.echo(f"{winner.moniker} wins ${pot} (uncontested)")
            table.last_result = {
                "kind": "uncontested",
                "winners": [winner.moniker],
                "pot": pot,
                "hand_name": None,
                "hands": {},
                "community_cards": list(table.community_cards),
            }
            table.pot = 0
            return

        best_hands = {}
        for player in active:
            rank, best_cards = table.variant.evaluate_showdown(
                player.hole_cards, table.community_cards
            )
            best_hands[player.moniker] = (rank, best_cards, player.hole_cards)

        # Rank each contender by the full evaluator tiebreak (pair value, kickers, ...), not by the
        # hand category alone. Two pairs are only equal when their pair values and kickers match.
        scored = {
            m: evaluator.get_hand_rank(best) for m, (_, best, _) in best_hands.items()
        }
        top = None
        for m, score in scored.items():
            if top is None or evaluator.compare_hands(score, scored[top]) > 0:
                top = m
        winners = [m for m, score in scored.items() if evaluator.compare_hands(score, scored[top]) == 0]
        winning_rank = scored[top][0]
        hand_name = evaluator.get_hand_name(winning_rank)
        # Hole cards and best five for every contender, so the table can show the showdown.
        hands = {
            m: {"hole_cards": list(hole), "best": list(best), "rank": evaluator.get_hand_name(r)}
            for m, (r, best, hole) in best_hands.items()
        }

        if len(winners) == 1:
            winner_moniker = winners[0]
            winner_player = table.players[winner_moniker]
            winner_player.credits += pot
            io.echo(f"{winner_moniker} wins ${pot} with {hand_name}")
            rank, best, _ = best_hands[winner_moniker]
            io.echo(f"Best hand: {best}")
            shares = {winner_moniker: pot}
        else:
            # Split evenly; the odd chip(s) go to the first winner in seat order.
            ordered = [p.moniker for p in table.get_players_in_order() if p.moniker in winners]
            split_amount = pot // len(winners)
            remainder = pot - split_amount * len(winners)
            shares = {w: split_amount for w in winners}
            shares[ordered[0]] += remainder
            for w in winners:
                table.players[w].credits += shares[w]
            io.echo(f"Split pot between {len(winners)} players: {winners} - ${split_amount} each")

        table.last_result = {
            "kind": "showdown",
            "winners": list(winners),
            "pot": pot,
            "shares": shares,
            "hand_name": hand_name,
            "hands": hands,
            "community_cards": list(table.community_cards),
        }
        table.pot = 0

    def last_result(self, table_moniker: str) -> Optional[dict[str, Any]]:
        """Outcome of the most recent hand at ``table_moniker``, or None before any hand ends."""
        table = self._table(table_moniker)
        return table.last_result if table is not None else None

    def seated_monikers(self, table_moniker: str) -> list[str]:
        """Everyone seated at a poker table (humans and bots), from the table's in-memory seats."""
        table = self._table(table_moniker)
        if table is None:
            return []
        return sorted(table.players.keys())

    def get_table_state(self, table_moniker: str, player_moniker: str) -> dict[str, Any]:
        """Get current state of a poker table for a player."""
        table = self._table(table_moniker)
        if table is None:
            return {"error": "Table not found"}

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

    def list_tables(self) -> list[dict[str, Any]]:
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

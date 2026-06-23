from typing import Optional
from casino.poker.lib import HandRank, SUITS, RANKS, RANK_ORDER, PokerCard


def get_card_rank_value(card_str: str) -> int:
    """Get numeric rank value from card string (e.g., 'AH' -> 12 for Ace)."""
    rank = card_str[:-1] if len(card_str) > 1 and card_str[:2] == "10" else card_str[0]
    return RANK_ORDER.get(rank, 0)


def get_card_suit(card_str: str) -> str:
    """Get suit from card string."""
    return card_str[-1] if card_str else ""


def is_flush(cards: list[str]) -> bool:
    """Check if all cards are same suit."""
    if len(cards) < 5:
        return False
    suits = [get_card_suit(c) for c in cards]
    return len(set(suits)) == 1


def is_straight(cards: list[str]) -> bool:
    """Check if cards form a straight."""
    if len(cards) < 5:
        return False
    
    ranks = sorted(set(get_card_rank_value(c) for c in cards), reverse=True)
    
    if len(ranks) < 5:
        return False
    
    # Check for straight
    for i in range(len(ranks) - 4):
        straight_ranks = ranks[i:i+5]
        if straight_ranks[0] - straight_ranks[4] == 4:
            return True
    
    # Check for wheel (A-2-3-4-5)
    wheel_ranks = {12, 0, 1, 2, 3}  # Ace low
    if wheel_ranks.issubset(set(ranks)):
        return True
    
    return False


def count_ranks(cards: list[str]) -> dict[int, int]:
    """Count occurrences of each rank."""
    counts: dict[int, int] = {}
    for card in cards:
        rank_val = get_card_rank_value(card)
        counts[rank_val] = counts.get(rank_val, 0) + 1
    return counts


def get_hand_rank(cards: list[str]) -> tuple[HandRank, list[int]]:
    """Evaluate hand rank and return tie-breaker values.
    
    Returns (HandRank, [tie_breaker_values...])
    """
    if len(cards) < 5:
        return (HandRank.HIGH_CARD, [])
    
    # Check flush first (needed for straight flush)
    flush_cards = []
    suit_groups: dict[str, list[str]] = {}
    for card in cards:
        suit = get_card_suit(card)
        if suit not in suit_groups:
            suit_groups[suit] = []
        suit_groups[suit].append(card)
    
    for suit, suit_cards in suit_groups.items():
        if len(suit_cards) >= 5:
            flush_cards = sorted(suit_cards, key=get_card_rank_value, reverse=True)[:5]
            break
    
    # Check straight from flush cards
    if flush_cards and is_straight(flush_cards):
        ranks = [get_card_rank_value(c) for c in flush_cards]
        if ranks[0] == 12 and ranks[1] == 3:  # A-5 wheel straight
            ranks = [3, 2, 1, 0, -1]  # 5-high straight
        if ranks[0] == 12:  # Ace-high straight
            return (HandRank.ROYAL_FLUSH, [12])
        return (HandRank.STRAIGHT_FLUSH, [ranks[0]])
    
    # Check straight from all cards
    all_ranks = sorted(set(get_card_rank_value(c) for c in cards), reverse=True)
    
    # Regular straight check
    for i in range(len(all_ranks) - 4):
        if all_ranks[i] - all_ranks[i+4] == 4:
            return (HandRank.STRAIGHT, [all_ranks[i]])
    
    # Wheel check
    if {12, 0, 1, 2, 3}.issubset(set(all_ranks)):
        return (HandRank.STRAIGHT, [3])
    
    # Count ranks for other hands
    rank_counts = count_ranks(cards)
    sorted_counts = sorted(rank_counts.items(), key=lambda x: (-x[1], -x[0]))
    
    # Four of a kind
    if sorted_counts[0][1] == 4:
        kickers = [r for r, c in sorted_counts if c != 4]
        kickers.sort(reverse=True)
        return (HandRank.FOUR_OF_A_KIND, [sorted_counts[0][0], kickers[0] if kickers else 0])
    
    # Full house
    if sorted_counts[0][1] == 3 and sorted_counts[1][1] >= 2:
        return (HandRank.FULL_HOUSE, [sorted_counts[0][0], sorted_counts[1][0]])
    
    # Flush
    if flush_cards:
        kickers = [get_card_rank_value(c) for c in flush_cards]
        return (HandRank.FLUSH, kickers)
    
    # Straight (already checked above)
    if is_straight(cards):
        for i in range(len(all_ranks) - 4):
            if all_ranks[i] - all_ranks[i+4] == 4:
                return (HandRank.STRAIGHT, [all_ranks[i]])
        if {12, 0, 1, 2, 3}.issubset(set(all_ranks)):
            return (HandRank.STRAIGHT, [3])
    
    # Three of a kind
    if sorted_counts[0][1] == 3:
        kickers = [r for r, c in sorted_counts if c != 3]
        kickers.sort(reverse=True)
        return (HandRank.THREE_OF_A_KIND, [sorted_counts[0][0], kickers[0], kickers[1]])
    
    # Two pair
    if sorted_counts[0][1] == 2 and sorted_counts[1][1] == 2:
        kickers = [r for r, c in sorted_counts if c != 2]
        kickers.sort(reverse=True)
        pair_ranks = sorted([sorted_counts[0][0], sorted_counts[1][0]], reverse=True)
        return (HandRank.TWO_PAIR, [pair_ranks[0], pair_ranks[1], kickers[0] if kickers else 0])
    
    # One pair
    if sorted_counts[0][1] == 2:
        kickers = [r for r, c in sorted_counts if c != 2]
        kickers.sort(reverse=True)
        return (HandRank.PAIR, [sorted_counts[0][0], kickers[0], kickers[1], kickers[2]])
    
    # High card
    high_cards = sorted(set(get_card_rank_value(c) for c in cards), reverse=True)
    return (HandRank.HIGH_CARD, high_cards[:5])


def evaluate_best_hand(
    hole_cards: list[str], community_cards: list[str], required_hole: int = 0
) -> tuple[HandRank, list[str], list[str]]:
    """Evaluate the best 5-card hand from hole cards + community cards.
    
    Args:
        hole_cards: Player's hole cards
        community_cards: Community cards on table
        required_hole: Minimum hole cards to use (0 = any, 2 = Omaha-style)
    
    Returns:
        (hand_rank, best_5_cards, used_hole_cards)
    """
    all_cards = hole_cards + community_cards
    if len(all_cards) < 5:
        return (HandRank.HIGH_CARD, [], hole_cards)
    
    if required_hole == 0:
        # Use any 5 cards
        best_rank = HandRank.HIGH_CARD
        best_tie = []
        best_hand = []
        
        # Try all 5-card combinations
        from itertools import combinations
        for combo in combinations(all_cards, 5):
            rank, tie = get_hand_rank(list(combo))
            if (rank > best_rank) or (rank == best_rank and tie > best_tie):
                best_rank = rank
                best_tie = tie
                best_hand = list(combo)
        
        used_hole = [c for c in best_hand if c in hole_cards]
        return (best_rank, best_hand, used_hole)
    else:
        # Must use exactly required_hole hole cards
        from itertools import combinations
        
        best_rank = HandRank.HIGH_CARD
        best_tie = []
        best_hand = []
        used_hole = []
        
        hole_combos = combinations(hole_cards, required_hole)
        comm_combos = combinations(community_cards, 5 - required_hole)
        
        for hole_combo in hole_combos:
            for comm_combo in comm_combos:
                combo = list(hole_combo) + list(comm_combo)
                rank, tie = get_hand_rank(combo)
                if (rank > best_rank) or (rank == best_rank and tie > best_tie):
                    best_rank = rank
                    best_tie = tie
                    best_hand = combo
                    used_hole = list(hole_combo)
        
        return (best_rank, best_hand, used_hole)


def compare_hands(
    hand1: tuple[HandRank, list[int]], 
    hand2: tuple[HandRank, list[int]]
) -> int:
    """Compare two hands. Returns 1 if hand1 wins, -1 if hand2 wins, 0 for tie."""
    rank1, tie1 = hand1
    rank2, tie2 = hand2
    
    if rank1 > rank2:
        return 1
    if rank1 < rank2:
        return -1
    
    # Same rank - compare tie breakers
    for t1, t2 in zip(tie1, tie2):
        if t1 > t2:
            return 1
        if t1 < t2:
            return -1
    
    return 0


def get_hand_name(rank: HandRank) -> str:
    """Get human-readable name for hand rank."""
    names = {
        HandRank.HIGH_CARD: "High Card",
        HandRank.PAIR: "Pair",
        HandRank.TWO_PAIR: "Two Pair",
        HandRank.THREE_OF_A_KIND: "Three of a Kind",
        HandRank.STRAIGHT: "Straight",
        HandRank.FLUSH: "Flush",
        HandRank.FULL_HOUSE: "Full House",
        HandRank.FOUR_OF_A_KIND: "Four of a Kind",
        HandRank.STRAIGHT_FLUSH: "Straight Flush",
        HandRank.ROYAL_FLUSH: "Royal Flush",
    }
    return names.get(rank, "Unknown")

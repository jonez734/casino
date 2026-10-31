from bbsengine6 import io, util

from .. import host
from .. import lib as libcasino
from .settle import classify_hand, describe


def init(args, **kw):
    return True


def access(args, op, **kw):
    return True


def buildargs(args, **kw):
    return None


def run_dealer_turn(hand: libcasino.Hand, shoe) -> dict:
    """Run dealer's turn - hit on 16 or less, stand on 17+."""
    io.echo("{f6}{var:titlecolor}Dealer's turn:{var:normalcolor}")

    hand.show(hide=False)

    total = hand.calcvalue()
    while total < 17:
        io.echo(f"{{var:labelcolor}}Dealer has {{var:valuecolor}}{total}{{var:labelcolor}}, hitting...")
        hand.hit(shoe)
        hand.show(hide=False)
        total = hand.calcvalue()

    if total > 21:
        io.echo("{level.error}Dealer busts!{var:normalcolor}")
        return {"bust": True, "total": total}

    io.echo(f"{{var:labelcolor}}Dealer stands on {{var:valuecolor}}{total}")
    return {"bust": False, "total": total}


def _hand_cards(hand: libcasino.Hand) -> list[str]:
    """The hand as card strings (e.g. ``AH``, ``10S``), the format settle.py classifies.

    Built from pips and suit, which every card type carries, rather than ``str(card)``, which
    is not the shorthand for every card class.
    """
    return [f"{c.pips}{c.suit}" for c in hand.cards]


# Door-mode stat per settled outcome. Same mapping as BED's GameService._count_stats, so a hand
# counts the same way in both modes.
_STAT_FOR_OUTCOME = {
    "win": ("win",),
    "blackjack": ("win",),
    "loss": ("loss",),
    "bust": ("loss", "bust"),
    "push": ("push",),
}

# Door-mode echo color per outcome.
_LEVEL_FOR_OUTCOME = {
    "win": "level.ok",
    "blackjack": "level.ok",
    "loss": "level.error",
    "bust": "level.error",
    "push": "level.warning",
}


def determine_winner(
    player_hand: libcasino.Hand, dealer_hand: libcasino.Hand, player, *, quit_hand: bool = False
) -> None:
    """Settle one door-mode hand with the same rules as BED, print the ending, and update stats.

    ``quit_hand`` settles a hand the player walked away from as a loss.
    """
    player_cards = _hand_cards(player_hand)
    dealer_cards = _hand_cards(dealer_hand)
    bet = int(getattr(player, "currentbet", 0) or 0)

    if quit_hand:
        outcome, reason = "loss", "player_quit"
    else:
        outcome, reason = classify_hand(player_cards, dealer_cards)

    net = _net_for(outcome, bet)
    text = describe(
        reason,
        player_cards=player_cards,
        dealer_cards=dealer_cards,
        bet=bet,
        net=net,
    )
    io.echo(f"{{{_LEVEL_FOR_OUTCOME[outcome]}}}Result: {outcome} -- {text}{{var:normalcolor}}")

    for stat in _STAT_FOR_OUTCOME.get(outcome, ()):
        player.incstat(stat)


def _net_for(outcome: str, bet: int) -> int:
    """Net change for a bet, matching BED's payouts (blackjack pays 3:2)."""
    if outcome == "blackjack":
        return int(bet * 1.5)
    if outcome in ("win",):
        return bet
    if outcome == "push":
        return 0
    return -bet


def _render_action_menu(**kwargs) -> None:
    """Print the blackjack action menu.

    Used as the ``help=`` callback passed to
    :func:`bbsengine6.io.inputchoice.inputchoice` so that pressing
    ``KEY_F1`` (or ``KEY_HELP``) redraws the action list. Accepts
    ``**kwargs`` because ``inputchoice`` forwards all caller-supplied
    kwargs to the help callable.
    """
    io.echo("{var:optioncolor}[H]{var:labelcolor} -- hit (draw one card)")
    io.echo("{var:optioncolor}[S]{var:labelcolor} -- stand (keep current hand)")
    io.echo("{var:optioncolor}[D]{var:labelcolor} -- double down (first two cards only)")
    io.echo("{var:optioncolor}[Q]{var:labelcolor} -- quit the hand")


def main(args, **kw):
    player = kw.get("player")
    dealer = kw.get("dealer")
    shoe = kw.get("shoe")

    if player is None or dealer is None or shoe is None:
        io.echo(
            "{level.error}Error: missing required arguments (player, dealer, shoe){var:normalcolor}"
        )
        return False

    util.heading("play blackjack")

    player.hand = libcasino.Hand("player 1")
    dealer.hand = libcasino.Hand("dealer")

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    io.echo("{f6}{var:titlecolor}Dealer's hand:{var:normalcolor}")
    dealer.hand.show(hide=True)

    io.echo("{f6}{var:titlecolor}Your hand:{var:normalcolor}")
    player.hand.show()
    io.echo(f"{{var:labelcolor}}Total: {{var:valuecolor}}{player.hand.calcvalue()}")

    player_total = player.hand.calcvalue()
    if player_total == 21 and len(player.hand.cards) == 2:
        io.echo("{level.ok}Blackjack!{var:normalcolor}")

    _render_action_menu()

    quit_hand = False
    while True:
        # host.choose: LO when hosted, io.inputchoice standalone. Both are uppercased below.
        choice = host.choose(
            "{var:promptcolor}Action: {var:optioncolor}[HSDQ]{var:promptcolor}: {var:inputcolor}",
            "hsdq",
            "h",
            help=_render_action_menu,
        )
        if choice is None:
            choice = ""
        else:
            choice = choice.upper()

        if choice == "H":
            io.echo("{var:promptcolor}You hit:{var:normalcolor}")
            player.hand.hit(shoe)
            player.hand.show()
            player_total = player.hand.calcvalue()
            io.echo(f"{{var:labelcolor}}Total: {{var:valuecolor}}{player_total}")

            if player_total > 21:
                io.echo("{level.error}Bust!{var:normalcolor}")
                break
            if player_total == 21:
                io.echo("{var:labelcolor}21 - standing")
                break
        elif choice == "D":
            if len(player.hand.cards) != 2:
                io.echo("{level.warning}Can only double down on the first two cards.{var:normalcolor}")
                continue
            io.echo("{var:promptcolor}You double down:{var:normalcolor}")
            player.hand.hit(shoe)
            player.hand.show()
            player_total = player.hand.calcvalue()
            io.echo(f"{{var:labelcolor}}Total: {{var:valuecolor}}{player_total}")
            if player_total > 21:
                io.echo("{level.error}Bust!{var:normalcolor}")
            break
        elif choice == "Q":
            io.echo("{var:promptcolor}You quit the hand.{var:normalcolor}")
            quit_hand = True
            break
        else:
            break

    if quit_hand:
        determine_winner(player.hand, dealer.hand, player, quit_hand=True)
    elif player_total > 21:
        # Bust: settled without a dealer turn, through the same settlement as a played-out hand.
        determine_winner(player.hand, dealer.hand, player)
    else:
        run_dealer_turn(dealer.hand, shoe)
        determine_winner(player.hand, dealer.hand, player)

    return True

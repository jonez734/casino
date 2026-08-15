from bbsengine6 import io, util

from .. import lib as libcasino


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


def determine_winner(
    player_hand: libcasino.Hand, dealer_hand: libcasino.Hand, player
) -> None:
    """Determine winner and update player stats."""
    player_total = player_hand.calcvalue()
    dealer_total = dealer_hand.calcvalue()

    if player_total > 21:
        io.echo("{level.error}You bust! Dealer wins.{var:normalcolor}")
        player.incstat("loss")
    elif dealer_total > 21:
        io.echo("{level.ok}Dealer busts! You win!{var:normalcolor}")
        player.incstat("win")
    elif player_total > dealer_total:
        io.echo(f"{{level.ok}}You win!{{var:normalcolor}} {{var:valuecolor}}{player_total}{{var:labelcolor}} vs {{var:valuecolor}}{dealer_total}")
        player.incstat("win")
    elif player_total < dealer_total:
        io.echo(f"{{level.error}}Dealer wins!{{var:normalcolor}} {dealer_total} vs {player_total}")
        player.incstat("loss")
    else:
        io.echo(f"{{level.warning}}Push!{{var:labelcolor}} Both have {player_total}")
        player.incstat("draw")


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
        choice = io.inputchoice(
            "{var:promptcolor}Action: {var:optioncolor}[HSDQ]{var:promptcolor}: {var:inputcolor}",
            "hsdq",
            "h",
            help=_render_action_menu,
        )

        if choice == "h":
            io.echo("{var:promptcolor}You hit:{var:normalcolor}")
            player.hand.hit(shoe)
            player.hand.show()
            player_total = player.hand.calcvalue()
            io.echo(f"{{var:labelcolor}}Total: {{var:valuecolor}}{player_total}")

            if player_total > 21:
                io.echo("{level.error}Bust!{var:normalcolor}")
                player.incstat("bust")
                break
            if player_total == 21:
                io.echo("{var:labelcolor}21 - standing")
                break
        elif choice == "d":
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
                player.incstat("bust")
            break
        elif choice == "q":
            io.echo("{var:promptcolor}You quit the hand.{var:normalcolor}")
            player.incstat("loss")
            quit_hand = True
            break
        else:
            break

    if not quit_hand and player_total <= 21:
        run_dealer_turn(dealer.hand, shoe)
        determine_winner(player.hand, dealer.hand, player)

    return True

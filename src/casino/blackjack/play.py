from bbsengine6 import util, io
from .. import lib as libcasino


def init(args, **kw):
    return True


def access(args, op, **kw):
    return True


def buildargs(args=None, **kw):
    return None


def run_dealer_turn(hand: libcasino.Hand, shoe) -> dict:
    """Run dealer's turn - hit on 16 or less, stand on 17+."""
    io.echo("\n{title}Dealer's turn:{normal}")

    hand.show(hide=False)

    total = hand.calcvalue()
    while total < 17:
        io.echo(f"Dealer has {total}, hitting...")
        hand.hit(shoe)
        hand.show(hide=False)
        total = hand.calcvalue()

    if total > 21:
        io.echo("{error}Dealer busts!{normal}")
        return {"bust": True, "total": total}

    io.echo(f"Dealer stands on {total}")
    return {"bust": False, "total": total}


def determine_winner(
    player_hand: libcasino.Hand, dealer_hand: libcasino.Hand, player
) -> None:
    """Determine winner and update player stats."""
    player_total = player_hand.calcvalue()
    dealer_total = dealer_hand.calcvalue()

    if player_total > 21:
        io.echo("{error}You bust! Dealer wins.{normal}")
        player.incstat("loss")
    elif dealer_total > 21:
        io.echo("{success}Dealer busts! You win!{normal}")
        player.incstat("win")
    elif player_total > dealer_total:
        io.echo(f"{{success}}You win!{{normal}} {player_total} vs {dealer_total}")
        player.incstat("win")
    elif player_total < dealer_total:
        io.echo(f"{{error}}Dealer wins!{{normal}} {dealer_total} vs {player_total}")
        player.incstat("loss")
    else:
        io.echo(f"{{warning}}Push!{{normal}} Both have {player_total}")
        player.incstat("draw")


def main(args, **kw):
    player = kw.get("player")
    dealer = kw.get("dealer")
    shoe = kw.get("shoe")

    if player is None or dealer is None or shoe is None:
        io.echo(
            "{error}Error: missing required arguments (player, dealer, shoe){normal}"
        )
        return False

    util.heading("play blackjack")

    player.hand = libcasino.Hand("player 1")
    dealer.hand = libcasino.Hand("dealer")

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    io.echo("\n{title}Dealer's hand:{normal}")
    dealer.hand.show(hide=True)

    io.echo("\n{title}Your hand:{normal}")
    player.hand.show()
    io.echo(f"Total: {player.hand.calcvalue()}")

    player_total = player.hand.calcvalue()
    if player_total == 21 and len(player.hand.cards) == 2:
        io.echo("{success}Blackjack!{normal}")

    while True:
        choice = io.inputchoice(
            "{promptcolor}Action: {optioncolor}[H]it [S]tand{promptcolor}: {inputcolor}",
            "hs",
            "h",
        )

        if choice == "h":
            io.echo("{promptcolor}You hit:{normal}")
            player.hand.hit(shoe)
            player.hand.show()
            player_total = player.hand.calcvalue()
            io.echo(f"Total: {player_total}")

            if player_total > 21:
                io.echo("{error}Bust!{normal}")
                player.incstat("bust")
                break
            if player_total == 21:
                io.echo("21 - standing")
                break
        else:
            break

    if player_total <= 21:
        run_dealer_turn(dealer.hand, shoe)
        determine_winner(player.hand, dealer.hand, player)

    return True

# casino/yahtzee/play.py
# Door-mode play loop for yahtzee. Mirrors casino/slots/play.py and
# casino/blackjack/play.py in structure.
#
# Help wiring:
#   Every interactive prompt passes a help= callback so KEY_HELP / KEY_F1
#   redraws the prompt's option list. Each callback calls util.heading()
#   exactly once per display of help (one F1 press -> one heading).
#
# Action prompt headings use "play yahtzee"; score-category prompt
# headings use "score category" so F1 shows the category list with
# a banner that reflects the current step.

from typing import Any

from bbsengine6 import io, util

from .. import host
from . import lib as yahtzee_lib
from .dealer import YahtzeeDealer
from .player import YahtzeePlayer


def init(args, **kw: dict) -> bool:
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict):
    return None


def auto_main(args: Any, **kw: dict) -> bool:
    """Zero-player yahtzee: roll all 13 rounds, greedy score, no prompts.

    Mirrors the dice/lock/score flow of ``main`` but replaces each
    prompt with a deterministic call into ``lib.greedy_locks`` and
    ``lib.greedy_best_category``. Used by the ``--mode auto`` branch
    of ``casino.yahtzee.__main__.main`` to stress-test the score
    engine and produce reproducible 13-round transcripts.

    Per round:

    - Roll fresh dice (rolls_left goes 2 -> 1).
    - If rolls_left > 0, lock + reroll using ``greedy_locks``.
    - Pick the highest-scoring open category via
      ``greedy_best_category``, score, advance to next round.

    Echoes a one-line summary per roll and per scored category, then
    a final scorecard and grand total.
    """
    player: YahtzeePlayer | None = kw.get("player")
    dealer: YahtzeeDealer | None = kw.get("dealer")
    if player is None:
        moniker = str(kw.get("moniker", "auto"))
        credits = int(kw.get("credits", 0))
        bet_amount = int(kw.get("bet_amount", yahtzee_lib.MIN_BET))
        if credits < bet_amount:
            credits = bet_amount
        player = YahtzeePlayer(
            moniker=moniker,
            credits=credits,
            bet_amount=bet_amount,
        )
    if dealer is None:
        dealer = YahtzeeDealer()

    util.heading("play yahtzee (auto)")
    io.echo(
        f"{{var:labelcolor}}Bet{{var:valuecolor}} {player.bet_amount}  "
        f"{{var:labelcolor}}Rounds{{var:valuecolor}} 13  "
        f"{{var:labelcolor}}strategy{{var:valuecolor}} greedy"
    )

    while not player.is_over:
        player.dice = dealer.fresh()
        player.locked = [False] * 5
        player.rolls_left = 1
        io.echo(
            f"{{var:labelcolor}}Round{{var:valuecolor}} "
            f"{player.round_idx + 1}/13  "
            f"{{var:labelcolor}}roll{{var:valuecolor}} "
            f"{' '.join(str(d) for d in player.dice)}"
        )

        if player.rolls_left > 0:
            player.locked = yahtzee_lib.greedy_locks(player.dice)
            player.dice = dealer.reroll(player.dice, player.locked)
            player.rolls_left = 0
            io.echo(
                f"{{var:labelcolor}}  reroll{{var:valuecolor}} "
                f"{' '.join(str(d) for d in player.dice)}  "
                f"{{var:labelcolor}}locked{{var:valuecolor}} "
                f"{' '.join('L' if l else '.' for l in player.locked)}"
            )

        category = yahtzee_lib.greedy_best_category(player.dice, player.scorecard)
        value = yahtzee_lib.score(player.dice, category)
        net = yahtzee_lib.net_payout(value)
        player.scorecard[category] = value
        player.last_score = value
        player.round_idx += 1
        player.dice = (0, 0, 0, 0, 0)
        player.locked = [False] * 5
        player.rolls_left = 2

        io.echo(
            f"{{var:labelcolor}}  scored{{var:valuecolor}} {value}"
            f"{{var:labelcolor}} into {{var:valuecolor}}{category}"
            f"{{var:labelcolor}} (net {{var:valuecolor}}{net:+d}"
            f"{{var:labelcolor}})."
        )

        if player.round_idx >= 13:
            player.is_over = True

    io.echo("{f6}")
    io.echo(f"{{var:titlecolor}}final scorecard{{/all}}")
    for cat in yahtzee_lib.CATEGORIES:
        v = player.scorecard[cat]
        if v is None:
            io.echo("  {var:labelcolor}" + f"{cat:<16} {{var:labelcolor}}--")
        else:
            io.echo(
                "  {var:labelcolor}" + f"{cat:<16} {{var:valuecolor}}{v}"
            )
    io.echo(
        f"{{var:titlecolor}}Game over!{{var:normalcolor}}  "
        f"{{var:labelcolor}}Grand total{{var:valuecolor}} {player.grand_total()}"
    )
    return True

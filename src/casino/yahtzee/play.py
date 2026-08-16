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

from . import lib as yahtzee_lib
from .dealer import YahtzeeDealer
from .player import YahtzeePlayer


def init(args, **kw: dict) -> bool:
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict):
    return None


def _render_action_help(**kwargs) -> None:
    """F1/HELP callback for the per-round action prompt.

    Per the spec: util.heading() is called exactly once per display
    of help, then the option list is echoed.
    """
    util.heading("play yahtzee")
    io.echo("{var:optioncolor}[R]{var:labelcolor}oll the dice (start of round)")
    io.echo("{var:optioncolor}[L]{var:labelcolor}ock dice and reroll (while rolls_left > 0)")
    io.echo("{var:optioncolor}[S]{var:labelcolor}core into a category (any time)")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit the game")


def _render_score_help(**kwargs) -> None:
    """F1/HELP callback for the score-category prompt.

    Per the spec: util.heading() is called exactly once per display
    of help, then the option list (13 categories) is echoed.
    """
    util.heading("score category")
    for cat in yahtzee_lib.CATEGORIES:
        io.echo(
            "{var:optioncolor}["
            + cat[0].upper()
            + "]{var:labelcolor}"
            + cat
        )


def _prompt_action(
    player: YahtzeePlayer, dealer: YahtzeeDealer
) -> str | None:
    """Show the current round and ask the player what to do.

    Performs the dice side effects for [R] and [L] so the player
    sees fresh dice before deciding whether to score. Returns one
    of "R", "L", "S", "Q" (uppercase). Returns None on EOF /
    interrupt.
    """
    _render_action_help()
    while True:
        choice = io.inputchoice(
            "{var:promptcolor}Action: {var:optioncolor}[RLSQ]{var:promptcolor}: {var:inputcolor}",
            "rlsq",
            default="r",
            help=_render_action_help,
        )

        if choice == "R":
            if player.rolls_left != 2:
                io.echo(
                    "{var:warning}Already rolled this round; reroll or score instead.{var:normalcolor}"
                )
                continue
            player.dice = dealer.fresh()
            player.locked = [False] * 5
            player.rolls_left = 1
            _show_dice(player)
            return "R"
        if choice == "L":
            if player.rolls_left <= 0:
                io.echo(
                    "{var:warning}No rolls left; score instead.{var:normalcolor}"
                )
                continue
            locks = _prompt_locks(player)
            if locks is None:
                continue
            player.locked = locks
            player.dice = dealer.reroll(player.dice, player.locked)
            player.rolls_left -= 1
            _show_dice(player)
            return "L"
        if choice == "S":
            return "S"
        if choice == "Q":
            return "Q"


def _prompt_locks(player: YahtzeePlayer) -> list[bool] | None:
    """Prompt the player for which dice indices to keep (lock).

    Returns a list[bool] of length 5, or None if the player wants
    to back out (empty / interrupt).
    """
    raw = io.inputstring(
        "{var:promptcolor}Lock which dice? "
        "(e.g. '013' for dice 0,1,3; blank to skip): {var:inputcolor}",
        default="",
    )
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    locked = [False] * 5
    for ch in raw:
        if not ch.isdigit():
            io.echo(
                f"{{var:warning}}Invalid digit '{ch}'; ignoring rest of input.{{var:normalcolor}}"
            )
            break
        idx = int(ch)
        if not (0 <= idx < 5):
            io.echo(
                f"{{var:warning}}Index {idx} out of [0,4]; ignoring rest of input.{{var:normalcolor}}"
            )
            break
        locked[idx] = True
    return locked


def _prompt_score_category(player: YahtzeePlayer) -> str | None:
    """Show the scorecard and ask the player which category to score.

    Returns the category name, or None on interrupt.
    """
    _show_scorecard(player)
    letters = "abcdefghijklm"
    while True:
        choice = io.inputchoice(
            "{var:promptcolor}Score into which category? {var:inputcolor}",
            letters,
            default="c",
            help=_render_score_help,
        )
        idx = letters.index(choice.lower())
        category = yahtzee_lib.CATEGORIES[idx]
        if player.scorecard[category] is not None:
            io.echo(
                f"{{var:warning}}{category} already scored as "
                f"{player.scorecard[category]}; pick another.{{var:normalcolor}}"
            )
            continue
        return category


def _show_dice(player: YahtzeePlayer) -> None:
    faces = " ".join(str(d) for d in player.dice)
    locked = " ".join("L" if lock else "." for lock in player.locked)
    io.echo(
        f"{{var:labelcolor}}Dice:{{var:valuecolor}} {faces}  "
        f"{{var:labelcolor}}[{locked}]{{var:normalcolor}}"
    )
    io.echo(
        f"{{var:labelcolor}}Round{{var:valuecolor}} {player.round_idx + 1}/13  "
        f"{{var:labelcolor}}rolls_left{{var:valuecolor}} {player.rolls_left}  "
        f"{{var:labelcolor}}grand_total{{var:valuecolor}} {player.grand_total()}"
    )


def _show_scorecard(player: YahtzeePlayer) -> None:
    for cat in yahtzee_lib.CATEGORIES:
        v = player.scorecard[cat]
        if v is None:
            io.echo("  {var:labelcolor}" + f"{cat:<16} {{var:labelcolor}}--")
        else:
            io.echo(
                "  {var:labelcolor}" + f"{cat:<16} {{var:valuecolor}}{v}"
            )


def main(args: Any, **kw: dict) -> bool:
    player: YahtzeePlayer | None = kw.get("player")
    dealer: YahtzeeDealer | None = kw.get("dealer")

    if player is None or dealer is None:
        moniker = str(kw.get("moniker", "anon"))
        credits = int(kw.get("credits", 0))
        bet_amount = int(kw.get("bet_amount", yahtzee_lib.MIN_BET))
        player = YahtzeePlayer(
            moniker=moniker,
            credits=credits,
            bet_amount=bet_amount,
        )
        dealer = YahtzeeDealer()

    util.heading("play yahtzee")
    io.echo(
        f"{{var:labelcolor}}Bet{{var:valuecolor}} {player.bet_amount}  "
        f"{{var:labelcolor}}Credits{{var:valuecolor}} {player.credits}  "
        f"{{var:labelcolor}}Rounds{{var:valuecolor}} 13"
    )

    while not player.is_over:
        action = _prompt_action(player, dealer)
        if action is None or action == "Q":
            io.echo(
                f"{{var:labelcolor}}Quitting yahtzee; final score {{var:valuecolor}}"
                f"{player.grand_total()}{{var:normalcolor}}"
            )
            return True
        if action != "S":
            continue

        category = _prompt_score_category(player)
        if category is None:
            continue
        value = yahtzee_lib.score(player.dice, category)
        net = yahtzee_lib.net_payout(value)
        player.scorecard[category] = value
        player.last_score = value
        player.round_idx += 1
        player.dice = (0, 0, 0, 0, 0)
        player.locked = [False] * 5
        player.rolls_left = 2

        io.echo(
            f"{{var:labelcolor}}Scored{{var:valuecolor}} {value}{{var:labelcolor}} "
            f"into {{var:valuecolor}}{category}{{var:labelcolor}} "
            f"(net {{var:valuecolor}}{net:+d}{{var:labelcolor}})."
        )

        if player.round_idx >= 13:
            player.is_over = True

    io.echo(
        f"{{var:titlecolor}}Game over!{{var:normalcolor}}  "
        f"{{var:labelcolor}}Grand total{{var:valuecolor}} {player.grand_total()}"
    )
    return True

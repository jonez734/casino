# casino/slots/__main__.py
# Slots subpackage entry point.
#
# Default mode (no args): smoke-test the slots engine. Reads no
# database state, no I/O, prints one spin result with the box-character
# renderer. Useful for verifying the install:
#
#   python -m casino.slots
#
# Door mode (--door): full door-mode play loop. Mirrors the BBS
# `play slots` flow but invoked directly from the command line.
#
# Demo mode (--demo N): run N spins at a flat bet and print summary
# statistics (win rate, realized RTP, biggest win). Useful for
# sanity-checking the paytable + reel strips.
#
# CLI arguments are kept minimal; door mode uses the table's min/max
# bet kwargs and starts with the supplied credits.

from __future__ import annotations

import argparse
import random
import sys

from . import lib
from .dealer import SlotDealer
from .player import SlotPlayer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="casino.slots",
        description="Slot machine subpackage entry point",
    )
    parser.add_argument(
        "--door",
        action="store_true",
        help="Run the door-mode play loop (interactive)",
    )
    parser.add_argument(
        "--demo",
        type=int,
        default=0,
        metavar="N",
        help="Run N spins at a flat bet and print summary statistics",
    )
    parser.add_argument(
        "--bet",
        type=int,
        default=1,
        help="Flat bet amount for --demo (default: 1)",
    )
    parser.add_argument(
        "--credits",
        type=int,
        default=1000,
        help="Starting credits for --door (default: 1000)",
    )
    parser.add_argument(
        "--min-bet",
        type=int,
        default=1,
        help="Minimum bet for --door (default: 1)",
    )
    parser.add_argument(
        "--max-bet",
        type=int,
        default=1000,
        help="Maximum bet for --door (default: 1000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for deterministic spins",
    )
    parser.add_argument(
        "--rtp-progress",
        type=int,
        default=0,
        metavar="N",
        help="Show a progress bar via screen.updateprogress while "
             "computing the theoretical RTP, updating every N outcomes. "
             "Default 0 (no progress).",
    )
    return parser


def _smoke_spin(seed: int | None, rtp_progress: int) -> int:
    rng = lib.RNG(random.Random(seed) if seed is not None else random.Random())
    dealer = SlotDealer(
        reels=lib.default_reels(lib.DEFAULT_SYMBOLS, rng),
        paytable=lib.Paytable(),
        rng=rng,
    )
    print("default reels:", len(dealer._reels), "x", dealer.num_rows)
    print("target RTP:    ", f"{lib.RTP_DEFAULT:.2%}")
    print("theoretical RTP:", f"{dealer.paytable.theoretical_rtp(dealer._reels, progress_every=rtp_progress):.4f}")
    print()

    player = SlotPlayer(
        moniker="smoke",
        credits=10,
        dealer=dealer,
        min_bet=1,
        max_bet=10,
    )
    result = player.play(bet=5)
    print(lib.render_ascii(result))
    print(
        f"bet={result.bet}  payout={result.payout}  "
        f"net={result.net:+d}  credits={player.credits}"
    )
    return 0


def _run_demo(n: int, bet: int, seed: int | None, rtp_progress: int) -> int:
    if n <= 0:
        print("--demo requires a positive N", file=sys.stderr)
        return 2
    if bet <= 0:
        print("--bet must be positive", file=sys.stderr)
        return 2

    rng = lib.RNG(random.Random(seed) if seed is not None else random.Random())
    dealer = SlotDealer(
        reels=lib.default_reels(lib.DEFAULT_SYMBOLS, rng),
        paytable=lib.Paytable(),
        rng=rng,
    )

    total_wagered = 0
    total_payout = 0
    wins = 0
    biggest_win = 0
    biggest_win_payline: tuple[str, ...] | None = None

    for _ in range(n):
        result = dealer.play(bet=bet)
        total_wagered += bet
        total_payout += result.payout
        if result.did_win:
            wins += 1
        if result.payout > biggest_win:
            biggest_win = result.payout
            biggest_win_payline = result.wins[0].symbols if result.wins else None

    realized_rtp = (total_payout / total_wagered) if total_wagered else 0.0
    target_rtp = dealer.paytable.theoretical_rtp(dealer._reels, progress_every=rtp_progress)

    print(f"spins:          {n}")
    print(f"bet per spin:   {bet}")
    print(f"total wagered:  {total_wagered}")
    print(f"total payout:   {total_payout}")
    print(f"net:            {total_payout - total_wagered:+d}")
    print(f"win rate:       {wins / n:.2%}")
    print(f"realized RTP:   {realized_rtp:.4f}")
    print(f"target RTP:     {target_rtp:.4f} (theoretical)")
    print(f"RTP delta:      {realized_rtp - target_rtp:+.4f}")
    print(f"biggest win:    {biggest_win}")
    if biggest_win_payline is not None:
        print(f"biggest pay:    {biggest_win_payline}")
    return 0


def _run_door(args: argparse.Namespace) -> int:
    """Door-mode play loop. Mirrors casino/slots/play.py:main but
    invoked from the CLI without going through the BBS session.
    """
    rng = lib.RNG(random.Random(args.seed) if args.seed is not None else random.Random())
    dealer = SlotDealer(
        reels=lib.default_reels(lib.DEFAULT_SYMBOLS, rng),
        paytable=lib.Paytable(),
        rng=rng,
    )
    player = SlotPlayer(
        moniker="cli",
        credits=args.credits,
        dealer=dealer,
        min_bet=args.min_bet,
        max_bet=args.max_bet,
    )

    print(f"credits={player.credits}  bet limits={player.min_bet}..{player.max_bet}")
    while True:
        try:
            bet_str = input(f"bet (q to quit, {player.min_bet}..{min(player.max_bet, player.credits)}): ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if bet_str.strip().lower() in ("q", "quit", "exit"):
            return 0
        try:
            bet = int(bet_str)
        except ValueError:
            print("not an integer")
            continue
        err = player.validate_bet(bet)
        if err is not None:
            print(f"  {err}")
            continue
        result = player.play(bet=bet)
        print()
        print(lib.render_ascii(result))
        if result.did_win:
            print(f"  won {result.payout}  net={result.net:+d}")
        else:
            print(f"  no win  net={result.net:+d}")
        print(f"  credits={player.credits}")
        print()
        if player.credits < player.min_bet:
            print("credits below minimum bet; ending session")
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.door:
        return _run_door(args)
    if args.demo > 0:
        return _run_demo(args.demo, args.bet, args.seed, args.rtp_progress)
    return _smoke_spin(args.seed, args.rtp_progress)


if __name__ == "__main__":
    sys.exit(main())

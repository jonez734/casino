"""Casino's credits <-> bank exchange: each player's ratio, passed to bbsengine6 BankService.exchange.

A player's ratio is two positive integers (ratio_num, ratio_den): ``ratio_num`` casino credits for every ``ratio_den`` bank credits.
A stored value that is missing or not two positive integers falls back to 1:1, so a bad row cannot mint or destroy coins.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

DEFAULT_RATIO: Tuple[int, int] = (1, 1)


def ratio_for_row(row: Dict[str, Any]) -> Tuple[int, int]:
    """The (num, den) for a casino player row, or the 1:1 default when the stored values are not valid."""
    num, den = row.get("ratio_num"), row.get("ratio_den")
    if isinstance(num, int) and isinstance(den, int) and num > 0 and den > 0:
        return (num, den)
    return DEFAULT_RATIO


def exchange_for_player(bank: Any, moniker: str, amount: int, *, to: str, token_moniker: str,
                        ratio: Tuple[int, int]) -> Dict[str, Any]:
    """Exchange ``amount`` for ``moniker`` at ``ratio``, through a BankService (or any object with ``exchange``)."""
    return bank.exchange(moniker, amount, to=to, ratio=ratio, token_moniker=token_moniker)

"""Typed views of blackjack's payloads (blackjack slice 3c-2).

These are casino's types, separate from the seam's ActionResult: a payload is the data a round produces
or a table shows, not a refusal. Each type keeps the dict it was built from, so ``to_dict`` returns exactly
the dict the client receives, including keys the type does not name. The typed fields are read-only views
over that dict, which is what makes a conversion safe: no wire output changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SettlementOutcome:
    """One hand's outcome. ``data`` keeps the whole entry, so keys not named here are not lost."""

    hand_id: int
    player: str
    result: str
    bet: int
    net: int
    reason: str | None
    text: str | None
    data: Mapping[str, Any]

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SettlementOutcome":
        return cls(
            hand_id=d["hand_id"], player=d["player"], result=d["result"], bet=d["bet"], net=d["net"],
            reason=d.get("reason"), text=d.get("text"), data=dict(d),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


class RoundSettlement:
    """A settled round: each hand's outcome and the dealer's hand."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RoundSettlement":
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    @property
    def outcomes(self) -> tuple[SettlementOutcome, ...]:
        return tuple(SettlementOutcome.from_dict(o) for o in self._data.get("outcomes", ()))

    @property
    def has_outcomes(self) -> bool:
        return bool(self._data.get("outcomes"))

    @property
    def dealer_total(self) -> int | None:
        return self._data.get("dealer_total")


class GameState:
    """The table's state as the client renders it. Only the fields the server reads are named."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GameState":
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    @property
    def table_moniker(self) -> str | None:
        return self._data.get("table_moniker")

    @property
    def phase(self) -> str | None:
        return self._data.get("phase")


class PlacedBet:
    """The result of placing a bet: the new hand, and the dealer's peek when there was one."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlacedBet":
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    @property
    def bet_id(self) -> int | None:
        return self._data.get("bet_id")

    @property
    def hand_id(self) -> int | None:
        return self._data.get("hand_id")

    @property
    def cards(self) -> list[str]:
        return list(self._data.get("cards", []))

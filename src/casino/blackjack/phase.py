from enum import Enum


class GamePhase(Enum):
    WAITING = "waiting"
    BETTING = "betting"
    PLAYING = "playing"
    SETTLING = "settling"
    SETTLED = "settled"

    @classmethod
    def from_string(cls, s: str) -> "GamePhase":
        for phase in cls:
            if phase.value == s.lower():
                return phase
        raise ValueError(f"Unknown game phase: {s}")

    def __str__(self) -> str:
        return self.value

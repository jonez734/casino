from .base import BaseVariant, BetLimits
from .texas_hold_em import TexasHoldEm
from .omaha import Omaha, OmahaHiLo
from .seven_card_stud import SevenCardStud


VARIANTS: dict[str, type[BaseVariant]] = {
    "texas_hold_em": TexasHoldEm,
    "holdem": TexasHoldEm,
    "omaha": Omaha,
    "omaha_hi_lo": OmahaHiLo,
    "seven_card_stud": SevenCardStud,
    "stud": SevenCardStud,
}


def get_variant(name: str) -> BaseVariant:
    variant_class = VARIANTS.get(name.lower())
    if variant_class is None:
        available = ", ".join(VARIANTS.keys())
        raise ValueError(f"Unknown variant: {name}. Available: {available}")
    return variant_class()


def list_variants() -> list[str]:
    return list(VARIANTS.keys())


__all__ = [
    "BaseVariant",
    "BetLimits",
    "TexasHoldEm",
    "Omaha",
    "SevenCardStud",
    "get_variant",
    "list_variants",
    "VARIANTS",
]

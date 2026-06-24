from importlib import import_module
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from .base import BaseVariant, BetLimits

if TYPE_CHECKING:
    from typing import Any


_VARIANT_MODULES = {
    "texas_hold_em": "casino.poker.variant.texas_hold_em",
    "omaha": "casino.poker.variant.omaha",
    "seven_card_stud": "casino.poker.variant.seven_card_stud",
}


class VariantRegistry:
    _variants: dict[str, type[BaseVariant]] = {}
    _discovered: bool = False
    _registered: bool = False

    @classmethod
    def register(cls, name: str, variant_class: type[BaseVariant]) -> None:
        cls._variants[name.lower()] = variant_class

    @classmethod
    def get(cls, name: str) -> BaseVariant:
        cls._ensure_discovered()
        name = name.lower()
        if name not in cls._variants:
            available = ", ".join(cls._variants.keys())
            raise ValueError(f"Unknown variant: {name}. Available: {available}")
        return cls._variants[name]()

    @classmethod
    def _ensure_discovered(cls) -> None:
        if cls._discovered:
            return
        cls._discovered = True
        cls._register_builtins()
        cls._discover_from_entry_points()

    @classmethod
    def _register_builtins(cls) -> None:
        if cls._registered:
            return
        cls._registered = True

        from .texas_hold_em import TexasHoldEm
        cls.register("texas_hold_em", TexasHoldEm)
        cls.register("holdem", TexasHoldEm)

        from .omaha import Omaha, OmahaHiLo
        cls.register("omaha", Omaha)
        cls.register("omaha_hi_lo", OmahaHiLo)

        from .seven_card_stud import SevenCardStud
        cls.register("seven_card_stud", SevenCardStud)
        cls.register("stud", SevenCardStud)

    @classmethod
    def _discover_from_entry_points(cls) -> None:
        try:
            eps = entry_points(group="casino.poker.variants")
            for ep in eps:
                try:
                    variant_class: type[BaseVariant] = ep.load()
                    cls.register(ep.name, variant_class)
                except Exception:
                    pass
        except Exception:
            pass

    @classmethod
    def list(cls) -> list[str]:
        cls._ensure_discovered()
        return list(cls._variants.keys())

    @classmethod
    def get_variants(cls) -> dict[str, type[BaseVariant]]:
        cls._ensure_discovered()
        return cls._variants.copy()


VARIANTS: dict[str, type[BaseVariant]] = VariantRegistry._variants


def get_variant(name: str) -> BaseVariant:
    return VariantRegistry.get(name)


def list_variants() -> list[str]:
    return VariantRegistry.list()


def get_all_variants() -> list[type[BaseVariant]]:
    VariantRegistry._ensure_discovered()
    return list(VariantRegistry._variants.values())


__all__ = [
    "BaseVariant",
    "BetLimits",
    "get_variant",
    "list_variants",
    "VARIANTS",
    "VariantRegistry",
    "get_all_variants",
]

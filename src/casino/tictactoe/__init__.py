from bbsengine6 import register_module

__version__ = "202606261200"


__all__ = ["lib", "dealer", "player", "service"]


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.tictactoe",
        module_path="casino.tictactoe",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw):
    return None


def main(args, **kw):
    """Standalone door-mode entry. ``casino.tictactoe.__main__.main``
    runs a single game (mode 0 = 2 AI self-play, mode 1 = human vs AI)
    using the local Postgres pool. The BED surface
    (``casino.tictactoe.api_handler``) is still the primary v1 entry
    point for multi-player and live state broadcast; this shim is for
    quick games without the bed daemon."""
    return True

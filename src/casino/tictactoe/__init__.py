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
    """No door-mode entry; tictactoe v1 is BED-only."""
    return True

from bbsengine6 import register_module


__version__ = "202601010900"


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.yahtzee",
        module_path="casino.yahtzee",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw):
    return None


def main(args, **kw):
    """No door-mode entry; yahtzee v1 is BED-only."""
    return True

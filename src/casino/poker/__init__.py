from bbsengine6 import io, register_module


__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.poker",
        module_path="casino.poker",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw):
    return None


def main(args, **kw):
    io.echo("poker module not yet implemented")
    return True

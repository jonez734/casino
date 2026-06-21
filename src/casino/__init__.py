from bbsengine6 import util, register_module
from . import lib


__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino",
        module_path="casino",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict) -> bool:
    return None


def main(args, **kw):
    util.heading("HEADER")
    lib.runmodule("main", **kw)
    return True

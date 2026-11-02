import argparse
from bbsengine6 import register, util

from . import lib

__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    # Hosted: the hosting program passes its bed session (with a ``choose`` menu). Route
    # casino's menus through it. Standalone runs pass no bedsession, so menus stay on
    # io.inputchoice.
    bedsession = kw.get("bedsession")
    if bedsession is not None:
        from . import host as casino_host

        casino_host.register_menu(bedsession.choose)
        casino_host.register_line_reader(getattr(bedsession, "read_line", None))
    register(
        name="casino",
        module_path="casino",
        version=__version__,
        apis={},
    )
    # Casino supplies bbsengine6's @here group: the sender's current table.
    from casino import here as casino_here

    casino_here.install(args)
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args: argparse.Namespace, **kw: dict) -> argparse.ArgumentParser | None:
    return None


def main(args, **kw):
    util.heading("HEADER")
    lib.runmodule("main", **kw)
    return True

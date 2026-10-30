from bbsengine6 import register_module, util

from . import lib
from .menus import register_casino_lib_options

__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    # Hosted: the hosting program passes its bed session (with a ``choose`` menu). Route
    # casino's menus through it. Standalone runs pass no bedsession, so menus stay on
    # io.inputchoice.
    bedsession = kw.get("bedsession")
    if bedsession is not None:
        from . import host as casino_host

        casino_host.register_menu(bedsession.choose)
    register_module(
        name="casino",
        module_path="casino",
        version=__version__,
        apis={},
    )
    # Casino supplies bbsengine6's @here group: the sender's current table.
    from casino import here as casino_here

    casino_here.install(args)
    register_casino_lib_options()
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict) -> bool:
    return None


def main(args, **kw):
    util.heading("HEADER")
    lib.runmodule("main", **kw)
    return True

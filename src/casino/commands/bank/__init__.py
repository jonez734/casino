# commands/bank/__init__.py
# Bank commands: balance, transfers, approvals, and history.

from bbsengine6 import io

from casino.commands import _common

from . import lib

__version__ = "202210010112"

SUBCOMMANDS = {
    "balance": lib.bank_balance,
    "add": lib.bank_add,
    "remove": lib.bank_remove,
    "transfer": lib.bank_transfer,
    "approve": lib.bank_approve,
    "reject": lib.bank_reject,
    "pending": lib.bank_pending,
    "history": lib.bank_history,
    "list": lib.bank_list_all,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.bank",
        module_path="casino.commands.bank",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("bank", subcommands=SUBCOMMANDS)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="bank",
        **kw,
    )

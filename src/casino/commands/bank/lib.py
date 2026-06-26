# commands/bank/lib.py
# Bank command functions

import asyncio

from bbsengine6 import io


def get_client():
    from casino.connect import get_client as _get_client

    return _get_client()


def bank_balance(args, client=None, **kwargs) -> bool:
    """Handle bank balance query."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_balance()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_add(args, client=None, **kwargs) -> bool:
    """Handle add funds to bank."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_add()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_remove(args, client=None, **kwargs) -> bool:
    """Handle remove funds from bank."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_remove()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_transfer(args, client=None, **kwargs) -> bool:
    """Handle transfer request between tables."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_transfer()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_approve(args, client=None, **kwargs) -> bool:
    """Handle approve transfer."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_approve()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_reject(args, client=None, **kwargs) -> bool:
    """Handle reject transfer."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_reject()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_pending(args, client=None, **kwargs) -> bool:
    """Handle list pending transfers."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_pending()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_history(args, client=None, **kwargs) -> bool:
    """Handle bank history query."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_history()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_list_all(args, client=None, **kwargs) -> bool:
    """Handle list all table balances (sysop only)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bank_list_all()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def menu(args, client=None, **kwargs):
    """Show bank operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = io.inputchoice(
            "{var:promptcolor}[B]alance  [A]dd  [W]ithdraw  [T]ransfer  [P]ending  [H]istory  [L]ist all  [Q]uit: {var:inputcolor}",
            "b,a,w,t,p,h,l,q",
            default="q",
        )

        if cmd == "B":
            bank_balance(args, client=client, **kwargs)
        elif cmd == "A":
            bank_add(args, client=client, **kwargs)
        elif cmd == "W":
            bank_remove(args, client=client, **kwargs)
        elif cmd == "T":
            bank_transfer(args, client=client, **kwargs)
        elif cmd == "P":
            bank_pending(args, client=client, **kwargs)
        elif cmd == "H":
            bank_history(args, client=client, **kwargs)
        elif cmd == "L":
            bank_list_all(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True

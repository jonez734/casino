from bbsengine6 import io, util, member
from casino.dal import table as dal_table
from casino.services import table as table_service
from casino.services import bank as bank_service


def init(args, **kwargs):
    return True


def access(args, op, **kwargs):
    return member.checkflag(args, "SYSOP", **kwargs)


def buildargs(args, **kwargs):
    return None


def main(args, **kwargs):
    sysop = member.issysop(args, **kwargs)
    if sysop is False:
        io.echo("permission denied.", level="error")
        return

    done = False
    while not done:
        util.heading("casino maint")
        io.echo("{optioncolor}[B]{labelcolor} House Bank")
        io.echo("{optioncolor}[T]{labelcolor} Table")
        io.echo("{optioncolor}[G]{labelcolor} Game")
        io.echo("{optioncolor}[H]{labelcolor} Hand")
        io.echo("{optioncolor}[P]{labelcolor} Player")
        io.echo("{optioncolor}[X]{labelcolor} Exit")

        ch = io.inputchar(
            "{var:promptcolor}casino maint: {var:inputcolor}",
            "BTGHQX",
            "",
        )

        if ch == "X" or ch == "Q":
            done = True
        elif ch == "B":
            house_bank_maint(args, sysop)
        elif ch == "T":
            table_maint(args, sysop)
        elif ch == "G":
            io.echo("Game (not implemented)")
        elif ch == "H":
            io.echo("Hand (not implemented)")
        elif ch == "P":
            io.echo("Player (not implemented)")

    return True


def table_maint(args, is_sysop=None):
    """Table maintenance menu."""
    is_sysop_bool = bool(is_sysop)
    done = False
    while not done:
        util.heading("casino table maint")
        io.echo("{optioncolor}[L]{labelcolor} List tables")
        io.echo("{optioncolor}[S]{labelcolor} Set status (open/closed)")
        io.echo("{optioncolor}[R]{labelcolor} Rename table")
        io.echo("{optioncolor}[M]{labelcolor} Set min/max bet")
        io.echo("{optioncolor}[E]{labelcolor} Reset shoe")
        io.echo("{optioncolor}[D]{labelcolor} Delete table")
        io.echo("{optioncolor}[X]{labelcolor} Exit")

        ch = io.inputchar(
            "{var:promptcolor}table maint: {var:inputcolor}",
            "LSRMEDX",
            "",
        )

        if ch == "X" or ch == "Q":
            done = True
        elif ch == "L":
            list_tables(args)
        elif ch == "S":
            set_table_status(args, is_sysop_bool)
        elif ch == "R":
            rename_table(args, is_sysop_bool)
        elif ch == "M":
            set_table_bets(args, is_sysop_bool)
        elif ch == "E":
            reset_table_shoe(args, is_sysop_bool)
        elif ch == "D":
            delete_table(args, is_sysop_bool)


def list_tables(args):
    """List all tables with their status."""
    tables = dal_table.list_tables(args)
    if not tables:
        io.echo("No tables found.")
        return

    for t in tables:
        status = t.get("status", "open")
        io.echo(f"  {t['moniker']}: {t['type']} owner={t['ownermoniker']} "
                f"bet={t['minimumbet']}-{t['maximumbet']} status={status}")


def set_table_status(args, is_sysop: bool):
    """Set table status (open/closed)."""
    moniker = io.inputstring("table moniker: ")
    table = dal_table.get_table(args, moniker)
    if not table:
        io.echo("Table not found.", level="error")
        return

    current_moniker = member.getcurrentmoniker(args)
    if current_moniker is None:
        io.echo("Not logged in.", level="error")
        return

    if table["ownermoniker"] != current_moniker and not is_sysop:
        io.echo("Permission denied. Only the owner or sysop can edit this table.", level="error")
        return

    status = io.inputstring("status (open/closed): ")
    if status not in ("open", "closed"):
        io.echo("Status must be 'open' or 'closed'.", level="error")
        return

    service = table_service.TableService(args)
    result = service.update_table(moniker, current_moniker, is_sysop, status=status)
    if result.get("success"):
        io.echo(result["message"])
    else:
        io.echo(result.get("message", "Failed to update table"), level="error")


def rename_table(args, is_sysop: bool):
    """Rename a table."""
    moniker = io.inputstring("current table moniker: ")
    table = dal_table.get_table(args, moniker)
    if not table:
        io.echo("Table not found.", level="error")
        return

    current_moniker = member.getcurrentmoniker(args)
    if current_moniker is None:
        io.echo("Not logged in.", level="error")
        return

    if table["ownermoniker"] != current_moniker and not is_sysop:
        io.echo("Permission denied. Only the owner or sysop can edit this table.", level="error")
        return

    new_moniker = io.inputstring("new table moniker: ")
    if not new_moniker:
        io.echo("New moniker cannot be empty.", level="error")
        return

    service = table_service.TableService(args)
    result = service.update_table(moniker, current_moniker, is_sysop, new_moniker=new_moniker)
    if result.get("success"):
        io.echo(result["message"])
    else:
        io.echo(result.get("message", "Failed to rename table"), level="error")


def set_table_bets(args, is_sysop: bool):
    """Set table min/max bets."""
    moniker = io.inputstring("table moniker: ")
    table = dal_table.get_table(args, moniker)
    if not table:
        io.echo("Table not found.", level="error")
        return

    current_moniker = member.getcurrentmoniker(args)
    if current_moniker is None:
        io.echo("Not logged in.", level="error")
        return

    if table["ownermoniker"] != current_moniker and not is_sysop:
        io.echo("Permission denied. Only the owner or sysop can edit this table.", level="error")
        return

    min_bet_input = io.inputinteger(f"{{var:promptcolor}}minimum bet [{table['minimumbet']}]: {{var:inputcolor}}", table['minimumbet'])
    max_bet_input = io.inputinteger(f"{{var:promptcolor}}maximum bet [{table['maximumbet']}]: {{var:inputcolor}}", table['maximumbet'])

    if isinstance(min_bet_input, list) or isinstance(max_bet_input, list):
        io.echo("Please enter a single value, not a list.", level="error")
        return

    if min_bet_input is None or max_bet_input is None:
        io.echo("Invalid bet values.", level="error")
        return

    if min_bet_input > max_bet_input:
        io.echo("Minimum bet cannot be greater than maximum bet.", level="error")
        return

    service = table_service.TableService(args)
    result = service.update_table(moniker, current_moniker, is_sysop, minimumbet=min_bet_input, maximumbet=max_bet_input)
    if result.get("success"):
        io.echo(result["message"])
    else:
        io.echo(result.get("message", "Failed to update table"), level="error")


def reset_table_shoe(args, is_sysop: bool):
    """Reset table shoe."""
    moniker = io.inputstring("table moniker: ")
    table = dal_table.get_table(args, moniker)
    if not table:
        io.echo("Table not found.", level="error")
        return

    current_moniker = member.getcurrentmoniker(args)
    if current_moniker is None:
        io.echo("Not logged in.", level="error")
        return

    if table["ownermoniker"] != current_moniker and not is_sysop:
        io.echo("Permission denied. Only the owner or sysop can reset the shoe.", level="error")
        return

    service = table_service.TableService(args)
    result = service.reset_shoe(moniker, current_moniker, is_sysop)
    if result.get("success"):
        io.echo(result["message"])
    else:
        io.echo(result.get("message", "Failed to reset shoe"), level="error")


def delete_table(args, is_sysop: bool):
    """Delete a table."""
    moniker = io.inputstring("table moniker to delete: ")
    table = dal_table.get_table(args, moniker)
    if not table:
        io.echo("Table not found.", level="error")
        return

    current_moniker = member.getcurrentmoniker(args)
    if current_moniker is None:
        io.echo("Not logged in.", level="error")
        return

    if table["ownermoniker"] != current_moniker and not is_sysop:
        io.echo("Permission denied. Only the owner or sysop can delete this table.", level="error")
        return

    confirm = io.inputstring(f"confirm delete {moniker} (yes/no): ")
    if confirm.lower() != "yes":
        io.echo("Cancelled.")
        return

    service = table_service.TableService(args)
    result = service.delete_table(moniker, current_moniker, is_sysop)
    if result.get("success"):
        io.echo(result["message"])
    else:
        io.echo(result.get("message", "Failed to delete table"), level="error")


def house_bank_maint(args, is_sysop=None):
    """House bank account maintenance menu."""
    is_sysop_bool = bool(is_sysop)
    done = False
    while not done:
        util.heading("casino house bank")

        bank = bank_service.BankService(args)
        status = bank.get_house_balance_with_status()

        io.echo(f"House Balance: {status['balance']}")
        io.echo(f"Overdraft Limit: {status['overdraft_limit']}")
        io.echo(f"Available: {status['available']}")
        io.echo(f"Status: {status['status'].upper()}")
        io.echo("")
        io.echo("{optioncolor}[S]{labelcolor} Status")
        io.echo("{optioncolor}[L]{labelcolor} Set overdraft limit")
        io.echo("{optioncolor}[F]{labelcolor} Fund house")
        io.echo("{optioncolor}[W]{labelcolor} Withdraw from house")
        io.echo("{optioncolor}[H]{labelcolor} History")
        io.echo("{optioncolor}[X]{labelcolor} Exit")

        ch = io.inputchar(
            "{var:promptcolor}house bank: {var:inputcolor}",
            "SLFWXHX",
            "",
        )

        if ch == "X" or ch == "Q":
            done = True
        elif ch == "S":
            show_house_status(args, is_sysop_bool)
        elif ch == "L":
            set_overdraft_limit(args, is_sysop_bool)
        elif ch == "F":
            fund_house(args, is_sysop_bool)
        elif ch == "W":
            withdraw_house(args, is_sysop_bool)
        elif ch == "H":
            show_house_history(args, is_sysop_bool)


def show_house_status(args, is_sysop: bool):
    """Show detailed house bank status."""
    bank = bank_service.BankService(args)
    status = bank.get_house_balance_with_status()

    io.echo("")
    io.echo(f"  Balance: {status['balance']}")
    io.echo(f"  Overdraft Limit: {status['overdraft_limit']}")
    io.echo(f"  Available Credit: {status['available']}")
    io.echo(f"  Status: {status['status'].upper()}")

    if status['balance'] < 0:
        pct = abs(status['balance']) / max(status['overdraft_limit'], 1) * 100
        io.echo(f"  Overdraft Used: {pct:.1f}%")


def set_overdraft_limit(args, is_sysop: bool):
    """Set the overdraft limit for the house account."""
    if not is_sysop:
        io.echo("Permission denied. Sysop required.", level="error")
        return

    bank = bank_service.BankService(args)
    current = bank.get_house_balance_with_status()

    new_limit = io.inputinteger(
        f"{{var:promptcolor}}overdraft limit [{current['overdraft_limit']}]: {{var:inputcolor}}",
        current['overdraft_limit']
    )

    if isinstance(new_limit, list) or new_limit is None:
        io.echo("Invalid value.", level="error")
        return

    result = bank.bank.account.update_settings("casino:house", overdraft_limit=new_limit)
    if result:
        io.echo(f"Overdraft limit set to {new_limit}")
    else:
        io.echo("Failed to update overdraft limit", level="error")


def fund_house(args, is_sysop: bool):
    """Add funds to the house account."""
    if not is_sysop:
        io.echo("Permission denied. Sysop required.", level="error")
        return

    amount = io.inputinteger("{var:promptcolor}amount to add: {var:inputcolor}", 0)

    if isinstance(amount, list) or amount is None or amount <= 0:
        io.echo("Invalid amount.", level="error")
        return

    bank = bank_service.BankService(args)
    result = bank._transfer(
        "sysop",
        "casino:house",
        amount,
        "manual_deposit",
        "Manual funding by sysop",
        "sysop"
    )

    if result.get("success"):
        io.echo(f"Added {amount} to house account")
        io.echo(f"New balance: {result.get('to_balance')}")
    else:
        io.echo(result.get("message", "Failed to fund house"), level="error")


def withdraw_house(args, is_sysop: bool):
    """Withdraw funds from the house account."""
    if not is_sysop:
        io.echo("Permission denied. Sysop required.", level="error")
        return

    bank = bank_service.BankService(args)
    current = bank.get_house_balance_with_status()

    amount = io.inputinteger(
        f"{{var:promptcolor}}amount to withdraw [{current['balance']}]: {{var:inputcolor}}",
        current['balance']
    )

    if isinstance(amount, list) or amount is None or amount <= 0:
        io.echo("Invalid amount.", level="error")
        return

    result = bank._transfer(
        "casino:house",
        "sysop",
        amount,
        "manual_withdrawal",
        "Manual withdrawal by sysop",
        "sysop"
    )

    if result.get("success"):
        io.echo(f"Withdrew {amount} from house account")
        io.echo(f"New balance: {result.get('from_balance')}")
    else:
        io.echo(result.get("message", "Failed to withdraw"), level="error")


def show_house_history(args, is_sysop: bool):
    """Show house account transaction history."""
    bank = bank_service.BankService(args)
    history = bank.bank.get_history("casino:house", 20)

    if not history:
        io.echo("No transactions found.")
        return

    io.echo("")
    for txn in history:
        io.echo(f"  {txn['dateposted']} {txn['transactiontype']:12} {txn['amount']:+10}  {txn.get('description', '')}")

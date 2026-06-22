# casino/services/bank.py
# Casino table bank management - uses bbsengine6 bank module

from typing import Any, Dict, List, Optional

from bbsengine6 import database
from bbsengine6.bank import BankService as BankModule
from casino.dal import table as dal_table


class BankService:
    """Service for casino table bank management using bbsengine6 bank module."""

    def __init__(self, args: Any):
        self.args = args
        self.bank = BankModule(args)

    def _get_bank_account_id(self, table_moniker: str) -> Optional[int]:
        """Get the bank account ID for a table from casino.__bank_table mapping."""
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "SELECT bank_account_id FROM casino.__bank_table WHERE table_moniker = %s",
                    (table_moniker,)
                )
                row = cur.fetchone()
                return row["bank_account_id"] if row else None

    def _get_or_create_account(self, table_moniker: str) -> Optional[int]:
        """Get or create a bank account for a table."""
        existing_id = self._get_bank_account_id(table_moniker)
        if existing_id:
            return existing_id

        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return None

        owner_moniker = table.get("ownermoniker")
        if not owner_moniker:
            return None

        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "SELECT id FROM bank.__account WHERE moniker = %s",
                    (owner_moniker,)
                )
                row = cur.fetchone()
                if row:
                    account_id = row["id"]
                else:
                    cur.execute(
                        "INSERT INTO bank.__account (moniker, balance) VALUES (%s, 0) RETURNING id",
                        (owner_moniker,)
                    )
                    account_id = cur.fetchone()["id"]

                cur.execute(
                    "INSERT INTO casino.__bank_table (table_moniker, bank_account_id) VALUES (%s, %s)",
                    (table_moniker, account_id)
                )

                cur.execute(
                    "UPDATE casino.__table SET accountid = %s WHERE moniker = %s",
                    (account_id, table_moniker)
                )

        return account_id

    def get_balance(self, table_moniker: str) -> int:
        """Get current bank balance for a table."""
        account_id = self._get_bank_account_id(table_moniker)
        if not account_id:
            table = dal_table.get_table(self.args, table_moniker)
            account_id = table.get("accountid") if table else None
        if not account_id:
            return 0
        account = self.bank.account.get_by_id(account_id)
        return int(account["balance"]) if account else 0

    def get_table(self, table_moniker: str) -> Optional[Dict[str, Any]]:
        """Get table info including bank settings."""
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return None
        
        if not table.get("accountid"):
            self._get_or_create_account(table_moniker)
            table = dal_table.get_table(self.args, table_moniker)
        
        if table and table.get("accountid"):
            account = self.bank.account.get_by_id(table["accountid"])
            if account:
                table["bank"] = account["balance"]
                table["maxtransfer"] = account["maxtransfer"]
        return table

    def can_manage(self, table_moniker: str, moniker_check: str, is_sysop: bool = False) -> bool:
        """Check if a user can manage a table's bank."""
        if is_sysop:
            return True
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return False
        return table.get("ownermoniker", "").lower() == moniker_check.lower()

    def add_funds(
        self,
        table_moniker: str,
        amount: int,
        source: str = "house",
        member_moniker: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        """Add funds to a table bank (buy-in, adjustment, transfer_in)."""
        if amount <= 0:
            return {"success": False, "message": "Amount must be positive"}

        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return {"success": False, "message": "Table not found"}

        owner_moniker = table.get("ownermoniker")
        if not owner_moniker:
            return {"success": False, "message": "Table has no owner"}

        trans_type = "buyin" if source == "player" else "adjustment"
        if source == "transfer":
            trans_type = "transfer_in"

        result = self.bank.add_funds(
            owner_moniker,
            amount,
            transaction_type=trans_type,
            description=description or f"Table {table_moniker} deposit: {source}",
            member_moniker=member_moniker,
        )

        if result["success"]:
            result["message"] = f"Added {amount} to table {table_moniker} bank"
        
        return result

    def remove_funds(
        self,
        table_moniker: str,
        amount: int,
        reason: str = "adjustment",
        member_moniker: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        """Remove funds from a table bank (payout, transfer_out)."""
        if amount <= 0:
            return {"success": False, "message": "Amount must be positive"}

        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return {"success": False, "message": "Table not found"}

        owner_moniker = table.get("ownermoniker")
        if not owner_moniker:
            return {"success": False, "message": "Table has no owner"}

        trans_type = "payout" if reason == "payout" else "adjustment"
        if reason == "transfer":
            trans_type = "transfer_out"

        result = self.bank.remove_funds(
            owner_moniker,
            amount,
            transaction_type=trans_type,
            description=description or f"Table {table_moniker} withdrawal: {reason}",
            member_moniker=member_moniker,
        )

        if result["success"]:
            result["message"] = f"Removed {amount} from table {table_moniker} bank"
        
        return result

    def record_win(
        self,
        table_moniker: str,
        amount: int,
        player_moniker: str,
    ) -> Dict[str, Any]:
        """Record a player win (deduct from table bank)."""
        return self.remove_funds(
            table_moniker,
            amount,
            reason="win",
            member_moniker=player_moniker,
            description=f"Win paid to {player_moniker}",
        )

    def record_loss(
        self,
        table_moniker: str,
        amount: int,
        player_moniker: str,
    ) -> Dict[str, Any]:
        """Record a player loss (add to table bank)."""
        return self.add_funds(
            table_moniker,
            amount,
            source="player",
            member_moniker=player_moniker,
            description=f"Bet from {player_moniker}",
        )

    def get_max_transfer(self, table_moniker: str) -> int:
        """Get max transfer limit for a table."""
        table = self.get_table(table_moniker)
        if not table:
            return 1000
        return int(table.get("maxtransfer", 1000))

    def check_transfer_limit(self, table_moniker: str, amount: int) -> Dict[str, Any]:
        """Check if transfer amount is within limit."""
        max_transfer = self.get_max_transfer(table_moniker)
        if amount > max_transfer:
            return {
                "success": False,
                "message": f"Transfer amount {amount} exceeds limit of {max_transfer}",
            }
        return {"success": True}

    def request_transfer(
        self,
        from_table: str,
        to_table: str,
        amount: int,
        requested_by: str,
    ) -> Dict[str, Any]:
        """Request a transfer between tables (requires approval)."""
        if from_table == to_table:
            return {"success": False, "message": "Cannot transfer to the same table"}

        if amount <= 0:
            return {"success": False, "message": "Amount must be positive"}

        limit_check = self.check_transfer_limit(from_table, amount)
        if not limit_check["success"]:
            return limit_check

        source_table = dal_table.get_table(self.args, from_table)
        dest_table = dal_table.get_table(self.args, to_table)
        if not source_table or not dest_table:
            return {"success": False, "message": "Table not found"}

        if not source_table.get("accountid") or not dest_table.get("accountid"):
            return {"success": False, "message": "One or both tables have no bank account"}

        from_account_moniker = f"table:{from_table}"
        to_account_moniker = f"table:{to_table}"

        balance = self.get_balance(from_table)
        if balance < amount:
            return {"success": False, "message": f"Insufficient funds. Current balance: {balance}"}

        return self.bank.transfer(
            from_account_moniker,
            to_account_moniker,
            amount,
            requested_by,
        )

    def approve_transfer(self, transfer_id: int, responded_by: str) -> Dict[str, Any]:
        """Approve a pending transfer."""
        return self.bank.approve_transfer(transfer_id, responded_by)

    def reject_transfer(self, transfer_id: int, responded_by: str) -> Dict[str, Any]:
        """Reject a pending transfer."""
        return self.bank.reject_transfer(transfer_id, responded_by)

    def list_pending_transfers(self, moniker: str = "", is_sysop: bool = False) -> List[Dict[str, Any]]:
        """List pending transfers for tables owned by user."""
        return self.bank.get_pending_transfers(moniker, is_sysop)

    def get_history(self, table_moniker: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get transaction history for a table."""
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return []
        owner_moniker = table.get("ownermoniker")
        if not owner_moniker:
            return []
        return self.bank.get_history(owner_moniker, limit)

    def get_all_balances(self) -> List[Dict[str, Any]]:
        """Get all table balances (sysop only)."""
        tables = dal_table.list_tables(self.args)
        result = []
        for t in tables:
            owner_moniker = t.get("ownermoniker")
            if not owner_moniker:
                continue
            balance = self.bank.get_balance(owner_moniker)
            account = self.bank.account.get(owner_moniker)
            result.append({
                "moniker": t["moniker"],
                "owner": owner_moniker,
                "bank": balance,
                "max_transfer": int(account["maxtransfer"]) if account else 1000,
                "type": t["type"],
            })
        return result

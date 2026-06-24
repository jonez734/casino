# casino/services/bank.py
# Casino table bank management - uses bbsengine6 bank module

import logging
from typing import Any, Dict, List, Optional

from bbsengine6 import database
from bbsengine6.bank import BankService as BankModule
from casino.dal import table as dal_table

try:
    from bbsengine6.message_delivery import send as notify_send, NotificationUrgency
    HAS_NOTIFY = True
except ImportError:
    HAS_NOTIFY = False
    NotificationUrgency = None

logger = logging.getLogger(__name__)

HOUSE_MONIKER = "casino:house"
OVERDRAFT_WARNING_THRESHOLD = 0.8
NOTIFICATION_TYPE = "casino.bankalert"


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

    def _get_house_account_id(self) -> int:
        """Get or create the house bank account ID."""
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute("SELECT id FROM bank.__account WHERE moniker = %s", (HOUSE_MONIKER,))
                row = cur.fetchone()
                if row:
                    return row["id"]
                cur.execute(
                    "INSERT INTO bank.__account (moniker, balance, maxtransfer) VALUES (%s, 0, 1000000) RETURNING id",
                    (HOUSE_MONIKER,)
                )
                return cur.fetchone()["id"]

    def _get_house_balance(self) -> int:
        """Get house account balance."""
        account = self.bank.account.get(HOUSE_MONIKER)
        return int(account["balance"]) if account else 0

    def _transfer(
        self,
        from_moniker: str,
        to_moniker: str,
        amount: int,
        transaction_type: str,
        description: str,
        member_moniker: str = "",
    ) -> Dict[str, Any]:
        """Transfer funds between two accounts. Both accounts must exist."""
        if amount <= 0:
            return {"success": False, "message": "Amount must be positive"}

        from_account = self.bank.account.get(from_moniker)
        if not from_account:
            return {"success": False, "message": f"Source account '{from_moniker}' not found"}

        to_account = self.bank.account.get(to_moniker)
        if not to_account:
            return {"success": False, "message": f"Destination account '{to_moniker}' not found"}

        if from_moniker == HOUSE_MONIKER:
            check_result = self._check_house_balance(amount, transaction_type)
            if not check_result["allowed"]:
                return {"success": False, "message": check_result["message"]}
            if check_result["alert"]:
                self._alert_house_status(check_result["message"], urgency_level="high")
        else:
            if from_account["balance"] < amount:
                return {"success": False, "message": f"Insufficient funds. Balance: {from_account['balance']}"}

        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "UPDATE bank.__account SET balance = balance - %s WHERE moniker = %s",
                    (amount, from_moniker)
                )
                cur.execute(
                    "UPDATE bank.__account SET balance = balance + %s WHERE moniker = %s",
                    (amount, to_moniker)
                )
                cur.execute(
                    """INSERT INTO bank.__transaction (accountid, amount, transactiontype, description, membermoniker)
                       SELECT id, %s, %s, %s, %s FROM bank.__account WHERE moniker = %s""",
                    (amount, f"{transaction_type}_debit", description, member_moniker, from_moniker)
                )
                cur.execute(
                    """INSERT INTO bank.__transaction (accountid, amount, transactiontype, description, membermoniker)
                       SELECT id, %s, %s, %s, %s FROM bank.__account WHERE moniker = %s""",
                    (amount, f"{transaction_type}_credit", description, member_moniker, to_moniker)
                )

        return {
            "success": True,
            "message": f"Transferred {amount} from {from_moniker} to {to_moniker}",
            "from_balance": from_account["balance"] - amount,
            "to_balance": to_account["balance"] + amount,
        }

    def _record_transaction(
        self,
        table_moniker: str,
        amount: int,
        transaction_type: str,
        source: str,
        destination: str,
        member_moniker: str,
        description: str,
    ) -> None:
        """Record a casino bank transaction."""
        with database.connect(self.args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    """INSERT INTO casino.__banktransaction 
                       (tablemoniker, amount, transactiontype, source, destination, relatedmoniker, description, membermoniker)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (table_moniker, amount, transaction_type, source, destination, member_moniker, description, member_moniker)
                )

    def _get_house_settings(self) -> Dict[str, Any]:
        """Get house account settings including overdraft limit."""
        account = self.bank.account.get(HOUSE_MONIKER)
        if not account:
            return {"overdraft_limit": 0, "balance": 0}
        return {
            "balance": account["balance"],
            "overdraft_limit": account.get("overdraft_limit", 0),
        }

    def get_house_balance_with_status(self) -> Dict[str, Any]:
        """Get house balance with status information."""
        settings = self._get_house_settings()
        balance = settings["balance"]
        overdraft_limit = settings["overdraft_limit"]

        if balance >= 0:
            status = "positive"
        elif balance >= -overdraft_limit * OVERDRAFT_WARNING_THRESHOLD:
            status = "warning"
        elif balance >= -overdraft_limit:
            status = "critical"
        else:
            status = "blocked"

        return {
            "balance": balance,
            "overdraft_limit": overdraft_limit,
            "available": balance + overdraft_limit,
            "status": status,
        }

    def _check_house_balance(self, amount: int, operation: str) -> Dict[str, Any]:
        """Check if house can afford a transaction.
        
        Returns dict with:
            allowed: bool - whether transaction can proceed
            new_balance: int - balance after transaction
            alert: bool - whether to send alert
            message: str - status message
        """
        settings = self._get_house_settings()
        current_balance = settings["balance"]
        overdraft_limit = settings["overdraft_limit"]
        new_balance = current_balance - amount

        if new_balance < -overdraft_limit:
            return {
                "allowed": False,
                "new_balance": new_balance,
                "alert": True,
                "message": f"House overdraft limit reached. Limit: {overdraft_limit}, Required: {amount}, Current: {current_balance}",
            }

        if new_balance < -overdraft_limit * OVERDRAFT_WARNING_THRESHOLD:
            return {
                "allowed": True,
                "new_balance": new_balance,
                "alert": True,
                "message": f"House balance warning: {new_balance} (limit: {overdraft_limit})",
            }

        return {
            "allowed": True,
            "new_balance": new_balance,
            "alert": False,
            "message": "OK",
        }

    def _alert_house_status(self, message: str, urgency_level: str = "routine") -> None:
        """Send notification to sysop about house account status."""
        if not HAS_NOTIFY:
            logger.warning(f"House alert (notify unavailable): {message}")
            return

        urgency_map = {
            "routine": NotificationUrgency.ROUTINE if NotificationUrgency else None,
            "important": NotificationUrgency.IMPORTANT if NotificationUrgency else None,
            "high": NotificationUrgency.URGENT if NotificationUrgency else None,
            "critical": NotificationUrgency.CRITICAL if NotificationUrgency else None,
        }
        urgency = urgency_map.get(urgency_level, NotificationUrgency.ROUTINE if NotificationUrgency else None)

        try:
            notify_send(
                notification_type=NOTIFICATION_TYPE,
                recipients=["sysop"],
                template="house_alert",
                template_vars={"message": message},
                sender_moniker="casino",
                urgency=urgency,
                args=self.args,
            )
        except Exception as e:
            logger.error(f"Failed to send house alert notification: {e}")

    def _ensure_house_notification_type(self) -> None:
        """Ensure the casino.bankalert notification type exists."""
        if not HAS_NOTIFY:
            return
        
        try:
            from bbsengine6.message_delivery import register_type
            register_type(
                NOTIFICATION_TYPE,
                NotificationUrgency.ROUTINE if NotificationUrgency else None,
                100,
                True,
                self.args,
            )
        except Exception as e:
            logger.debug(f"Could not ensure notification type: {e}")

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
        """Add funds to a table bank (buy-in, house funding, transfer_in)."""
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

        if source == "player":
            if not member_moniker:
                return {"success": False, "message": "Player moniker required for player buy-in"}
            result = self._transfer(
                member_moniker,
                owner_moniker,
                amount,
                "buyin",
                f"Table {table_moniker} buy-in",
                member_moniker,
            )
            self._record_transaction(
                table_moniker, amount, "buyin", "player", "table", member_moniker,
                description or f"Buy-in from {member_moniker}"
            )
        elif source == "house":
            result = self._transfer(
                HOUSE_MONIKER,
                owner_moniker,
                amount,
                "house_funding",
                f"Table {table_moniker} funded by house",
                member_moniker or "system",
            )
            self._record_transaction(
                table_moniker, amount, "adjustment", "house", "table", member_moniker or "system",
                description or f"House funding for {table_moniker}"
            )
        else:
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
        """Remove funds from a table bank (payout, transfer_out, house withdrawal)."""
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

        if reason == "payout":
            result = self._transfer(
                owner_moniker,
                HOUSE_MONIKER,
                amount,
                "payout",
                f"Table {table_moniker} payout to house",
                member_moniker or "system",
            )
            self._record_transaction(
                table_moniker, amount, "payout", "table", "house", member_moniker or "system",
                description or f"Payout from {table_moniker}"
            )
        elif reason == "house_withdrawal":
            result = self._transfer(
                owner_moniker,
                HOUSE_MONIKER,
                amount,
                "house_withdrawal",
                f"Table {table_moniker} returns float to house",
                member_moniker or "system",
            )
            self._record_transaction(
                table_moniker, amount, "adjustment", "table", "house", member_moniker or "system",
                description or f"Float returned from {table_moniker}"
            )
        else:
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
        """Record a player win (pay from house account to player)."""
        if amount <= 0:
            return {"success": False, "message": "Amount must be positive"}

        result = self._transfer(
            HOUSE_MONIKER,
            player_moniker,
            amount,
            "win",
            f"Win paid to {player_moniker} at {table_moniker}",
            player_moniker,
        )
        self._record_transaction(
            table_moniker, amount, "win", "house", "player", player_moniker,
            f"Win paid to {player_moniker}"
        )

        if result["success"]:
            result["message"] = f"Paid {amount} to {player_moniker}"
        
        return result

    def record_loss(
        self,
        table_moniker: str,
        amount: int,
        player_moniker: str,
    ) -> Dict[str, Any]:
        """Record a player loss (debit player, credit house)."""
        if amount <= 0:
            return {"success": False, "message": "Amount must be positive"}

        result = self._transfer(
            player_moniker,
            HOUSE_MONIKER,
            amount,
            "loss",
            f"Bet from {player_moniker} at {table_moniker}",
            player_moniker,
        )
        self._record_transaction(
            table_moniker, amount, "loss", "player", "house", player_moniker,
            f"Bet from {player_moniker}"
        )

        if result["success"]:
            result["message"] = f"House won {amount} from {player_moniker}"
        
        return result

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

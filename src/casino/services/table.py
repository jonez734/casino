# casino/services/table.py
# Table service - table management

from typing import Any, Dict, List, Optional

from casino.dal import table as dal_table


class TableService:
    """Service for table management."""

    def __init__(self, args: Any):
        self.args = args

    def create_table(
        self,
        game_type: str,
        owner_moniker: str,
        min_bet: int = 10,
        max_bet: int = 1000,
        moniker: Optional[str] = None,
        hidden: bool = False,
    ) -> Dict[str, Any]:
        """Create a new casino table.

        Args:
            hidden: If True, table is hidden from list_tables for non-sysop users.
        """
        table = dal_table.create_table(
            self.args, game_type, owner_moniker, min_bet, max_bet, moniker, hidden=hidden
        )
        if table is None:
            return {
                "success": False,
                "message": "Failed to create table",
            }
        return {
            "success": True,
            "table": table,
            "message": f"Table {table['moniker']} created",
        }

    def get_table(self, moniker: str) -> Optional[Dict[str, Any]]:
        """Get table by moniker."""
        return dal_table.get_table(self.args, moniker)

    def list_tables(
        self,
        game_type: Optional[str] = None,
        is_sysop: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all tables, optionally filtered by game type.

        Hidden tables are excluded unless the caller is a sysop (sysops
        always see every table so they can be discovered and managed).
        """
        tables = dal_table.list_tables(
            self.args, game_type, include_hidden=is_sysop
        )

        result = []
        for table in tables:
            players = dal_table.get_table_players(self.args, table["moniker"])
            spectators = dal_table.get_table_spectators(self.args, table["moniker"])
            result.append({
                "moniker": table["moniker"],
                "game_type": table["type"],
                "min_bet": table["minimumbet"],
                "max_bet": table["maximumbet"],
                "owner": table["ownermoniker"],
                "players": players,
                "spectators": spectators,
                "phase": "waiting",
                "status": table.get("status", "open"),
                "hidden": bool(table.get("hidden", False)),
            })
        return result

    def join_table(
        self,
        moniker: str,
        player_moniker: str = "",
        is_sysop: bool = False,
    ) -> Dict[str, Any]:
        """Player joins a table (sits down).

        Hidden tables are not discoverable via list_tables for non-sysop
        users; however if a user knows the exact moniker they can still
        join. Sysops can join any table (including hidden) without
        approval.
        """
        table = dal_table.get_table(self.args, moniker)
        if not table:
            return {
                "success": False,
                "message": "Table not found",
            }

        dal_table.add_player_to_table(self.args, moniker, player_moniker)

        return {
            "success": True,
            "moniker": moniker,
            "message": f"Sat down at table {moniker}",
        }

    def leave_table(self, moniker: str, player_moniker: str) -> Dict[str, Any]:
        """Player leaves a table (stands up)."""
        success = dal_table.remove_player_from_table(self.args, moniker, player_moniker)

        return {
            "success": success,
            "message": "Left table" if success else "Not at table",
        }

    def delete_table(self, moniker: str, current_moniker: str, is_sysop: bool = False) -> Dict[str, Any]:
        """Delete a table (owner or sysop)."""
        table = dal_table.get_table(self.args, moniker)
        if not table:
            return {
                "success": False,
                "message": "Table not found",
            }

        if table["ownermoniker"] != current_moniker and not is_sysop:
            return {
                "success": False,
                "message": "Only the owner or sysop can delete this table",
            }

        dal_table.delete_table(self.args, moniker)

        return {
            "success": True,
            "message": f"Table {moniker} deleted",
        }

    def update_table(self, moniker: str, current_moniker: str, is_sysop: bool = False, **updates) -> Dict[str, Any]:
        """Update table fields (owner or sysop only).

        Args:
            moniker: Table moniker
            current_moniker: Current user moniker
            is_sysop: Whether current user is sysop
            **updates: Fields to update (new_moniker, minimumbet, maximumbet, status, hidden)
        """
        table = dal_table.get_table(self.args, moniker)
        if not table:
            return {
                "success": False,
                "message": "Table not found",
            }

        if table["ownermoniker"] != current_moniker and not is_sysop:
            return {
                "success": False,
                "message": "Only the owner or sysop can edit this table",
            }

        if "status" in updates and updates["status"] not in ("open", "closed"):
            return {
                "success": False,
                "message": "Status must be 'open' or 'closed'",
            }

        if "hidden" in updates and not isinstance(updates["hidden"], bool):
            return {
                "success": False,
                "message": "hidden must be a boolean",
            }

        updated = dal_table.update_table(self.args, moniker, **updates)
        if updated:
            return {
                "success": True,
                "message": f"Table {moniker} updated",
                "table": updated,
            }
        return {
            "success": False,
            "message": "Failed to update table",
        }

    def reset_shoe(self, moniker: str, current_moniker: str, is_sysop: bool = False) -> Dict[str, Any]:
        """Reset table shoe (owner or sysop only)."""
        table = dal_table.get_table(self.args, moniker)
        if not table:
            return {
                "success": False,
                "message": "Table not found",
            }

        if table["ownermoniker"] != current_moniker and not is_sysop:
            return {
                "success": False,
                "message": "Only the owner or sysop can reset the shoe",
            }

        dal_table.reset_shoe(self.args, moniker)

        return {
            "success": True,
            "message": f"Shoe for table {moniker} has been reset",
        }

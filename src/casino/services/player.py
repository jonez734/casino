# casino/services/player.py
# Player service - authentication and profile management

from typing import Any, Dict, Optional

from bbsengine6 import database, member

from casino.dal import player as dal_player


class PlayerService:
    """Service for player authentication and management."""
    
    def __init__(self, args: Any):
        self.args = args
    
    def _pool(self) -> Any:
        """Return the connection pool to use for member credential checks.

        bbsengine6.member requires the caller to own the pool
        (CONN_POOL_PATTERN). bed puts a pool on ``args.pool`` at startup;
        reuse it when present, otherwise fall back to the cached
        ``database.getpool``.
        """
        pool = getattr(self.args, "pool", None)
        if pool is not None:
            return pool
        return database.getpool(self.args, database=self.args.databasename)
    
    def authenticate(self, moniker: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a player via BBS member credentials.
        
        Returns:
            Dict with success, moniker, balance, message
        """
        pool = self._pool()
        # Verify member exists
        if not member.verifyMemberFound(
            self.args, moniker, column="moniker", pool=pool
        ):
            return {
                "success": False,
                "moniker": "",
                "balance": 0,
                "message": "Member not found",
            }
        
        # Check if member has a password set
        has_pwd = member.has_password(self.args, moniker, pool=pool)
        
        # If member has a password, verify it
        if has_pwd:
            result = member.checkpassword(self.args, password, moniker, pool=pool)
            if result is None or result is False:
                return {
                    "success": False,
                    "moniker": moniker,
                    "balance": 0,
                    "message": "Invalid password",
                }
        
        # Get or create casino player record
        dal_player.get_or_create_player(self.args, moniker)
        
        # Get balance
        balance = dal_player.get_player_balance(self.args, moniker)
        
        return {
            "success": True,
            "moniker": moniker,
            "balance": balance,
            "message": "Authentication successful",
        }
    
    def get_balance(self, moniker: str) -> int:
        """Get player's current balance."""
        return dal_player.get_player_balance(self.args, moniker)
    
    def update_lastplayed(self, moniker: str) -> None:
        """Update player's last played timestamp."""
        dal_player.update_player_lastplayed(self.args, moniker)
    
    def get_profile(self, moniker: str) -> Optional[Dict[str, Any]]:
        """Get player profile."""
        return dal_player.get_player_by_moniker(self.args, moniker)

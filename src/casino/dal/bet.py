# casino/dal/bet.py
# Bet data access layer

from typing import Any, Dict, List

from bbsengine6 import database


def place_bet(
    args: Any,
    player_moniker: str,
    table_moniker: str,
    game_id: int,
    amount: int,
) -> Dict[str, Any]:
    """
    Place a bet and deduct from player's balance.
    
    Args:
        args: Application args
        player_moniker: Player's BBS moniker
        table_moniker: Table moniker
        game_id: Game ID
        amount: Bet amount
        
    Returns:
        Bet dict with id, amount, etc.
    """
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT credits FROM $engine.__member WHERE moniker = :player_moniker",
                    player_moniker=player_moniker
                )
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Player not found")
            
            balance = int(row["credits"])
            if balance < amount:
                raise ValueError("Insufficient funds")
            
            cur.execute(
                database.query(
                    "UPDATE $engine.__member SET credits = credits - :amount WHERE moniker = :player_moniker",
                    amount=amount, player_moniker=player_moniker
                )
            )
            
            cur.execute(
                database.query(
                    "INSERT INTO $casino.__betlog (membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted) VALUES (:player_moniker, :table_moniker, :game_id, :player_moniker2, :amount, 'pending', NOW()) RETURNING id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted",
                    player_moniker=player_moniker, table_moniker=table_moniker, game_id=game_id, player_moniker2=player_moniker, amount=amount
                )
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "membermoniker": row["membermoniker"],
                "cardtablemoniker": row["cardtablemoniker"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "amount": row["amount"],
                "status": row["status"],
                "dateposted": row["dateposted"],
            }


def settle_bet(
    args: Any,
    bet_id: int,
    won: bool,
    payout: int,
) -> None:
    """
    Settle a bet (win or loss).
    
    Args:
        bet_id: Bet ID
        won: Whether player won
        payout: Amount to pay out (including original bet for wins)
    """
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT playermoniker, amount FROM $casino.__betlog WHERE id = :bet_id",
                    bet_id=bet_id
                )
            )
            row = cur.fetchone()
            if not row:
                return
            
            player_moniker = row["playermoniker"]
            
            status = "won" if won else "lost"
            cur.execute(
                database.query(
                    "UPDATE $casino.__betlog SET status = :status WHERE id = :bet_id",
                    status=status, bet_id=bet_id
                )
            )
            
            if won and payout > 0:
                cur.execute(
                    database.query(
                        "UPDATE $engine.__member SET credits = credits + :payout WHERE moniker = :player_moniker",
                        payout=payout, player_moniker=player_moniker
                    )
                )


def get_player_bets(args: Any, player_moniker: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get player's recent bets."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted FROM $casino.__betlog WHERE playermoniker = :player_moniker ORDER BY dateposted DESC LIMIT :limit",
                    player_moniker=player_moniker, limit=limit
                )
            )
            bets = []
            for row in cur:
                bets.append({
                    "id": row["id"],
                    "membermoniker": row["membermoniker"],
                    "cardtablemoniker": row["cardtablemoniker"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "amount": row["amount"],
                    "status": row["status"],
                    "dateposted": row["dateposted"],
                })
            return bets


def get_table_bets(args: Any, game_id: int) -> List[Dict[str, Any]]:
    """Get all bets for a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted FROM $casino.__betlog WHERE gameid = :game_id ORDER BY dateposted",
                    game_id=game_id
                )
            )
            bets = []
            for row in cur:
                bets.append({
                    "id": row["id"],
                    "membermoniker": row["membermoniker"],
                    "cardtablemoniker": row["cardtablemoniker"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "amount": row["amount"],
                    "status": row["status"],
                    "dateposted": row["dateposted"],
                })
            return bets

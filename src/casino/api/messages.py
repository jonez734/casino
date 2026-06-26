# casino/api/messages.py
# WebSocket message types for casino API
#
# All messages are JSON objects with a "type" field.
# Client->Server messages are requests, Server->Client are responses.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class MessageType(str, Enum):
    # Authentication
    AUTH = "auth"
    AUTH_RESULT = "auth_result"
    LOGOUT = "logout"

    # Table management
    LIST_TABLES = "list_tables"
    TABLE_LIST = "table_list"
    CREATE_TABLE = "create_table"
    TABLE_CREATED = "table_created"
    UPDATE_TABLE = "update_table"
    TABLE_UPDATED = "table_updated"
    JOIN_TABLE = "join_table"
    LEAVE_TABLE = "leave_table"
    WATCH_TABLE = "watch_table"
    STOP_WATCHING = "stop_watching"

    # Gameplay
    BET = "bet"
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"
    GAME_STATE = "game_state"

    # Yahtzee
    YAHTZEE_QUICK_PLAY = "yahtzee_quick_play"
    YAHTZEE_ROLL = "yahtzee_roll"
    YAHTZEE_REROLL = "yahtzee_reroll"
    YAHTZEE_SCORE = "yahtzee_score"
    YAHTZEE_STATE = "yahtzee_state"
    YAHTZEE_RESULT = "yahtzee_result"

    # Chat
    CHAT_TABLE = "chat_table"
    CHAT_GLOBAL = "chat_global"
    EMOTE = "emote"
    CHAT_MESSAGE = "chat_message"

    # System
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


class GamePhase(str, Enum):
    WAITING = "waiting"
    BETTING = "betting"
    DEALING = "dealing"
    PLAYING = "playing"
    SETTLING = "settling"
    CLOSED = "closed"


class GameType(str, Enum):
    BLACKJACK = "blackjack"
    POKER = "poker"
    SLOTS = "slots"
    YAHTZEE = "yahtzee"


class ChatScope(str, Enum):
    TABLE = "table"
    GLOBAL = "global"


class ErrorCode(str, Enum):
    NOT_AUTHENTICATED = "not_authenticated"
    INVALID_CREDENTIALS = "invalid_credentials"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    TABLE_NOT_FOUND = "table_not_found"
    TABLE_FULL = "table_full"
    INVALID_BET = "invalid_bet"
    NOT_YOUR_TURN = "not_your_turn"
    GAME_ERROR = "game_error"
    ALREADY_SITTING = "already_sitting"
    NOT_SITTING = "not_sitting"
    INVALID_ACTION = "invalid_action"


# =============================================================================
# Client -> Server Messages
# =============================================================================


@dataclass
class AuthMessage:
    type: str = MessageType.AUTH
    moniker: str = ""
    password: str = ""


@dataclass
class LogoutMessage:
    type: str = MessageType.LOGOUT


@dataclass
class ListTablesMessage:
    type: str = MessageType.LIST_TABLES


@dataclass
class CreateTableMessage:
    type: str = MessageType.CREATE_TABLE
    game_type: str = GameType.BLACKJACK
    min_bet: int = 10
    max_bet: int = 1000
    moniker: str = ""


@dataclass
class UpdateTableMessage:
    type: str = MessageType.UPDATE_TABLE
    moniker: str = ""
    new_moniker: Optional[str] = None
    min_bet: Optional[int] = None
    max_bet: Optional[int] = None
    status: Optional[str] = None


@dataclass
class JoinTableMessage:
    type: str = MessageType.JOIN_TABLE
    moniker: str = ""


@dataclass
class LeaveTableMessage:
    type: str = MessageType.LEAVE_TABLE
    moniker: Optional[str] = None


@dataclass
class WatchTableMessage:
    type: str = MessageType.WATCH_TABLE
    moniker: str = ""


@dataclass
class StopWatchingMessage:
    type: str = MessageType.STOP_WATCHING
    table_id: Optional[int] = None


@dataclass
class BetMessage:
    type: str = MessageType.BET
    amount: int = 0


@dataclass
class HitMessage:
    type: str = MessageType.HIT


@dataclass
class StandMessage:
    type: str = MessageType.STAND


@dataclass
class DoubleMessage:
    type: str = MessageType.DOUBLE


@dataclass
class SplitMessage:
    type: str = MessageType.SPLIT


@dataclass
class ChatTableMessage:
    type: str = MessageType.CHAT_TABLE
    table_id: int = 0
    message: str = ""


@dataclass
class ChatGlobalMessage:
    type: str = MessageType.CHAT_GLOBAL
    message: str = ""


@dataclass
class EmoteMessage:
    type: str = MessageType.EMOTE
    message: str = ""


@dataclass
class PingMessage:
    type: str = MessageType.PING


# =============================================================================
# Server -> Client Messages
# =============================================================================


@dataclass
class AuthResultMessage:
    type: str = MessageType.AUTH_RESULT
    success: bool = False
    player_id: Optional[int] = None
    moniker: str = ""
    balance: int = 0
    message: str = ""


@dataclass
class TableInfo:
    moniker: str
    game_type: str
    min_bet: int
    max_bet: int
    players: list[str] = field(default_factory=list)
    spectators: list[str] = field(default_factory=list)
    owner: str = ""
    phase: str = GamePhase.WAITING


@dataclass
class TableListMessage:
    type: str = MessageType.TABLE_LIST
    tables: list[TableInfo] = field(default_factory=list)


@dataclass
class TableUpdatedMessage:
    type: str = MessageType.TABLE_UPDATED
    moniker: str = ""
    message: str = ""


@dataclass
class CardInfo:
    pips: str
    suit: str
    facedown: bool = False
    value: int = 0


@dataclass
class HandInfo:
    player_moniker: str
    cards: list[CardInfo] = field(default_factory=list)
    bet: int = 0
    total: int = 0
    status: str = "playing"
    is_split: bool = False


@dataclass
class GameStateMessage:
    type: str = MessageType.GAME_STATE
    table_id: int = 0
    phase: str = GamePhase.WAITING
    dealer_hand: list[CardInfo] = field(default_factory=list)
    dealer_total: int = 0
    hands: list[HandInfo] = field(default_factory=list)
    current_player: str = ""
    pots: list[int] = field(default_factory=list)


@dataclass
class ChatMessageMessage:
    type: str = MessageType.CHAT_MESSAGE
    from_moniker: str = ""
    message: str = ""
    scope: str = ChatScope.GLOBAL
    table_id: Optional[int] = None
    timestamp: str = ""


@dataclass
class PongMessage:
    type: str = MessageType.PONG
    timestamp: str = ""


@dataclass
class ErrorMessage:
    type: str = MessageType.ERROR
    code: str = ErrorCode.GAME_ERROR
    message: str = ""


# =============================================================================
# Message Parsing
# =============================================================================


def parse_message(data: dict[str, Any]) -> dict[str, Any]:
    """Parse incoming JSON message, returning a standardized dict."""
    if not isinstance(data, dict):
        raise ValueError("Message must be a JSON object")
    
    msg_type = data.get("type")
    if not msg_type:
        raise ValueError("Message must have a 'type' field")
    
    return data


def create_message(msg_type: MessageType, **kwargs) -> dict[str, Any]:
    """Create a message dict with type and fields."""
    msg = {"type": msg_type.value}
    msg.update(kwargs)
    return msg


def error_message(code: ErrorCode, message: str) -> dict[str, Any]:
    return {
        "type": MessageType.ERROR.value,
        "code": code.value,
        "message": message,
    }


def pong_message() -> dict[str, Any]:
    return {
        "type": MessageType.PONG.value,
        "timestamp": datetime.utcnow().isoformat(),
    }

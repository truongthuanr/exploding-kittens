"""Room domain module."""

from app.modules.room.errors import (
    DuplicateNicknameError,
    DuplicateRoomCodeError,
    NotHostError,
    PlayerNotInRoomError,
    RoomNotFoundError,
    RoomNotJoinableError,
    RoomNotWaitingError,
)
from app.modules.room.mappers import to_room_updated_event
from app.modules.room.models import RoomPlayerState, RoomState
from app.modules.room.registry import RoomRegistry
from app.modules.room.service import RoomOperationResult, RoomService

__all__ = [
    "DuplicateNicknameError",
    "DuplicateRoomCodeError",
    "NotHostError",
    "PlayerNotInRoomError",
    "RoomNotFoundError",
    "RoomNotJoinableError",
    "RoomNotWaitingError",
    "RoomOperationResult",
    "RoomPlayerState",
    "RoomRegistry",
    "RoomService",
    "RoomState",
    "to_room_updated_event",
]

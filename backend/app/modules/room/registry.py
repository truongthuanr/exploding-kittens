from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.room.errors import DuplicateRoomCodeError, RoomNotFoundError
from app.modules.room.models import RoomState


@dataclass(slots=True)
class RoomRegistry:
    rooms_by_id: dict[str, RoomState] = field(default_factory=dict)
    room_id_by_code: dict[str, str] = field(default_factory=dict)

    def add(self, room: RoomState) -> None:
        if room.room_code in self.room_id_by_code:
            raise DuplicateRoomCodeError(room.room_code)

        self.rooms_by_id[room.room_id] = room
        self.room_id_by_code[room.room_code] = room.room_id

    def get_by_id(self, room_id: str) -> RoomState:
        room = self.rooms_by_id.get(room_id)
        if room is None:
            raise RoomNotFoundError(room_id)
        return room

    def get_by_code(self, room_code: str) -> RoomState:
        room_id = self.room_id_by_code.get(room_code)
        if room_id is None:
            raise RoomNotFoundError(room_code)
        return self.get_by_id(room_id)

    def remove(self, room_id: str) -> RoomState:
        room = self.get_by_id(room_id)
        del self.rooms_by_id[room_id]
        del self.room_id_by_code[room.room_code]
        return room

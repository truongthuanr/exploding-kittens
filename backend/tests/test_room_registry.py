import pytest

from app.modules.room.errors import DuplicateRoomCodeError, RoomNotFoundError
from app.modules.room.models import RoomPlayerState, RoomState
from app.modules.room.registry import RoomRegistry


def build_room(*, room_id: str = "room-1", room_code: str = "ABCD12") -> RoomState:
    host = RoomPlayerState(player_id="player-1", nickname="alice")
    return RoomState(
        room_id=room_id,
        room_code=room_code,
        host_player_id=host.player_id,
        players=[host],
    )


def test_registry_adds_and_looks_up_room_by_id_and_code() -> None:
    room = build_room()
    registry = RoomRegistry()

    registry.add(room)

    assert registry.get_by_id("room-1") is room
    assert registry.get_by_code("ABCD12") is room


def test_registry_rejects_duplicate_room_code() -> None:
    registry = RoomRegistry()
    registry.add(build_room(room_id="room-1", room_code="ABCD12"))

    with pytest.raises(DuplicateRoomCodeError):
        registry.add(build_room(room_id="room-2", room_code="ABCD12"))


def test_registry_remove_cleans_both_indexes() -> None:
    room = build_room()
    registry = RoomRegistry()
    registry.add(room)

    removed = registry.remove(room.room_id)

    assert removed is room
    with pytest.raises(RoomNotFoundError):
        registry.get_by_id(room.room_id)
    with pytest.raises(RoomNotFoundError):
        registry.get_by_code(room.room_code)

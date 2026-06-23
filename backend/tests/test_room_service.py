import pytest

from app.modules.room.errors import (
    DuplicateNicknameError,
    PlayerNotInRoomError,
    RoomNotJoinableError,
    RoomNotWaitingError,
)
from app.modules.room.registry import RoomRegistry
from app.modules.room.service import RoomService
from app.schemas.enums import RoomStatus


class StubRoomService(RoomService):
    def __init__(self) -> None:
        super().__init__(registry=RoomRegistry())
        self._player_ids = iter(["player-1", "player-2", "player-3"])
        self._room_ids = iter(["room-1"])
        self._room_codes = iter(["ABCD12"])

    def _generate_player_id(self) -> str:
        return next(self._player_ids)

    def _generate_room_id(self) -> str:
        return next(self._room_ids)

    def _generate_unique_room_code(self) -> str:
        return next(self._room_codes)


def test_create_room_creates_host_and_stores_room() -> None:
    service = StubRoomService()

    result = service.create_room("alice")

    assert result.room.room_id == "room-1"
    assert result.room.room_code == "ABCD12"
    assert result.room.host_player_id == "player-1"
    assert result.player.player_id == "player-1"
    assert result.player.nickname == "alice"
    assert service.registry.get_by_id("room-1") is result.room


def test_join_room_adds_player_to_waiting_room() -> None:
    service = StubRoomService()
    created = service.create_room("alice")

    joined = service.join_room(created.room.room_code.lower(), "bob")

    assert joined.room is created.room
    assert joined.player.player_id == "player-2"
    assert [player.nickname for player in created.room.players] == ["alice", "bob"]


def test_join_room_rejects_duplicate_nickname() -> None:
    service = StubRoomService()
    created = service.create_room("alice")

    with pytest.raises(DuplicateNicknameError):
        service.join_room(created.room.room_code, "alice")


def test_join_room_rejects_room_that_is_not_joinable() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    created.room.status = RoomStatus.STARTING

    with pytest.raises(RoomNotJoinableError):
        service.join_room(created.room.room_code, "bob")


def test_set_ready_updates_player_state() -> None:
    service = StubRoomService()
    created = service.create_room("alice")

    updated_room = service.set_ready(created.room.room_id, created.player.player_id, True)

    assert updated_room.get_player(created.player.player_id).is_ready is True


def test_set_ready_rejects_non_waiting_room() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    created.room.status = RoomStatus.IN_GAME

    with pytest.raises(RoomNotWaitingError):
        service.set_ready(created.room.room_id, created.player.player_id, True)


def test_set_ready_rejects_player_not_in_room() -> None:
    service = StubRoomService()
    created = service.create_room("alice")

    with pytest.raises(PlayerNotInRoomError):
        service.set_ready(created.room.room_id, "missing-player", True)

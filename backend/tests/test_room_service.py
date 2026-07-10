import pytest

from app.modules.room.errors import (
    DuplicateNicknameError,
    NotEnoughPlayersError,
    NotHostError,
    PlayerNotInRoomError,
    PlayersDisconnectedError,
    PlayersNotReadyError,
    RoomFullError,
    RoomNotJoinableError,
    RoomNotWaitingError,
)
from app.modules.room.mappers import to_room_updated_event
from app.modules.room.registry import RoomRegistry
from app.modules.room.service import RoomService
from app.schemas.enums import PlayerStatus, RoomStatus


class StubRoomService(RoomService):
    def __init__(self) -> None:
        super().__init__(registry=RoomRegistry())
        self._player_ids = iter(["player-1", "player-2", "player-3", "player-4", "player-5", "player-6"])
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


def test_join_room_rejects_room_that_is_full() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    service.join_room(created.room.room_code, "bob")
    service.join_room(created.room.room_code, "charlie")
    service.join_room(created.room.room_code, "dora")
    service.join_room(created.room.room_code, "eve")

    with pytest.raises(RoomFullError):
        service.join_room(created.room.room_code, "frank")


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


def test_validate_start_preconditions_accepts_ready_connected_host() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined_one = service.join_room(created.room.room_code, "bob")
    joined_two = service.join_room(created.room.room_code, "charlie")
    created.player.is_ready = True
    joined_one.player.is_ready = True
    joined_two.player.is_ready = True

    validated_room = service.validate_start_preconditions(created.room.room_id, created.player.player_id)

    assert validated_room is created.room


def test_validate_start_preconditions_rejects_non_host() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined_one = service.join_room(created.room.room_code, "bob")
    joined_two = service.join_room(created.room.room_code, "charlie")
    created.player.is_ready = True
    joined_one.player.is_ready = True
    joined_two.player.is_ready = True

    with pytest.raises(NotHostError):
        service.validate_start_preconditions(created.room.room_id, joined_one.player.player_id)


def test_validate_start_preconditions_rejects_not_enough_players() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined = service.join_room(created.room.room_code, "bob")
    created.player.is_ready = True
    joined.player.is_ready = True

    with pytest.raises(NotEnoughPlayersError):
        service.validate_start_preconditions(created.room.room_id, created.player.player_id)


def test_validate_start_preconditions_rejects_unready_player() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined_one = service.join_room(created.room.room_code, "bob")
    service.join_room(created.room.room_code, "charlie")
    created.player.is_ready = True
    joined_one.player.is_ready = True

    with pytest.raises(PlayersNotReadyError):
        service.validate_start_preconditions(created.room.room_id, created.player.player_id)


def test_validate_start_preconditions_rejects_disconnected_player() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined_one = service.join_room(created.room.room_code, "bob")
    joined_two = service.join_room(created.room.room_code, "charlie")
    created.player.is_ready = True
    joined_one.player.is_ready = True
    joined_two.player.is_ready = True
    joined_two.player.status = PlayerStatus.DISCONNECTED

    with pytest.raises(PlayersDisconnectedError):
        service.validate_start_preconditions(created.room.room_id, created.player.player_id)


def test_transition_to_starting_updates_room_status() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined_one = service.join_room(created.room.room_code, "bob")
    joined_two = service.join_room(created.room.room_code, "charlie")
    created.player.is_ready = True
    joined_one.player.is_ready = True
    joined_two.player.is_ready = True

    updated_room = service.transition_to_starting(created.room.room_id, created.player.player_id)

    assert updated_room is created.room
    assert updated_room.status == RoomStatus.STARTING


def test_transition_to_starting_rejects_non_waiting_room() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined_one = service.join_room(created.room.room_code, "bob")
    joined_two = service.join_room(created.room.room_code, "charlie")
    created.player.is_ready = True
    joined_one.player.is_ready = True
    joined_two.player.is_ready = True
    created.room.status = RoomStatus.STARTING

    with pytest.raises(RoomNotWaitingError):
        service.transition_to_starting(created.room.room_id, created.player.player_id)


def test_mapper_converts_room_state_to_room_updated_event() -> None:
    service = StubRoomService()
    created = service.create_room("alice")
    joined = service.join_room(created.room.room_code, "bob")
    created.player.is_ready = True
    joined.player.status = PlayerStatus.DISCONNECTED

    payload = to_room_updated_event(created.room)

    assert payload.roomId == "room-1"
    assert payload.roomCode == "ABCD12"
    assert payload.status == RoomStatus.WAITING
    assert [player.model_dump() for player in payload.players] == [
        {
            "playerId": "player-1",
            "nickname": "alice",
            "isReady": True,
            "isHost": True,
            "status": PlayerStatus.CONNECTED,
        },
        {
            "playerId": "player-2",
            "nickname": "bob",
            "isReady": False,
            "isHost": False,
            "status": PlayerStatus.DISCONNECTED,
        },
    ]

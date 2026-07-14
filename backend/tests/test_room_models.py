from app.modules.room.models import RoomPlayerState, RoomState
from app.schemas.enums import RoomStatus


def test_room_state_player_helpers_work() -> None:
    host = RoomPlayerState(player_id="player-1", nickname="alice")
    guest = RoomPlayerState(player_id="player-2", nickname="bob", is_ready=True)
    room = RoomState(
        room_id="room-1",
        room_code="ABCD12",
        host_player_id=host.player_id,
        players=[host, guest],
    )

    assert room.get_player("player-1") is host
    assert room.get_player("missing") is None
    assert room.has_nickname("alice") is True
    assert room.has_nickname("carol") is False
    assert room.is_joinable() is True
    assert room.is_host_player("player-1") is True
    assert room.is_host_player("player-2") is False


def test_room_state_not_joinable_when_not_waiting() -> None:
    room = RoomState(
        room_id="room-1",
        room_code="ABCD12",
        host_player_id="player-1",
        players=[RoomPlayerState(player_id="player-1", nickname="alice")],
        status=RoomStatus.STARTING,
    )

    assert room.is_joinable() is False


def test_room_state_not_joinable_when_room_is_full() -> None:
    players = [
        RoomPlayerState(player_id=f"player-{index}", nickname=f"player-{index}")
        for index in range(1, 6)
    ]
    room = RoomState(
        room_id="room-1",
        room_code="ABCD12",
        host_player_id="player-1",
        players=players,
        status=RoomStatus.WAITING,
    )

    assert room.is_joinable() is False

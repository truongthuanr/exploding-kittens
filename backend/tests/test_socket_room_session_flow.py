import asyncio

from app.modules.room.registry import RoomRegistry
from app.modules.room.service import RoomService
from app.modules.session.registry import SessionRegistry
from app.modules.session.service import SessionService
from app.realtime import server


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


class StubSessionService(SessionService):
    def __init__(self) -> None:
        super().__init__(registry=SessionRegistry())
        self._session_ids = iter(["session-1", "session-2", "session-3"])

    def _generate_session_id(self) -> str:
        return next(self._session_ids)


def test_room_create_returns_player_session_id(monkeypatch) -> None:
    monkeypatch.setattr(server, "room_service", StubRoomService())
    monkeypatch.setattr(server, "session_service", StubSessionService())

    entered_rooms: list[tuple[str, str]] = []

    async def fake_enter_room(sid: str, room: str) -> None:
        entered_rooms.append((sid, room))

    monkeypatch.setattr(server.sio, "enter_room", fake_enter_room)

    async def run() -> dict | None:
        return await server.handle_room_create("sid-1", {"nickname": "alice"})

    payload = asyncio.run(run())

    assert payload == {
        "roomId": "room-1",
        "roomCode": "ABCD12",
        "playerId": "player-1",
        "playerSessionId": "session-1",
    }
    assert entered_rooms == [("sid-1", "room-1")]


def test_room_join_returns_player_session_id(monkeypatch) -> None:
    room_service = StubRoomService()
    created = room_service.create_room("alice")
    session_service = StubSessionService()
    host_session = session_service.create_session(created.player.player_id, created.room.room_id)
    session_service.bind_socket(host_session.player_session_id, "sid-host")

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)

    entered_rooms: list[tuple[str, str]] = []
    emitted: list[tuple[str, dict, str]] = []

    async def fake_enter_room(sid: str, room: str) -> None:
        entered_rooms.append((sid, room))

    async def fake_emit(event: str, data: dict, room: str) -> None:
        emitted.append((event, data, room))

    monkeypatch.setattr(server.sio, "enter_room", fake_enter_room)
    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> dict | None:
        return await server.handle_room_join(
            "sid-2",
            {"roomCode": created.room.room_code, "nickname": "bob"},
        )

    payload = asyncio.run(run())

    assert payload == {
        "roomId": "room-1",
        "roomCode": "ABCD12",
        "playerId": "player-2",
        "playerSessionId": "session-2",
    }
    assert entered_rooms == [("sid-2", "room-1")]
    assert emitted[0][0] == "room:updated"
    assert emitted[0][2] == "room-1"


def test_disconnect_unbinds_socket_without_deleting_session(monkeypatch) -> None:
    room_service = StubRoomService()
    created = room_service.create_room("alice")
    session_service = StubSessionService()
    session = session_service.create_session(created.player.player_id, created.room.room_id)
    session_service.bind_socket(session.player_session_id, "sid-1")

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, room: str) -> None:
        emitted.append((event, data, room))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.disconnect("sid-1")

    asyncio.run(run())

    assert session_service.get_session(session.player_session_id) is session
    assert session_service.get_session_by_socket("sid-1") is None
    assert emitted[0][0] == "room:updated"
    assert emitted[0][2] == "room-1"


def test_reconnect_rebinds_same_session_to_new_socket(monkeypatch) -> None:
    room_service = StubRoomService()
    created = room_service.create_room("alice")
    session_service = StubSessionService()
    session = session_service.create_session(created.player.player_id, created.room.room_id)
    session_service.bind_socket(session.player_session_id, "sid-1")

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)

    entered_rooms: list[tuple[str, str]] = []
    emitted: list[tuple[str, dict, str]] = []

    async def fake_enter_room(sid: str, room: str) -> None:
        entered_rooms.append((sid, room))

    async def fake_emit(event: str, data: dict, room: str) -> None:
        emitted.append((event, data, room))

    monkeypatch.setattr(server.sio, "enter_room", fake_enter_room)
    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_player_reconnect("sid-2", {"playerSessionId": session.player_session_id})

    asyncio.run(run())

    assert session_service.get_session_by_socket("sid-1") is None
    rebound = session_service.get_session_by_socket("sid-2")
    assert rebound is session
    assert entered_rooms == [("sid-2", "room-1")]
    assert emitted[0][0] == "room:updated"
    assert emitted[0][2] == "room-1"

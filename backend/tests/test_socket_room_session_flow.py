import asyncio

from app.modules.game import GameRegistry, GameRuntimeState, GameSetupService
from app.modules.room.registry import RoomRegistry
from app.modules.room.service import RoomService
from app.modules.session.registry import SessionRegistry
from app.modules.session.service import SessionService
from app.realtime import server
from app.schemas import RoomStatus


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
    emitted: list[tuple[str, dict, str]] = []

    async def fake_enter_room(sid: str, room: str) -> None:
        entered_rooms.append((sid, room))

    async def fake_emit(event: str, data: dict, room: str) -> None:
        emitted.append((event, data, room))

    monkeypatch.setattr(server.sio, "enter_room", fake_enter_room)
    monkeypatch.setattr(server.sio, "emit", fake_emit)

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
    assert emitted[0][0] == "room:updated"
    assert emitted[0][2] == "room-1"


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


def test_room_join_duplicate_nickname_emits_error(monkeypatch) -> None:
    room_service = StubRoomService()
    created = room_service.create_room("alice")

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", StubSessionService())

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        emitted.append((event, data, to))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> dict | None:
        return await server.handle_room_join(
            "sid-2",
            {"roomCode": created.room.room_code, "nickname": "alice"},
        )

    payload = asyncio.run(run())

    assert payload is None
    assert emitted == [
        (
            "error",
            {
                "code": "duplicate_nickname",
                "message": "Duplicate nickname in room: alice",
                "requestId": None,
            },
            "sid-2",
        )
    ]


def test_room_ready_updates_player_readiness(monkeypatch) -> None:
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
        await server.handle_room_ready("sid-1", {"isReady": True})

    asyncio.run(run())

    assert created.player.is_ready is True
    assert emitted[0][0] == "room:updated"
    assert emitted[0][1]["players"][0]["isReady"] is True
    assert emitted[0][2] == "room-1"


def test_room_ready_without_bound_socket_session_emits_error(monkeypatch) -> None:
    monkeypatch.setattr(server, "session_service", StubSessionService())

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        emitted.append((event, data, to))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_room_ready("sid-1", {"isReady": True})

    asyncio.run(run())

    assert emitted == [
        (
            "error",
            {
                "code": "session_not_bound",
                "message": "Socket has no bound player session",
                "requestId": None,
            },
            "sid-1",
        )
    ]


def setup_startable_room() -> tuple[StubRoomService, StubSessionService]:
    room_service = StubRoomService()
    created = room_service.create_room("alice")
    room_service.join_room(created.room.room_code, "bob")
    room_service.join_room(created.room.room_code, "charlie")

    session_service = StubSessionService()
    host_session = session_service.create_session("player-1", created.room.room_id)
    guest_session = session_service.create_session("player-2", created.room.room_id)
    third_session = session_service.create_session("player-3", created.room.room_id)
    session_service.bind_socket(host_session.player_session_id, "sid-host")
    session_service.bind_socket(guest_session.player_session_id, "sid-guest")
    session_service.bind_socket(third_session.player_session_id, "sid-third")

    room_service.set_ready(created.room.room_id, "player-1", True)
    room_service.set_ready(created.room.room_id, "player-2", True)
    room_service.set_ready(created.room.room_id, "player-3", True)

    return room_service, session_service


def test_game_start_by_host_stores_runtime_state(monkeypatch) -> None:
    room_service, session_service = setup_startable_room()
    game_registry = GameRegistry()

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)
    monkeypatch.setattr(server, "game_setup_service", GameSetupService(shuffler=lambda cards: cards))
    monkeypatch.setattr(server, "game_registry", game_registry)

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, **kwargs) -> None:
        emitted.append((event, data, kwargs["room"]))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_game_start("sid-host", {"requestId": "req-1"})

    asyncio.run(run())

    runtime = game_registry.get("room-1")
    room = room_service.registry.get_by_id("room-1")
    assert runtime is not None
    assert room.status is RoomStatus.IN_GAME
    assert runtime.game_state.current_player_id == "player-1"
    assert [event[0] for event in emitted] == ["room:updated", "game:started"]
    assert emitted[1] == (
        "game:started",
        {"roomId": "room-1", "currentPlayerId": "player-1", "turnNumber": 1},
        "room-1",
    )


def test_game_start_by_non_host_emits_not_host(monkeypatch) -> None:
    room_service, session_service = setup_startable_room()

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)
    monkeypatch.setattr(server, "game_registry", GameRegistry())

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        emitted.append((event, data, to))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_game_start("sid-guest", {"requestId": "req-2"})

    asyncio.run(run())

    assert emitted[0][0] == "error"
    assert emitted[0][1]["code"] == "not_host"
    assert emitted[0][1]["requestId"] == "req-2"


def test_game_start_with_unready_players_emits_players_not_ready(monkeypatch) -> None:
    room_service, session_service = setup_startable_room()
    room_service.set_ready("room-1", "player-2", False)

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)
    monkeypatch.setattr(server, "game_registry", GameRegistry())

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        emitted.append((event, data, to))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_game_start("sid-host", {"requestId": "req-3"})

    asyncio.run(run())

    assert emitted[0][0] == "error"
    assert emitted[0][1]["code"] == "players_not_ready"
    assert emitted[0][1]["requestId"] == "req-3"


def test_duplicate_game_start_emits_game_already_started(monkeypatch) -> None:
    room_service, session_service = setup_startable_room()
    setup_result = GameSetupService(shuffler=lambda cards: cards).create_initial_game_state(
        room_service.registry.get_by_id("room-1")
    )
    game_registry = GameRegistry()
    game_registry.add(GameRuntimeState.from_setup_result(setup_result))

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)
    monkeypatch.setattr(server, "game_registry", game_registry)

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        emitted.append((event, data, to))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_game_start("sid-host", {"requestId": "req-4"})

    asyncio.run(run())

    assert emitted == [
        (
            "error",
            {
                "code": "game_already_started",
                "message": "Game already started for room: room-1",
                "requestId": "req-4",
            },
            "sid-host",
        )
    ]


def test_game_start_setup_failure_rolls_room_status_back(monkeypatch) -> None:
    class FailingGameSetupService:
        def create_initial_game_state(self, room):
            del room
            raise ValueError("setup failed")

    room_service, session_service = setup_startable_room()

    monkeypatch.setattr(server, "room_service", room_service)
    monkeypatch.setattr(server, "session_service", session_service)
    monkeypatch.setattr(server, "game_setup_service", FailingGameSetupService())
    monkeypatch.setattr(server, "game_registry", GameRegistry())

    emitted: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        emitted.append((event, data, to))

    monkeypatch.setattr(server.sio, "emit", fake_emit)

    async def run() -> None:
        await server.handle_game_start("sid-host", {"requestId": "req-5"})

    asyncio.run(run())

    room = room_service.registry.get_by_id("room-1")
    assert room.status is RoomStatus.WAITING
    assert emitted == [
        (
            "error",
            {
                "code": "invalid_operation",
                "message": "setup failed",
                "requestId": "req-5",
            },
            "sid-host",
        )
    ]


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

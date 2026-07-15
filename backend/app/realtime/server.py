import socketio
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.modules.game import GameRegistry, GameRuntimeState, GameSetupService
from app.modules.room import RoomService, RoomRegistry, to_room_updated_event
from app.modules.room.errors import (
    DuplicateNicknameError,
    NotEnoughPlayersError,
    NotHostError,
    PlayerNotInRoomError,
    PlayersDisconnectedError,
    PlayersNotReadyError,
    RoomFullError,
    RoomNotFoundError,
    RoomNotJoinableError,
    RoomNotWaitingError,
)
from app.modules.session import SessionService, SessionRegistry
from app.modules.session.models import PlayerSession
from app.schemas import (
    DrawCardRequest,
    ErrorEvent,
    GameStartedEvent,
    GameStartRequest,
    PlayerStatus,
    PlayCardRequest,
    ReconnectRequest,
    RoomCreateResponse,
    RoomCreateRequest,
    RoomJoinResponse,
    RoomJoinRequest,
    RoomReadyRequest,
    RoomStatus,
)

settings = get_settings()
room_service = RoomService(registry=RoomRegistry())
session_service = SessionService(registry=SessionRegistry())
game_setup_service = GameSetupService()
game_registry = GameRegistry()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins,
)

REQUEST_MODELS: dict[str, type[BaseModel]] = {
    "room:create": RoomCreateRequest,
    "room:join": RoomJoinRequest,
    "room:ready": RoomReadyRequest,
    "game:start": GameStartRequest,
    "turn:play-card": PlayCardRequest,
    "turn:draw-card": DrawCardRequest,
    "player:reconnect": ReconnectRequest,
}

ROOM_ERROR_CODES: dict[type[Exception], str] = {
    RoomNotFoundError: "room_not_found",
    DuplicateNicknameError: "duplicate_nickname",
    RoomNotJoinableError: "room_not_joinable",
    RoomFullError: "room_full",
    NotHostError: "not_host",
    RoomNotWaitingError: "room_not_waiting",
    PlayerNotInRoomError: "player_not_in_room",
    NotEnoughPlayersError: "not_enough_players",
    PlayersNotReadyError: "players_not_ready",
    PlayersDisconnectedError: "players_disconnected",
}
SERVICE_ERROR_TYPES = (ValueError, *ROOM_ERROR_CODES.keys())


def get_request_id(payload: BaseModel | None) -> str | None:
    if payload is None:
        return None
    return getattr(payload, "requestId", None)


async def emit_socket_error(
    sid: str,
    code: str,
    message: str,
    request_id: str | None = None,
) -> None:
    await sio.emit(
        "error",
        ErrorEvent(code=code, message=message, requestId=request_id).model_dump(),
        to=sid,
    )


async def emit_service_error(sid: str, error: Exception, request_id: str | None = None) -> None:
    error_code = ROOM_ERROR_CODES.get(type(error))
    if error_code is None and isinstance(error, ValueError):
        error_code = "invalid_operation"
    if error_code is None:
        raise error

    await emit_socket_error(sid, error_code, str(error), request_id)


async def emit_invalid_payload_error(
    sid: str,
    event_name: str,
    error: ValidationError,
) -> None:
    error_count = len(error.errors())
    await emit_socket_error(
        sid,
        "invalid_payload",
        f"Invalid payload for {event_name} ({error_count} validation error(s))",
    )


async def validate_socket_payload(
    sid: str,
    event_name: str,
    data: dict | None,
) -> BaseModel | None:
    model = REQUEST_MODELS[event_name]

    try:
        return model.model_validate(data or {})
    except ValidationError as error:
        await emit_invalid_payload_error(sid, event_name, error)
        return None


async def resolve_bound_session(sid: str, request_id: str | None = None) -> PlayerSession | None:
    session = session_service.get_session_by_socket(sid)
    if session is None:
        await emit_socket_error(
            sid,
            "session_not_bound",
            "Socket has no bound player session",
            request_id,
        )
        return None
    return session


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None) -> None:
    del environ, auth
    await sio.emit(
        "system:connected",
        {"sid": sid, "message": "Socket.IO connection established"},
        to=sid,
    )


@sio.event
async def disconnect(sid: str) -> None:
    session = session_service.unbind_socket(sid)
    if session is None:
        return

    room = room_service.registry.get_by_id(session.room_id)
    player = room.get_player(session.player_id)
    if player is None:
        return

    player.status = PlayerStatus.DISCONNECTED
    await sio.emit("room:updated", to_room_updated_event(room).model_dump(), room=room.room_id)


@sio.on("room:create")
async def handle_room_create(sid: str, data: dict | None) -> dict | None:
    payload = await validate_socket_payload(sid, "room:create", data)
    if payload is None:
        return None

    try:
        result = room_service.create_room(payload.nickname)
        session = session_service.create_session(
            player_id=result.player.player_id,
            room_id=result.room.room_id,
        )
        session_service.bind_socket(session.player_session_id, sid)
        await sio.enter_room(sid, result.room.room_id)
        await sio.emit(
            "room:updated",
            to_room_updated_event(result.room).model_dump(),
            room=result.room.room_id,
        )
    except SERVICE_ERROR_TYPES as error:
        await emit_service_error(sid, error)
        return None

    return RoomCreateResponse(
        roomId=result.room.room_id,
        roomCode=result.room.room_code,
        playerId=result.player.player_id,
        playerSessionId=session.player_session_id,
    ).model_dump()


@sio.on("room:join")
async def handle_room_join(sid: str, data: dict | None) -> dict | None:
    payload = await validate_socket_payload(sid, "room:join", data)
    if payload is None:
        return None

    try:
        result = room_service.join_room(payload.roomCode, payload.nickname)
        session = session_service.create_session(
            player_id=result.player.player_id,
            room_id=result.room.room_id,
        )
        session_service.bind_socket(session.player_session_id, sid)
        await sio.enter_room(sid, result.room.room_id)
        await sio.emit(
            "room:updated",
            to_room_updated_event(result.room).model_dump(),
            room=result.room.room_id,
        )
    except SERVICE_ERROR_TYPES as error:
        await emit_service_error(sid, error)
        return None

    return RoomJoinResponse(
        roomId=result.room.room_id,
        roomCode=result.room.room_code,
        playerId=result.player.player_id,
        playerSessionId=session.player_session_id,
    ).model_dump()


@sio.on("room:ready")
async def handle_room_ready(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "room:ready", data)
    if payload is None:
        return

    session = await resolve_bound_session(sid)
    if session is None:
        return

    try:
        room = room_service.set_ready(session.room_id, session.player_id, payload.isReady)
        await sio.emit(
            "room:updated",
            to_room_updated_event(room).model_dump(),
            room=room.room_id,
        )
    except SERVICE_ERROR_TYPES as error:
        await emit_service_error(sid, error)


@sio.on("game:start")
async def handle_game_start(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "game:start", data)
    if payload is None:
        return

    request_id = get_request_id(payload)
    session = await resolve_bound_session(sid, request_id)
    if session is None:
        return

    if game_registry.get(session.room_id) is not None:
        await emit_socket_error(
            sid,
            "game_already_started",
            f"Game already started for room: {session.room_id}",
            request_id,
        )
        return

    room = None
    try:
        room = room_service.transition_to_starting(session.room_id, session.player_id)
        setup_result = game_setup_service.create_initial_game_state(room)
        game_registry.add(GameRuntimeState.from_setup_result(setup_result))
        room.status = RoomStatus.IN_GAME
        await sio.emit(
            "room:updated",
            to_room_updated_event(room).model_dump(),
            room=room.room_id,
        )
        await sio.emit(
            "game:started",
            GameStartedEvent(
                roomId=setup_result.game_state.room_id,
                currentPlayerId=setup_result.game_state.current_player_id,
                turnNumber=setup_result.game_state.turn_number,
            ).model_dump(),
            room=room.room_id,
        )
    except SERVICE_ERROR_TYPES as error:
        if room is not None and room.status is RoomStatus.STARTING:
            room.status = RoomStatus.WAITING
        await emit_service_error(sid, error, request_id)


@sio.on("turn:play-card")
async def handle_turn_play_card(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "turn:play-card", data)
    if payload is None:
        return

    del payload


@sio.on("turn:draw-card")
async def handle_turn_draw_card(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "turn:draw-card", data)
    if payload is None:
        return

    del payload


@sio.on("player:reconnect")
async def handle_player_reconnect(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "player:reconnect", data)
    if payload is None:
        return

    session = session_service.rebind_socket(payload.playerSessionId, sid)
    await sio.enter_room(sid, session.room_id)

    room = room_service.registry.get_by_id(session.room_id)
    player = room.get_player(session.player_id)
    if player is None:
        return

    player.status = PlayerStatus.CONNECTED
    await sio.emit("room:updated", to_room_updated_event(room).model_dump(), room=room.room_id)


def build_socket_app(fastapi_app: FastAPI) -> socketio.ASGIApp:
    return socketio.ASGIApp(
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path=settings.socket_io_path,
    )

import socketio
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.modules.room import RoomService, RoomRegistry, to_room_updated_event
from app.modules.session import SessionService, SessionRegistry
from app.schemas import (
    DrawCardRequest,
    GameStartRequest,
    PlayerStatus,
    PlayCardRequest,
    ReconnectRequest,
    RoomCreateResponse,
    RoomCreateRequest,
    RoomJoinResponse,
    RoomJoinRequest,
    RoomReadyRequest,
)

settings = get_settings()
room_service = RoomService(registry=RoomRegistry())
session_service = SessionService(registry=SessionRegistry())

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


async def emit_invalid_payload_error(
    sid: str,
    event_name: str,
    error: ValidationError,
) -> None:
    error_count = len(error.errors())
    await sio.emit(
        "error",
        {
            "code": "invalid_payload",
            "message": f"Invalid payload for {event_name} ({error_count} validation error(s))",
        },
        to=sid,
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

    result = room_service.create_room(payload.nickname)
    session = session_service.create_session(
        player_id=result.player.player_id,
        room_id=result.room.room_id,
    )
    session_service.bind_socket(session.player_session_id, sid)
    await sio.enter_room(sid, result.room.room_id)

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

    result = room_service.join_room(payload.roomCode, payload.nickname)
    session = session_service.create_session(
        player_id=result.player.player_id,
        room_id=result.room.room_id,
    )
    session_service.bind_socket(session.player_session_id, sid)
    await sio.enter_room(sid, result.room.room_id)
    await sio.emit("room:updated", to_room_updated_event(result.room).model_dump(), room=result.room.room_id)

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

    del payload


@sio.on("game:start")
async def handle_game_start(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "game:start", data)
    if payload is None:
        return

    del payload


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

import socketio
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas import (
    DrawCardRequest,
    GameStartRequest,
    PlayCardRequest,
    ReconnectRequest,
    RoomCreateRequest,
    RoomJoinRequest,
    RoomReadyRequest,
)

settings = get_settings()

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
    del sid


@sio.on("room:create")
async def handle_room_create(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "room:create", data)
    if payload is None:
        return

    del payload


@sio.on("room:join")
async def handle_room_join(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "room:join", data)
    if payload is None:
        return

    del payload


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

    del payload


def build_socket_app(fastapi_app: FastAPI) -> socketio.ASGIApp:
    return socketio.ASGIApp(
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path=settings.socket_io_path,
    )

import asyncio
from collections import OrderedDict

import socketio
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.modules.game import (
    GameRegistry,
    GameRuntimeState,
    GameSetupService,
    TurnLifecycleOutcome,
    TurnLifecycleService,
)
from app.modules.game.errors import (
    CardNotInHandError,
    EmptyDrawPileError,
    GameNotFoundError,
    GameNotInProgressError,
    InvalidCardTypeError,
    InvalidExplosionStateError,
    InvalidPendingDrawsError,
    InvalidTurnPhaseError,
    NoPendingExplosionError,
    NotCurrentPlayerError,
    PendingResolutionError,
    PlayerDisconnectedError,
    PlayerEliminatedError,
    PlayerNotFoundError,
    TurnActionLockedError,
)
from app.modules.game.models import CardInstance, TurnLifecycleResult
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
from app.modules.session import SessionNotFoundError, SessionService, SessionRegistry
from app.modules.session.models import PlayerSession
from app.realtime.game_events import (
    build_recent_action,
    emit_game_ended,
    emit_game_state,
    emit_player_eliminated,
    emit_private_states,
    emit_requester_snapshot,
    emit_turn_started,
    emit_turn_started_to_sid,
    sync_finished_room,
)
from app.schemas import (
    ActionType,
    CardType,
    DrawCardRequest,
    ErrorEvent,
    GamePhase,
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
turn_service = TurnLifecycleService(registry=game_registry)
room_action_locks: dict[str, asyncio.Lock] = {}
processed_request_ids: OrderedDict[tuple[str, str, str], None] = OrderedDict()
MAX_PROCESSED_REQUEST_IDS = 500

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
GAME_ERROR_CODES: dict[type[Exception], str] = {
    GameNotFoundError: "game_not_found",
    GameNotInProgressError: "game_not_in_progress",
    PlayerNotFoundError: "player_not_found",
    NotCurrentPlayerError: "not_current_player",
    PlayerEliminatedError: "player_eliminated",
    PlayerDisconnectedError: "player_disconnected",
    CardNotInHandError: "card_not_in_hand",
    InvalidCardTypeError: "invalid_card_type",
    InvalidTurnPhaseError: "invalid_turn_phase",
    TurnActionLockedError: "turn_action_locked",
    PendingResolutionError: "pending_resolution",
    NoPendingExplosionError: "no_pending_explosion",
    InvalidExplosionStateError: "invalid_explosion_state",
    InvalidPendingDrawsError: "invalid_pending_draws",
    EmptyDrawPileError: "empty_draw_pile",
}
SERVICE_ERROR_TYPES = (ValueError, *ROOM_ERROR_CODES.keys(), *GAME_ERROR_CODES.keys())


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
    error_code = ROOM_ERROR_CODES.get(type(error)) or GAME_ERROR_CODES.get(type(error))
    if error_code is None and isinstance(error, ValueError):
        error_code = "invalid_operation"
    if error_code is None:
        raise error

    await emit_socket_error(sid, error_code, str(error), request_id)


def get_room_lock(room_id: str) -> asyncio.Lock:
    lock = room_action_locks.get(room_id)
    if lock is None:
        lock = asyncio.Lock()
        room_action_locks[room_id] = lock
    return lock


def get_active_turn_service() -> TurnLifecycleService:
    turn_service.registry = game_registry
    return turn_service


def get_processed_request_key(
    room_id: str,
    player_id: str,
    request_id: str | None,
) -> tuple[str, str, str] | None:
    if request_id is None:
        return None
    return (room_id, player_id, request_id)


def is_processed_request(room_id: str, player_id: str, request_id: str | None) -> bool:
    key = get_processed_request_key(room_id, player_id, request_id)
    return key is not None and key in processed_request_ids


def mark_processed_request(room_id: str, player_id: str, request_id: str | None) -> None:
    key = get_processed_request_key(room_id, player_id, request_id)
    if key is None:
        return

    processed_request_ids[key] = None
    processed_request_ids.move_to_end(key)
    while len(processed_request_ids) > MAX_PROCESSED_REQUEST_IDS:
        processed_request_ids.popitem(last=False)


def get_player_nickname(runtime: GameRuntimeState, player_id: str) -> str:
    for player in runtime.game_state.players:
        if player.player_id == player_id:
            return player.nickname
    return player_id


def find_card_in_private_hand(
    runtime: GameRuntimeState,
    player_id: str,
    card_id: str,
) -> CardInstance:
    private_state = runtime.player_private_states.get(player_id)
    if private_state is None:
        raise PlayerNotFoundError(player_id)

    for card in private_state.hand:
        if card.card_id == card_id:
            return card

    raise CardNotInHandError(player_id, card_id)


def should_emit_turn_started(
    before_turn: tuple[str, int],
    runtime: GameRuntimeState,
) -> bool:
    return before_turn != (
        runtime.game_state.current_player_id,
        runtime.game_state.turn_number,
    )


def recent_action_for_result(
    result: TurnLifecycleResult,
    eliminated_player_id: str | None = None,
) -> ActionType:
    if result.outcome is TurnLifecycleOutcome.SKIP_PLAYED:
        return ActionType.PLAY_SKIP
    if result.outcome is TurnLifecycleOutcome.ATTACK_PLAYED:
        return ActionType.PLAY_ATTACK
    if result.outcome is TurnLifecycleOutcome.DEFUSED:
        return ActionType.DEFUSE
    if result.outcome is TurnLifecycleOutcome.PLAYER_ELIMINATED:
        return ActionType.ELIMINATE
    if result.outcome is TurnLifecycleOutcome.GAME_FINISHED and eliminated_player_id is not None:
        return ActionType.ELIMINATE
    return ActionType.DRAW_CARD


def summary_for_action(runtime: GameRuntimeState, player_id: str, action_type: ActionType) -> str:
    nickname = get_player_nickname(runtime, player_id)
    if action_type is ActionType.START_GAME:
        return f"{nickname} started the game"
    if action_type is ActionType.PLAY_SKIP:
        return f"{nickname} played Skip"
    if action_type is ActionType.PLAY_ATTACK:
        return f"{nickname} played Attack"
    if action_type is ActionType.DEFUSE:
        return f"{nickname} defused an Exploding Kitten"
    if action_type is ActionType.ELIMINATE:
        return f"{nickname} was eliminated"
    return f"{nickname} drew a card"


async def emit_action_result(
    result: TurnLifecycleResult,
    before_turn: tuple[str, int],
    action_type: ActionType,
    eliminated_player_id: str | None = None,
) -> None:
    runtime = result.runtime
    recent_action = build_recent_action(
        actor_player_id=result.player_id,
        action_type=action_type,
        summary=summary_for_action(runtime, result.player_id, action_type),
    )
    await emit_game_state(sio, runtime, recent_action)
    await emit_private_states(sio, session_service, runtime)

    if eliminated_player_id is not None:
        await emit_player_eliminated(sio, runtime, eliminated_player_id)

    if result.outcome is TurnLifecycleOutcome.GAME_FINISHED:
        await sync_finished_room(sio, room_service, runtime)
        await emit_game_ended(sio, runtime)
    elif should_emit_turn_started(before_turn, runtime):
        await emit_turn_started(sio, runtime)


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
        runtime = GameRuntimeState.from_setup_result(setup_result)
        game_registry.add(runtime)
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
        recent_action = build_recent_action(
            actor_player_id=session.player_id,
            action_type=ActionType.START_GAME,
            summary=summary_for_action(runtime, session.player_id, ActionType.START_GAME),
        )
        await emit_game_state(sio, runtime, recent_action)
        await emit_private_states(sio, session_service, runtime)
        await emit_turn_started(sio, runtime)
    except SERVICE_ERROR_TYPES as error:
        if room is not None and room.status is RoomStatus.STARTING:
            room.status = RoomStatus.WAITING
        await emit_service_error(sid, error, request_id)


@sio.on("turn:play-card")
async def handle_turn_play_card(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "turn:play-card", data)
    if payload is None:
        return

    request_id = get_request_id(payload)
    session = await resolve_bound_session(sid, request_id)
    if session is None:
        return

    async with get_room_lock(session.room_id):
        runtime = game_registry.get(session.room_id)
        if runtime is None:
            await emit_service_error(sid, GameNotFoundError(session.room_id), request_id)
            return

        if is_processed_request(session.room_id, session.player_id, request_id):
            await emit_requester_snapshot(sio, sid, runtime, session.player_id)
            return

        try:
            card = find_card_in_private_hand(runtime, session.player_id, payload.cardId)
            before_turn = (runtime.game_state.current_player_id, runtime.game_state.turn_number)
            service = get_active_turn_service()

            if card.card_type is CardType.SKIP:
                result = service.play_skip(
                    session.room_id,
                    session.player_id,
                    payload.cardId,
                    request_id,
                )
            elif card.card_type is CardType.ATTACK:
                result = service.play_attack(
                    session.room_id,
                    session.player_id,
                    payload.cardId,
                    request_id,
                )
            else:
                await emit_socket_error(
                    sid,
                    "unsupported_card_action",
                    f"Card action is not supported yet: {card.card_type}",
                    request_id,
                )
                return

            action_type = recent_action_for_result(result)
            await emit_action_result(result, before_turn, action_type)
            mark_processed_request(session.room_id, session.player_id, request_id)
        except SERVICE_ERROR_TYPES as error:
            await emit_service_error(sid, error, request_id)


@sio.on("turn:draw-card")
async def handle_turn_draw_card(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "turn:draw-card", data)
    if payload is None:
        return

    request_id = get_request_id(payload)
    session = await resolve_bound_session(sid, request_id)
    if session is None:
        return

    async with get_room_lock(session.room_id):
        runtime = game_registry.get(session.room_id)
        if runtime is None:
            await emit_service_error(sid, GameNotFoundError(session.room_id), request_id)
            return

        if is_processed_request(session.room_id, session.player_id, request_id):
            await emit_requester_snapshot(sio, sid, runtime, session.player_id)
            return

        try:
            before_turn = (runtime.game_state.current_player_id, runtime.game_state.turn_number)
            was_eliminated = session.player_id in runtime.game_state.eliminated_player_ids
            service = get_active_turn_service()
            result = service.draw_card(session.room_id, session.player_id, request_id)

            if result.outcome is TurnLifecycleOutcome.EXPLOSION_PENDING:
                result = service.resolve_pending_explosion(
                    session.room_id,
                    session.player_id,
                    request_id,
                )

            is_eliminated = session.player_id in result.runtime.game_state.eliminated_player_ids
            eliminated_player_id = session.player_id if is_eliminated and not was_eliminated else None
            action_type = recent_action_for_result(result, eliminated_player_id)
            await emit_action_result(result, before_turn, action_type, eliminated_player_id)
            mark_processed_request(session.room_id, session.player_id, request_id)
        except SERVICE_ERROR_TYPES as error:
            await emit_service_error(sid, error, request_id)


@sio.on("player:reconnect")
async def handle_player_reconnect(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "player:reconnect", data)
    if payload is None:
        return

    try:
        session = session_service.rebind_socket(payload.playerSessionId, sid)
    except SessionNotFoundError:
        await emit_socket_error(
            sid,
            "invalid_session",
            f"Invalid player session: {payload.playerSessionId}",
        )
        return

    await sio.enter_room(sid, session.room_id)

    room = room_service.registry.get_by_id(session.room_id)
    player = room.get_player(session.player_id)
    if player is None:
        return

    player.status = PlayerStatus.CONNECTED
    await sio.emit("room:updated", to_room_updated_event(room).model_dump(), room=room.room_id)

    runtime = game_registry.get(session.room_id)
    if runtime is not None:
        await emit_requester_snapshot(sio, sid, runtime, session.player_id)
        if runtime.game_state.phase is not GamePhase.FINISHED:
            await emit_turn_started_to_sid(sio, sid, runtime)


def build_socket_app(fastapi_app: FastAPI) -> socketio.ASGIApp:
    return socketio.ASGIApp(
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path=settings.socket_io_path,
    )

import asyncio
from functools import wraps
from time import time
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
    FavorSelfTargetError,
    FavorTargetEmptyHandError,
    FavorTargetRequiredError,
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
from app.realtime.admission import AdmissionCache, AdmissionError, EPOCH, TTL_MS
from app.schemas.responses import BootstrapResponse
from app.realtime.game_events import (
    to_public_game_state,
    to_player_private_state,
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

# MVP uses one gateway transaction lock: all mutations and bootstrap serialization
# share an ordering boundary, including admission, presence and ownership changes.
# Engine room locks remain useful for service callers. Do not await a bound socket's
# disconnect inside this lock: takeover first removes its binding.
gateway_lock = asyncio.Lock()
admission_cache = AdmissionCache()


def serialized(handler):
    @wraps(handler)
    async def wrapped(*args, **kwargs):
        async with gateway_lock:
            return await handler(*args, **kwargs)
    return wrapped


def advance_version(room_id: str) -> None:
    room = room_service.registry.get_by_id(room_id)
    room.state_version += 1
    runtime = game_registry.get(room_id)
    if runtime:
        runtime.state_version = room.state_version


def bootstrap(session: PlayerSession, attempt_id: str | None = None) -> dict:
    room = room_service.registry.get_by_id(session.room_id)
    runtime = game_registry.get(session.room_id)
    private = to_player_private_state(runtime.player_private_states[session.player_id]) if runtime else None
    if private:
        private.stateVersion = room.state_version
    public = to_public_game_state(runtime) if runtime else None
    if public:
        public.stateVersion = room.state_version
    return BootstrapResponse(
        roomId=room.room_id, roomCode=room.room_code, playerId=session.player_id,
        playerSessionId=session.player_session_id, stateVersion=room.state_version,
        room=to_room_updated_event(room), game=public, private=private, attemptId=attempt_id,
    ).model_dump(mode="json")


async def bind_owner(
    session: PlayerSession, sid: str, instance: str | None, takeover: bool = False,
) -> None:
    owner = session_service.get_session_by_socket(sid)
    if owner is not None and owner is not session:
        raise ValueError("Socket already has a session binding")
    if session.client_instance_id is not None:
        if instance is None:
            raise AdmissionError("session_in_use", "This session requires its client instance identity")
        competing = session.client_instance_id != instance or (
            session.socket_id is not None and session.socket_id != sid
        )
        if competing and not takeover:
            raise AdmissionError("session_in_use", "Choose Continue in this tab to take over the session")
    old_sid = session.socket_id
    session_service.rebind_socket(session.player_session_id, sid)
    session.client_instance_id = instance
    if old_sid and old_sid != sid and instance is not None:
        await sio.emit("session:replaced", {"message": "Session continued in another tab"}, to=old_sid)
        await sio.disconnect(old_sid)
    await sio.enter_room(sid, session.room_id)
    room = room_service.registry.get_by_id(session.room_id)
    room.get_player(session.player_id).status = PlayerStatus.CONNECTED
    runtime = game_registry.get(session.room_id)
    if runtime:
        for player in runtime.game_state.players:
            if player.player_id == session.player_id and player.status is not PlayerStatus.ELIMINATED:
                player.status = PlayerStatus.CONNECTED
    advance_version(session.room_id)
    await sio.emit("room:updated", to_room_updated_event(room).model_dump(), room=room.room_id)
    if runtime and instance is not None:
        await emit_game_state(sio, runtime)
        await emit_private_states(sio, session_service, runtime)


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
    FavorTargetRequiredError: "target_required",
    FavorSelfTargetError: "invalid_target",
    FavorTargetEmptyHandError: "target_hand_empty",
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
    if result.outcome is TurnLifecycleOutcome.SHUFFLE_PLAYED:
        return ActionType.PLAY_SHUFFLE
    if result.outcome is TurnLifecycleOutcome.SEE_THE_FUTURE_PLAYED:
        return ActionType.PLAY_SEE_THE_FUTURE
    if result.outcome is TurnLifecycleOutcome.FAVOR_PLAYED:
        return ActionType.PLAY_FAVOR
    if result.outcome is TurnLifecycleOutcome.DEFUSED:
        return ActionType.DEFUSE
    if result.outcome is TurnLifecycleOutcome.PLAYER_ELIMINATED:
        return ActionType.ELIMINATE
    if result.outcome is TurnLifecycleOutcome.GAME_FINISHED and eliminated_player_id is not None:
        return ActionType.ELIMINATE
    return ActionType.DRAW_CARD


def summary_for_action(
    runtime: GameRuntimeState,
    player_id: str,
    action_type: ActionType,
    target_player_id: str | None = None,
) -> str:
    nickname = get_player_nickname(runtime, player_id)
    if action_type is ActionType.START_GAME:
        return f"{nickname} started the game"
    if action_type is ActionType.PLAY_SKIP:
        return f"{nickname} played Skip"
    if action_type is ActionType.PLAY_ATTACK:
        return f"{nickname} played Attack"
    if action_type is ActionType.PLAY_SHUFFLE:
        return f"{nickname} played Shuffle"
    if action_type is ActionType.PLAY_SEE_THE_FUTURE:
        return f"{nickname} played See the Future"
    if action_type is ActionType.PLAY_FAVOR:
        if target_player_id is not None:
            target_nickname = get_player_nickname(runtime, target_player_id)
            return f"{nickname} played Favor on {target_nickname}"
        return f"{nickname} played Favor"
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
    target_player_id: str | None = None,
) -> None:
    runtime = result.runtime
    advance_version(runtime.game_state.room_id)
    recent_action = build_recent_action(
        actor_player_id=result.player_id,
        action_type=action_type,
        summary=summary_for_action(runtime, result.player_id, action_type, target_player_id),
        target_player_id=target_player_id,
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
        correlation = (data.get("attemptId") or data.get("requestId")) if isinstance(data, dict) else None
        await emit_socket_error(sid, "invalid_payload",
            f"Invalid payload for {event_name} ({len(error.errors())} validation error(s))",
            correlation if isinstance(correlation, str) else None)
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
        {"sid": sid, "message": "Socket.IO connection established", "serverEpoch": EPOCH,
         "serverTime": int(time() * 1000), "idempotencyTtlMs": TTL_MS},
        to=sid,
    )


@sio.event
async def disconnect(sid: str, reason=None) -> None:
    # A replaced socket is already unbound; this also avoids reentering the lock.
    if session_service.get_session_by_socket(sid) is None:
        return
    async with gateway_lock:
        session = session_service.unbind_socket(sid)
        if session is None:
            return
        room = room_service.registry.get_by_id(session.room_id)
        player = room.get_player(session.player_id)
        if player is None:
            return
        player.status = PlayerStatus.DISCONNECTED
        runtime = game_registry.get(session.room_id)
        if runtime:
            for summary in runtime.game_state.players:
                if summary.player_id == session.player_id and summary.status is not PlayerStatus.ELIMINATED:
                    summary.status = PlayerStatus.DISCONNECTED
        advance_version(room.room_id)
        await sio.emit("room:updated", to_room_updated_event(room).model_dump(), room=room.room_id)
        if runtime and session.client_instance_id is not None:
            await emit_game_state(sio, runtime)
            await emit_private_states(sio, session_service, runtime)


async def admit(sid: str, event: str, data: dict | None) -> dict | None:
    payload = await validate_socket_payload(sid, event, data)
    if payload is None:
        return None
    request_id = payload.requestId
    fingerprint = (event, payload.clientInstanceId, payload.nickname, getattr(payload, "roomCode", None))
    try:
        if request_id:
            entry = admission_cache.lookup(request_id, fingerprint)
            if entry:
                session = session_service.get_session(entry.session_id)
                try:
                    await bind_owner(session, sid, payload.clientInstanceId)
                except AdmissionError as error:
                    if error.code != "session_in_use":
                        raise
                    # The replay key recovers identity, but never silently takes ownership.
                    # A different instance still needs an explicit reconnect takeover.
                    return {**bootstrap(session), "requiresTakeover": True}
                return bootstrap(session)
        if session_service.get_session_by_socket(sid) is not None:
            raise ValueError("Socket already has a session binding")
        result = (room_service.create_room(payload.nickname) if event == "room:create"
                  else room_service.join_room(payload.roomCode, payload.nickname))
        session = session_service.create_session(result.player.player_id, result.room.room_id)
        session.client_instance_id = payload.clientInstanceId
        session_service.bind_socket(session.player_session_id, sid)
        # Record before any network await: loss of the ack must not repeat creation.
        if request_id:
            admission_cache.remember(request_id, fingerprint, session.player_session_id)
        advance_version(session.room_id)
        await sio.enter_room(sid, result.room.room_id)
        await sio.emit("room:updated", to_room_updated_event(result.room).model_dump(), room=result.room.room_id)
        if request_id:
            return bootstrap(session)
        return RoomCreateResponse(roomId=result.room.room_id, roomCode=result.room.room_code,
            playerId=session.player_id, playerSessionId=session.player_session_id).model_dump()
    except AdmissionError as error:
        await emit_socket_error(sid, error.code, str(error), request_id)
    except SessionNotFoundError:
        await emit_socket_error(sid, "invalid_session", "Admission session is no longer available", request_id)
    except SERVICE_ERROR_TYPES as error:
        await emit_service_error(sid, error, request_id)
    return None


@sio.on("room:create")
@serialized
async def handle_room_create(sid: str, data: dict | None) -> dict | None:
    return await admit(sid, "room:create", data)


@sio.on("room:join")
@serialized
async def handle_room_join(sid: str, data: dict | None) -> dict | None:
    return await admit(sid, "room:join", data)


@sio.on("room:ready")
@serialized
async def handle_room_ready(sid: str, data: dict | None) -> None:
    payload = await validate_socket_payload(sid, "room:ready", data)
    if payload is None:
        return

    session = await resolve_bound_session(sid)
    if session is None:
        return

    try:
        room = room_service.set_ready(session.room_id, session.player_id, payload.isReady)
        advance_version(room.room_id)
        await sio.emit(
            "room:updated",
            to_room_updated_event(room).model_dump(),
            room=room.room_id,
        )
    except SERVICE_ERROR_TYPES as error:
        await emit_service_error(sid, error)


@sio.on("game:start")
@serialized
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
        advance_version(room.room_id)
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
@serialized
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
            elif card.card_type is CardType.SHUFFLE:
                result = service.play_shuffle(
                    session.room_id,
                    session.player_id,
                    payload.cardId,
                    request_id,
                )
            elif card.card_type is CardType.SEE_THE_FUTURE:
                result = service.play_see_the_future(
                    session.room_id,
                    session.player_id,
                    payload.cardId,
                    request_id,
                )
            elif card.card_type is CardType.FAVOR:
                result = service.play_favor(
                    session.room_id,
                    session.player_id,
                    payload.cardId,
                    payload.targetPlayerId,
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
            await emit_action_result(
                result,
                before_turn,
                action_type,
                target_player_id=payload.targetPlayerId if card.card_type is CardType.FAVOR else None,
            )
            mark_processed_request(session.room_id, session.player_id, request_id)
        except SERVICE_ERROR_TYPES as error:
            await emit_service_error(sid, error, request_id)


@sio.on("turn:draw-card")
@serialized
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
@serialized
async def handle_player_reconnect(sid: str, data: dict | None) -> dict | None:
    payload = await validate_socket_payload(sid, "player:reconnect", data)
    if payload is None:
        return

    correlation = payload.attemptId
    try:
        session = session_service.get_session(payload.playerSessionId)
        if session.client_instance_id is not None and (not payload.clientInstanceId or not payload.attemptId):
            raise AdmissionError("invalid_payload", "clientInstanceId and attemptId are required")
        await bind_owner(session, sid, payload.clientInstanceId, payload.takeover)
        result = bootstrap(session, payload.attemptId)
        # Preserve legacy backend-only clients' event bootstrap during migration.
        if payload.clientInstanceId is None:
            runtime = game_registry.get(session.room_id)
            if runtime is not None:
                await emit_requester_snapshot(sio, sid, runtime, session.player_id)
                if runtime.game_state.phase is not GamePhase.FINISHED:
                    await emit_turn_started_to_sid(sio, sid, runtime)
        return result
    except SessionNotFoundError:
        await emit_socket_error(sid, "invalid_session",
            f"Invalid player session: {payload.playerSessionId}", correlation)
    except AdmissionError as error:
        await emit_socket_error(sid, error.code, str(error), correlation)
    except SERVICE_ERROR_TYPES as error:
        await emit_service_error(sid, error, correlation)
    return None


def build_socket_app(fastapi_app: FastAPI) -> socketio.ASGIApp:
    return socketio.ASGIApp(
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path=settings.socket_io_path,
    )

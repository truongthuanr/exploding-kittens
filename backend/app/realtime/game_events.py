from __future__ import annotations

import socketio

from app.modules.game.models import GameRuntimeState, PlayerPrivateState
from app.modules.room import RoomService, to_room_updated_event
from app.modules.session import SessionService
from app.schemas.enums import ActionType, RoomStatus
from app.schemas.responses import (
    GameEndedEvent,
    PlayerEliminatedEvent,
    PlayerPrivateStateEvent,
    PrivateCardView,
    PublicGamePlayer,
    PublicGameStateEvent,
    RecentAction,
    TurnStartedEvent,
)


def build_recent_action(
    actor_player_id: str,
    action_type: ActionType,
    summary: str,
    target_player_id: str | None = None,
) -> RecentAction:
    return RecentAction(
        actorPlayerId=actor_player_id,
        actionType=action_type,
        targetPlayerId=target_player_id,
        summary=summary,
    )


def to_public_game_state(
    runtime: GameRuntimeState,
    recent_action: RecentAction | None = None,
) -> PublicGameStateEvent:
    state = runtime.game_state
    discard_top_card_type = None
    if state.discard_pile:
        discard_top_card_type = state.discard_pile[-1].card_type

    return PublicGameStateEvent(
        roomId=state.room_id,
        phase=state.phase,
        currentPlayerId=state.current_player_id,
        pendingDraws=state.pending_draws,
        turnNumber=state.turn_number,
        players=[
            PublicGamePlayer(
                playerId=player.player_id,
                nickname=player.nickname,
                handCount=player.hand_count,
                status=player.status,
            )
            for player in state.players
        ],
        discardTopCardType=discard_top_card_type,
        discardCount=len(state.discard_pile),
        winnerPlayerId=state.winner_player_id,
        recentAction=recent_action,
    )


def to_player_private_state(private_state: PlayerPrivateState) -> PlayerPrivateStateEvent:
    return PlayerPrivateStateEvent(
        playerId=private_state.player_id,
        hand=[
            PrivateCardView(cardId=card.card_id, cardType=card.card_type)
            for card in private_state.hand
        ],
        visibleFutureCards=private_state.visible_future_cards,
    )


def to_turn_started_event(runtime: GameRuntimeState) -> TurnStartedEvent:
    state = runtime.game_state
    return TurnStartedEvent(
        currentPlayerId=state.current_player_id,
        pendingDraws=state.pending_draws,
        turnNumber=state.turn_number,
    )


async def emit_game_state(
    sio: socketio.AsyncServer,
    runtime: GameRuntimeState,
    recent_action: RecentAction | None = None,
) -> None:
    await sio.emit(
        "game:state",
        to_public_game_state(runtime, recent_action).model_dump(mode="json"),
        room=runtime.game_state.room_id,
    )


async def emit_game_state_to_sid(
    sio: socketio.AsyncServer,
    sid: str,
    runtime: GameRuntimeState,
    recent_action: RecentAction | None = None,
) -> None:
    await sio.emit(
        "game:state",
        to_public_game_state(runtime, recent_action).model_dump(mode="json"),
        to=sid,
    )


async def emit_private_state(
    sio: socketio.AsyncServer,
    session_service: SessionService,
    runtime: GameRuntimeState,
    player_id: str,
) -> None:
    session = session_service.get_session_by_player(runtime.game_state.room_id, player_id)
    if session is None or session.socket_id is None:
        return

    private_state = runtime.player_private_states.get(player_id)
    if private_state is None:
        return

    await sio.emit(
        "player:private-state",
        to_player_private_state(private_state).model_dump(mode="json"),
        to=session.socket_id,
    )


async def emit_private_state_to_sid(
    sio: socketio.AsyncServer,
    sid: str,
    private_state: PlayerPrivateState,
) -> None:
    await sio.emit(
        "player:private-state",
        to_player_private_state(private_state).model_dump(mode="json"),
        to=sid,
    )


async def emit_private_states(
    sio: socketio.AsyncServer,
    session_service: SessionService,
    runtime: GameRuntimeState,
) -> None:
    for player_id in runtime.player_private_states:
        await emit_private_state(sio, session_service, runtime, player_id)


async def emit_turn_started(
    sio: socketio.AsyncServer,
    runtime: GameRuntimeState,
) -> None:
    await sio.emit(
        "turn:started",
        to_turn_started_event(runtime).model_dump(mode="json"),
        room=runtime.game_state.room_id,
    )


async def emit_turn_started_to_sid(
    sio: socketio.AsyncServer,
    sid: str,
    runtime: GameRuntimeState,
) -> None:
    await sio.emit(
        "turn:started",
        to_turn_started_event(runtime).model_dump(mode="json"),
        to=sid,
    )


async def emit_player_eliminated(
    sio: socketio.AsyncServer,
    runtime: GameRuntimeState,
    player_id: str,
) -> None:
    await sio.emit(
        "player:eliminated",
        PlayerEliminatedEvent(
            playerId=player_id,
            eliminatedBy="exploding_kitten",
        ).model_dump(mode="json"),
        room=runtime.game_state.room_id,
    )


async def emit_game_ended(
    sio: socketio.AsyncServer,
    runtime: GameRuntimeState,
) -> None:
    await sio.emit(
        "game:ended",
        GameEndedEvent(winnerPlayerId=runtime.game_state.winner_player_id).model_dump(mode="json"),
        room=runtime.game_state.room_id,
    )


async def sync_finished_room(
    sio: socketio.AsyncServer,
    room_service: RoomService,
    runtime: GameRuntimeState,
) -> None:
    room = room_service.registry.get_by_id(runtime.game_state.room_id)
    room.status = RoomStatus.FINISHED
    await sio.emit("room:updated", to_room_updated_event(room).model_dump(), room=room.room_id)


async def emit_requester_snapshot(
    sio: socketio.AsyncServer,
    sid: str,
    runtime: GameRuntimeState,
    player_id: str,
    recent_action: RecentAction | None = None,
) -> None:
    await emit_game_state_to_sid(sio, sid, runtime, recent_action)
    private_state = runtime.player_private_states.get(player_id)
    if private_state is not None:
        await emit_private_state_to_sid(sio, sid, private_state)

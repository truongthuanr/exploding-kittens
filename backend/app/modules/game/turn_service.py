from __future__ import annotations

from dataclasses import dataclass

from app.modules.game.errors import (
    EmptyDrawPileError,
    GameNotFoundError,
    GameNotInProgressError,
    InvalidPendingDrawsError,
    InvalidTurnPhaseError,
    NotCurrentPlayerError,
    PendingResolutionError,
    PlayerDisconnectedError,
    PlayerEliminatedError,
    PlayerNotFoundError,
    TurnActionLockedError,
)
from app.modules.game.models import (
    GamePlayerSummary,
    GameRuntimeState,
    PlayerPrivateState,
    TurnLifecycleOutcome,
    TurnLifecycleResult,
    utc_now_iso,
)
from app.modules.game.registry import GameRegistry
from app.schemas.enums import CardType, GamePhase, PlayerStatus, RoomStatus


@dataclass(slots=True)
class TurnLifecycleService:
    registry: GameRegistry

    def draw_card(
        self,
        room_id: str,
        player_id: str,
        request_id: str | None = None,
    ) -> TurnLifecycleResult:
        runtime = self.registry.get(room_id)
        if runtime is None:
            raise GameNotFoundError(room_id)

        validate_draw_request(runtime, player_id)

        state = runtime.game_state
        state.phase = GamePhase.TURN_DRAW
        card = state.draw_pile.pop(0)

        if card.card_type is CardType.EXPLODING_KITTEN:
            runtime.pending_explosion_card = card
            state.phase = GamePhase.RESOLVING_EXPLOSION
            state.action_lock = True
            state.updated_at = utc_now_iso()
            return TurnLifecycleResult(
                outcome=TurnLifecycleOutcome.EXPLOSION_PENDING,
                runtime=runtime,
                player_id=player_id,
                request_id=request_id,
            )

        player_private_state = _get_player_private_state(runtime, player_id)
        player_summary = _get_player_summary(runtime, player_id)
        player_private_state.hand.append(card)
        player_summary.hand_count += 1
        state.pending_draws -= 1

        if state.pending_draws > 0:
            state.phase = GamePhase.TURN_ACTION
            state.updated_at = utc_now_iso()
            outcome = TurnLifecycleOutcome.NORMAL_DRAW
        else:
            outcome = complete_turn(runtime)

        return TurnLifecycleResult(
            outcome=outcome,
            runtime=runtime,
            player_id=player_id,
            request_id=request_id,
        )


def validate_draw_request(runtime: GameRuntimeState, player_id: str) -> None:
    state = runtime.game_state

    if state.room_status is not RoomStatus.IN_GAME:
        raise GameNotInProgressError(state.room_id)

    if runtime.pending_explosion_card is not None:
        raise PendingResolutionError(state.room_id)

    if state.phase is not GamePhase.TURN_ACTION:
        raise InvalidTurnPhaseError(state.phase)

    if state.action_lock:
        raise TurnActionLockedError(state.room_id)

    player_summary = _get_player_summary(runtime, player_id)
    _get_player_private_state(runtime, player_id)

    if player_summary.player_id != state.current_player_id:
        raise NotCurrentPlayerError(player_id)

    if player_summary.status is PlayerStatus.ELIMINATED or player_id in state.eliminated_player_ids:
        raise PlayerEliminatedError(player_id)

    if player_summary.status is not PlayerStatus.CONNECTED:
        raise PlayerDisconnectedError(player_id)

    if state.pending_draws < 1:
        raise InvalidPendingDrawsError(state.pending_draws)

    if not state.draw_pile:
        raise EmptyDrawPileError(state.room_id)


def next_alive_player(runtime: GameRuntimeState) -> GamePlayerSummary | None:
    state = runtime.game_state
    current_player = _get_player_summary(runtime, state.current_player_id)
    ordered_players = sorted(state.players, key=lambda player: player.seat_index)
    current_index = ordered_players.index(current_player)

    for offset in range(1, len(ordered_players)):
        candidate = ordered_players[(current_index + offset) % len(ordered_players)]
        if candidate.status is not PlayerStatus.ELIMINATED and candidate.player_id not in state.eliminated_player_ids:
            return candidate

    return None


def complete_turn(
    runtime: GameRuntimeState,
    pending_draws_for_next: int = 1,
) -> TurnLifecycleOutcome:
    state = runtime.game_state
    next_player = next_alive_player(runtime)

    if next_player is None:
        state.phase = GamePhase.FINISHED
        state.room_status = RoomStatus.FINISHED
        state.winner_player_id = state.current_player_id
        state.action_lock = False
        state.updated_at = utc_now_iso()
        return TurnLifecycleOutcome.GAME_FINISHED

    state.turn_number += 1
    state.current_player_id = next_player.player_id
    state.pending_draws = pending_draws_for_next
    state.phase = GamePhase.TURN_ACTION
    state.updated_at = utc_now_iso()
    return TurnLifecycleOutcome.NORMAL_DRAW


def _get_player_summary(runtime: GameRuntimeState, player_id: str) -> GamePlayerSummary:
    for player in runtime.game_state.players:
        if player.player_id == player_id:
            return player
    raise PlayerNotFoundError(player_id)


def _get_player_private_state(runtime: GameRuntimeState, player_id: str) -> PlayerPrivateState:
    private_state = runtime.player_private_states.get(player_id)
    if private_state is None:
        raise PlayerNotFoundError(player_id)
    return private_state

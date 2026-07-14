from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.modules.game.errors import (
    CardNotInHandError,
    EmptyDrawPileError,
    GameNotFoundError,
    GameNotInProgressError,
    InvalidExplosionStateError,
    InvalidCardTypeError,
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
from app.modules.game.models import (
    CardInstance,
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
    randomizer: random.Random = field(default_factory=random.Random)

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

    def play_skip(
        self,
        room_id: str,
        player_id: str,
        card_id: str,
        request_id: str | None = None,
    ) -> TurnLifecycleResult:
        runtime = self.registry.get(room_id)
        if runtime is None:
            raise GameNotFoundError(room_id)

        card = validate_action_card_request(runtime, player_id, card_id, CardType.SKIP)
        _discard_card_from_hand(runtime, player_id, card)

        state = runtime.game_state
        state.pending_draws -= 1

        if state.pending_draws > 0:
            state.phase = GamePhase.TURN_ACTION
            state.updated_at = utc_now_iso()
            outcome = TurnLifecycleOutcome.SKIP_PLAYED
        else:
            turn_outcome = complete_turn(runtime)
            if turn_outcome is TurnLifecycleOutcome.GAME_FINISHED:
                outcome = TurnLifecycleOutcome.GAME_FINISHED
            else:
                outcome = TurnLifecycleOutcome.SKIP_PLAYED

        return TurnLifecycleResult(
            outcome=outcome,
            runtime=runtime,
            player_id=player_id,
            request_id=request_id,
        )

    def play_attack(
        self,
        room_id: str,
        player_id: str,
        card_id: str,
        request_id: str | None = None,
    ) -> TurnLifecycleResult:
        runtime = self.registry.get(room_id)
        if runtime is None:
            raise GameNotFoundError(room_id)

        card = validate_action_card_request(runtime, player_id, card_id, CardType.ATTACK)
        inherited_pending_draws = runtime.game_state.pending_draws + 1
        _discard_card_from_hand(runtime, player_id, card)

        turn_outcome = complete_turn(runtime, pending_draws_for_next=inherited_pending_draws)
        if turn_outcome is TurnLifecycleOutcome.GAME_FINISHED:
            outcome = TurnLifecycleOutcome.GAME_FINISHED
        else:
            outcome = TurnLifecycleOutcome.ATTACK_PLAYED

        return TurnLifecycleResult(
            outcome=outcome,
            runtime=runtime,
            player_id=player_id,
            request_id=request_id,
        )

    def resolve_pending_explosion(
        self,
        room_id: str,
        player_id: str,
        request_id: str | None = None,
    ) -> TurnLifecycleResult:
        runtime = self.registry.get(room_id)
        if runtime is None:
            raise GameNotFoundError(room_id)

        player_summary = validate_explosion_resolution_request(runtime, player_id)
        defuse_card = _find_card_in_hand(runtime, player_id, CardType.DEFUSE)

        if defuse_card is not None:
            outcome = self._resolve_explosion_with_defuse(runtime, player_id, defuse_card)
        else:
            outcome = _resolve_explosion_without_defuse(runtime, player_id, player_summary)

        return TurnLifecycleResult(
            outcome=outcome,
            runtime=runtime,
            player_id=player_id,
            request_id=request_id,
        )

    def _resolve_explosion_with_defuse(
        self,
        runtime: GameRuntimeState,
        player_id: str,
        defuse_card: CardInstance,
    ) -> TurnLifecycleOutcome:
        state = runtime.game_state
        bomb = runtime.pending_explosion_card
        if bomb is None:
            raise NoPendingExplosionError(state.room_id)

        _discard_card_from_hand(runtime, player_id, defuse_card)
        insert_index = self.randomizer.randint(0, len(state.draw_pile))
        state.draw_pile.insert(insert_index, bomb)
        runtime.pending_explosion_card = None
        state.pending_draws -= 1
        state.action_lock = False

        if state.pending_draws > 0:
            state.phase = GamePhase.TURN_ACTION
            state.updated_at = utc_now_iso()
            return TurnLifecycleOutcome.DEFUSED

        turn_outcome = complete_turn(runtime)
        if turn_outcome is TurnLifecycleOutcome.GAME_FINISHED:
            return TurnLifecycleOutcome.GAME_FINISHED
        return TurnLifecycleOutcome.DEFUSED


def validate_draw_request(runtime: GameRuntimeState, player_id: str) -> None:
    _validate_active_turn(runtime, player_id)

    if not runtime.game_state.draw_pile:
        raise EmptyDrawPileError(runtime.game_state.room_id)


def validate_action_card_request(
    runtime: GameRuntimeState,
    player_id: str,
    card_id: str,
    expected_card_type: CardType,
) -> CardInstance:
    _validate_active_turn(runtime, player_id)
    player_private_state = _get_player_private_state(runtime, player_id)

    for card in player_private_state.hand:
        if card.card_id == card_id:
            if card.card_type is not expected_card_type:
                raise InvalidCardTypeError(card.card_id, expected_card_type, card.card_type)
            return card

    raise CardNotInHandError(player_id, card_id)


def validate_explosion_resolution_request(
    runtime: GameRuntimeState,
    player_id: str,
) -> GamePlayerSummary:
    state = runtime.game_state

    if state.room_status is not RoomStatus.IN_GAME:
        raise GameNotInProgressError(state.room_id)

    if runtime.pending_explosion_card is None:
        raise NoPendingExplosionError(state.room_id)

    if state.phase is not GamePhase.RESOLVING_EXPLOSION or not state.action_lock:
        raise InvalidExplosionStateError(state.room_id, state.phase, state.action_lock)

    player_summary = _get_player_summary(runtime, player_id)
    _get_player_private_state(runtime, player_id)

    if player_summary.player_id != state.current_player_id:
        raise NotCurrentPlayerError(player_id)

    if player_summary.status is PlayerStatus.ELIMINATED or player_id in state.eliminated_player_ids:
        raise PlayerEliminatedError(player_id)

    if state.pending_draws < 1:
        raise InvalidPendingDrawsError(state.pending_draws)

    return player_summary


def _validate_active_turn(runtime: GameRuntimeState, player_id: str) -> None:
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


def _discard_card_from_hand(runtime: GameRuntimeState, player_id: str, card: CardInstance) -> None:
    player_private_state = _get_player_private_state(runtime, player_id)
    player_summary = _get_player_summary(runtime, player_id)

    player_private_state.hand.remove(card)
    runtime.game_state.discard_pile.append(card)
    player_summary.hand_count -= 1


def _find_card_in_hand(
    runtime: GameRuntimeState,
    player_id: str,
    card_type: CardType,
) -> CardInstance | None:
    player_private_state = _get_player_private_state(runtime, player_id)
    for card in player_private_state.hand:
        if card.card_type is card_type:
            return card
    return None


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


def alive_players(runtime: GameRuntimeState) -> list[GamePlayerSummary]:
    state = runtime.game_state
    return [
        player
        for player in state.players
        if player.status is not PlayerStatus.ELIMINATED and player.player_id not in state.eliminated_player_ids
    ]


def sole_alive_player(runtime: GameRuntimeState) -> GamePlayerSummary | None:
    players = alive_players(runtime)
    if len(players) == 1:
        return players[0]
    return None


def _resolve_explosion_without_defuse(
    runtime: GameRuntimeState,
    player_id: str,
    player_summary: GamePlayerSummary,
) -> TurnLifecycleOutcome:
    state = runtime.game_state
    bomb = runtime.pending_explosion_card
    if bomb is None:
        raise NoPendingExplosionError(state.room_id)

    player_private_state = _get_player_private_state(runtime, player_id)
    player_summary.status = PlayerStatus.ELIMINATED
    if player_id not in state.eliminated_player_ids:
        state.eliminated_player_ids.append(player_id)

    state.discard_pile.append(bomb)
    state.discard_pile.extend(player_private_state.hand)
    player_private_state.hand.clear()
    player_private_state.visible_future_cards = None
    player_summary.hand_count = 0
    runtime.pending_explosion_card = None
    state.action_lock = False

    winner = sole_alive_player(runtime)
    if winner is not None:
        state.phase = GamePhase.FINISHED
        state.room_status = RoomStatus.FINISHED
        state.winner_player_id = winner.player_id
        state.updated_at = utc_now_iso()
        return TurnLifecycleOutcome.GAME_FINISHED

    next_player = next_alive_player(runtime)
    if next_player is None:
        state.phase = GamePhase.FINISHED
        state.room_status = RoomStatus.FINISHED
        state.winner_player_id = None
        state.updated_at = utc_now_iso()
        return TurnLifecycleOutcome.GAME_FINISHED

    state.turn_number += 1
    state.current_player_id = next_player.player_id
    state.pending_draws = 1
    state.phase = GamePhase.TURN_ACTION
    state.updated_at = utc_now_iso()
    return TurnLifecycleOutcome.PLAYER_ELIMINATED


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

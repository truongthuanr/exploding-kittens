from __future__ import annotations

from copy import deepcopy

import pytest

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
    CardInstance,
    GamePlayerSummary,
    GameRuntimeState,
    GameSetupResult,
    PlayerPrivateState,
    ServerGameState,
    TurnLifecycleOutcome,
)
from app.modules.game.registry import GameRegistry
from app.modules.game.turn_service import TurnLifecycleService, complete_turn, next_alive_player
from app.schemas.enums import CardType, GamePhase, PlayerStatus, RoomStatus


def card(card_id: str, card_type: CardType = CardType.SKIP) -> CardInstance:
    return CardInstance(card_id=card_id, card_type=card_type)


def build_runtime(
    *,
    current_player_id: str = "player-1",
    pending_draws: int = 1,
    draw_pile: list[CardInstance] | None = None,
    room_status: RoomStatus = RoomStatus.IN_GAME,
    phase: GamePhase = GamePhase.TURN_ACTION,
    action_lock: bool = False,
    statuses: dict[str, PlayerStatus] | None = None,
    eliminated_player_ids: list[str] | None = None,
) -> GameRuntimeState:
    statuses = statuses or {}
    eliminated_player_ids = eliminated_player_ids or []
    players = [
        GamePlayerSummary(
            player_id=f"player-{index}",
            nickname=f"player-{index}",
            status=statuses.get(f"player-{index}", PlayerStatus.CONNECTED),
            hand_count=1,
            seat_index=index - 1,
            is_host=index == 1,
            is_ready=True,
        )
        for index in range(1, 4)
    ]
    private_states = {
        player.player_id: PlayerPrivateState(
            player_id=player.player_id,
            hand=[card(f"{player.player_id}-hand")],
        )
        for player in players
    }
    game_state = ServerGameState(
        room_id="room-1",
        room_status=room_status,
        phase=phase,
        turn_number=1,
        current_player_id=current_player_id,
        pending_draws=pending_draws,
        players=players,
        draw_pile=draw_pile if draw_pile is not None else [card("draw-1"), card("draw-2")],
        discard_pile=[],
        eliminated_player_ids=eliminated_player_ids,
        winner_player_id=None,
        action_lock=action_lock,
        created_at="t0",
        updated_at="t0",
    )
    return GameRuntimeState(
        game_state=game_state,
        player_private_states=private_states,
        pending_explosion_card=None,
    )


def build_service(runtime: GameRuntimeState) -> TurnLifecycleService:
    registry = GameRegistry()
    registry.add(runtime)
    return TurnLifecycleService(registry=registry)


def assert_unchanged_after_error(runtime: GameRuntimeState, error_type: type[Exception], player_id: str) -> None:
    before = deepcopy(runtime)
    service = build_service(runtime)

    with pytest.raises(error_type):
        service.draw_card("room-1", player_id)

    assert runtime == before


def test_runtime_state_from_setup_result_preserves_setup_output() -> None:
    setup_runtime = build_runtime()
    setup_result = GameSetupResult(
        game_state=setup_runtime.game_state,
        player_private_states=setup_runtime.player_private_states,
    )

    runtime = GameRuntimeState.from_setup_result(setup_result)

    assert runtime.game_state is setup_result.game_state
    assert runtime.player_private_states is setup_result.player_private_states
    assert runtime.pending_explosion_card is None


def test_valid_normal_draw_adds_top_card_to_only_current_player_hand() -> None:
    top_card = card("top-card", CardType.FAVOR)
    second_card = card("second-card", CardType.SKIP)
    runtime = build_runtime(pending_draws=2, draw_pile=[top_card, second_card])
    service = build_service(runtime)

    result = service.draw_card("room-1", "player-1", request_id="request-1")

    assert result.outcome is TurnLifecycleOutcome.NORMAL_DRAW
    assert result.runtime is runtime
    assert result.player_id == "player-1"
    assert result.request_id == "request-1"
    assert not hasattr(result, "card")
    assert runtime.game_state.draw_pile == [second_card]
    assert runtime.player_private_states["player-1"].hand[-1] is top_card
    assert len(runtime.player_private_states["player-2"].hand) == 1
    assert len(runtime.player_private_states["player-3"].hand) == 1
    assert runtime.game_state.players[0].hand_count == 2
    assert runtime.game_state.players[1].hand_count == 1
    assert runtime.pending_explosion_card is None
    assert runtime.game_state.phase is GamePhase.TURN_ACTION
    assert runtime.game_state.current_player_id == "player-1"
    assert runtime.game_state.turn_number == 1
    assert runtime.game_state.pending_draws == 1


def test_normal_draw_with_one_pending_draw_completes_turn() -> None:
    runtime = build_runtime(pending_draws=1, draw_pile=[card("top-card")])
    service = build_service(runtime)

    result = service.draw_card("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.NORMAL_DRAW
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.turn_number == 2
    assert runtime.game_state.pending_draws == 1
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_next_alive_player_wraps_around_and_skips_eliminated_players() -> None:
    runtime = build_runtime(
        current_player_id="player-3",
        statuses={"player-1": PlayerStatus.ELIMINATED},
        eliminated_player_ids=["player-1"],
    )

    next_player = next_alive_player(runtime)

    assert next_player is not None
    assert next_player.player_id == "player-2"


def test_complete_turn_finishes_game_when_no_other_alive_player_exists() -> None:
    runtime = build_runtime(
        statuses={
            "player-2": PlayerStatus.ELIMINATED,
            "player-3": PlayerStatus.ELIMINATED,
        },
        eliminated_player_ids=["player-2", "player-3"],
    )

    outcome = complete_turn(runtime)

    assert outcome is TurnLifecycleOutcome.GAME_FINISHED
    assert runtime.game_state.phase is GamePhase.FINISHED
    assert runtime.game_state.room_status is RoomStatus.FINISHED
    assert runtime.game_state.winner_player_id == "player-1"
    assert runtime.game_state.action_lock is False
    assert runtime.game_state.turn_number == 1


def test_selecting_disconnected_next_player_advances_then_blocks_their_draw() -> None:
    runtime = build_runtime(
        pending_draws=1,
        draw_pile=[card("draw-1"), card("draw-2")],
        statuses={
            "player-2": PlayerStatus.DISCONNECTED,
            "player-3": PlayerStatus.ELIMINATED,
        },
        eliminated_player_ids=["player-3"],
    )
    service = build_service(runtime)

    result = service.draw_card("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.NORMAL_DRAW
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.pending_draws == 1

    before = deepcopy(runtime)
    with pytest.raises(PlayerDisconnectedError):
        service.draw_card("room-1", "player-2")
    assert runtime == before


@pytest.mark.parametrize(
    ("runtime", "player_id", "error_type"),
    [
        (build_runtime(), "player-2", NotCurrentPlayerError),
        (
            build_runtime(
                statuses={"player-1": PlayerStatus.ELIMINATED},
                eliminated_player_ids=["player-1"],
            ),
            "player-1",
            PlayerEliminatedError,
        ),
        (
            build_runtime(statuses={"player-1": PlayerStatus.DISCONNECTED}),
            "player-1",
            PlayerDisconnectedError,
        ),
        (build_runtime(action_lock=True), "player-1", TurnActionLockedError),
        (build_runtime(phase=GamePhase.TURN_DRAW), "player-1", InvalidTurnPhaseError),
        (build_runtime(room_status=RoomStatus.FINISHED), "player-1", GameNotInProgressError),
        (build_runtime(pending_draws=0), "player-1", InvalidPendingDrawsError),
        (build_runtime(draw_pile=[]), "player-1", EmptyDrawPileError),
    ],
)
def test_invalid_draw_requests_are_rejected_without_state_mutation(
    runtime: GameRuntimeState,
    player_id: str,
    error_type: type[Exception],
) -> None:
    assert_unchanged_after_error(runtime, error_type, player_id)


def test_missing_game_raises_game_not_found() -> None:
    service = TurnLifecycleService(registry=GameRegistry())

    with pytest.raises(GameNotFoundError):
        service.draw_card("missing-room", "player-1")


def test_missing_player_is_rejected_without_state_mutation() -> None:
    runtime = build_runtime()

    assert_unchanged_after_error(runtime, PlayerNotFoundError, "missing-player")


def test_pending_explosion_card_rejects_draw_without_state_mutation() -> None:
    runtime = build_runtime()
    runtime.pending_explosion_card = card("pending-bomb", CardType.EXPLODING_KITTEN)

    assert_unchanged_after_error(runtime, PendingResolutionError, "player-1")


def test_exploding_kitten_draw_enters_pending_explosion_without_decrementing_pending_draws() -> None:
    bomb = card("bomb", CardType.EXPLODING_KITTEN)
    next_card = card("next-card", CardType.SKIP)
    runtime = build_runtime(pending_draws=2, draw_pile=[bomb, next_card])
    service = build_service(runtime)

    result = service.draw_card("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.EXPLOSION_PENDING
    assert runtime.game_state.draw_pile == [next_card]
    assert runtime.pending_explosion_card is bomb
    assert runtime.game_state.phase is GamePhase.RESOLVING_EXPLOSION
    assert runtime.game_state.action_lock is True
    assert runtime.game_state.pending_draws == 2
    assert bomb not in runtime.player_private_states["player-1"].hand
    assert bomb not in runtime.game_state.discard_pile

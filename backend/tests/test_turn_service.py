from __future__ import annotations

from copy import deepcopy

import pytest

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
    GameSetupResult,
    PlayerPrivateState,
    ServerGameState,
    TurnLifecycleOutcome,
)
from app.modules.game.registry import GameRegistry
from app.modules.game.turn_service import TurnLifecycleService, complete_turn, next_alive_player
from app.schemas.enums import CardType, GamePhase, PlayerStatus, RoomStatus


class FixedRandom:
    def __init__(self, value: int) -> None:
        self.value = value

    def randint(self, start: int, stop: int) -> int:
        assert start <= self.value <= stop
        return self.value


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


def build_service_with_random(runtime: GameRuntimeState, index: int) -> TurnLifecycleService:
    registry = GameRegistry()
    registry.add(runtime)
    return TurnLifecycleService(registry=registry, randomizer=FixedRandom(index))


def prepare_pending_explosion(
    runtime: GameRuntimeState,
    bomb: CardInstance | None = None,
) -> CardInstance:
    pending_bomb = bomb or card("pending-bomb", CardType.EXPLODING_KITTEN)
    runtime.pending_explosion_card = pending_bomb
    runtime.game_state.phase = GamePhase.RESOLVING_EXPLOSION
    runtime.game_state.action_lock = True
    return pending_bomb


def set_player_hand(runtime: GameRuntimeState, player_id: str, hand: list[CardInstance]) -> None:
    runtime.player_private_states[player_id].hand = hand
    for player in runtime.game_state.players:
        if player.player_id == player_id:
            player.hand_count = len(hand)
            return
    raise AssertionError(f"missing player: {player_id}")


def assert_unchanged_after_error(runtime: GameRuntimeState, error_type: type[Exception], player_id: str) -> None:
    before = deepcopy(runtime)
    service = build_service(runtime)

    with pytest.raises(error_type):
        service.draw_card("room-1", player_id)

    assert runtime == before


def assert_unchanged_after_action_error(
    runtime: GameRuntimeState,
    error_type: type[Exception],
    player_id: str,
    card_id: str = "player-1-hand",
) -> None:
    before = deepcopy(runtime)
    service = build_service(runtime)

    with pytest.raises(error_type):
        service.play_skip("room-1", player_id, card_id)

    assert runtime == before


def assert_unchanged_after_explosion_error(
    runtime: GameRuntimeState,
    error_type: type[Exception],
    player_id: str,
) -> None:
    before = deepcopy(runtime)
    service = build_service(runtime)

    with pytest.raises(error_type):
        service.resolve_pending_explosion("room-1", player_id)

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


def test_play_skip_with_one_pending_draw_discards_card_and_completes_turn() -> None:
    runtime = build_runtime(pending_draws=1)
    skip_card = runtime.player_private_states["player-1"].hand[0]
    service = build_service(runtime)

    result = service.play_skip("room-1", "player-1", skip_card.card_id, request_id="request-1")

    assert result.outcome is TurnLifecycleOutcome.SKIP_PLAYED
    assert result.runtime is runtime
    assert result.player_id == "player-1"
    assert result.request_id == "request-1"
    assert runtime.player_private_states["player-1"].hand == []
    assert runtime.game_state.discard_pile == [skip_card]
    assert runtime.game_state.players[0].hand_count == 0
    assert len(runtime.player_private_states["player-2"].hand) == 1
    assert len(runtime.player_private_states["player-3"].hand) == 1
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.turn_number == 2
    assert runtime.game_state.pending_draws == 1
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_play_skip_with_multiple_pending_draws_keeps_current_player_and_reduces_one_draw() -> None:
    runtime = build_runtime(pending_draws=3)
    skip_card = runtime.player_private_states["player-1"].hand[0]
    service = build_service(runtime)

    result = service.play_skip("room-1", "player-1", skip_card.card_id)

    assert result.outcome is TurnLifecycleOutcome.SKIP_PLAYED
    assert runtime.player_private_states["player-1"].hand == []
    assert runtime.game_state.discard_pile == [skip_card]
    assert runtime.game_state.players[0].hand_count == 0
    assert runtime.game_state.current_player_id == "player-1"
    assert runtime.game_state.turn_number == 1
    assert runtime.game_state.pending_draws == 2
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_play_attack_with_one_pending_draw_hands_two_draws_to_next_player() -> None:
    runtime = build_runtime(pending_draws=1)
    attack_card = card("attack-card", CardType.ATTACK)
    runtime.player_private_states["player-1"].hand = [attack_card]
    service = build_service(runtime)

    result = service.play_attack("room-1", "player-1", attack_card.card_id, request_id="request-1")

    assert result.outcome is TurnLifecycleOutcome.ATTACK_PLAYED
    assert result.runtime is runtime
    assert result.player_id == "player-1"
    assert result.request_id == "request-1"
    assert runtime.player_private_states["player-1"].hand == []
    assert runtime.game_state.discard_pile == [attack_card]
    assert runtime.game_state.players[0].hand_count == 0
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.turn_number == 2
    assert runtime.game_state.pending_draws == 2
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_play_attack_with_multiple_pending_draws_hands_old_value_plus_one_to_next_player() -> None:
    runtime = build_runtime(pending_draws=3)
    attack_card = card("attack-card", CardType.ATTACK)
    runtime.player_private_states["player-1"].hand = [attack_card]
    service = build_service(runtime)

    result = service.play_attack("room-1", "player-1", attack_card.card_id)

    assert result.outcome is TurnLifecycleOutcome.ATTACK_PLAYED
    assert runtime.game_state.discard_pile == [attack_card]
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.turn_number == 2
    assert runtime.game_state.pending_draws == 4
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_attack_chaining_preserves_stacking_policy() -> None:
    runtime = build_runtime(pending_draws=1)
    player_1_attack = card("player-1-attack", CardType.ATTACK)
    player_2_attack = card("player-2-attack", CardType.ATTACK)
    runtime.player_private_states["player-1"].hand = [player_1_attack]
    runtime.player_private_states["player-2"].hand = [player_2_attack]
    service = build_service(runtime)

    first_result = service.play_attack("room-1", "player-1", player_1_attack.card_id)
    second_result = service.play_attack("room-1", "player-2", player_2_attack.card_id)

    assert first_result.outcome is TurnLifecycleOutcome.ATTACK_PLAYED
    assert second_result.outcome is TurnLifecycleOutcome.ATTACK_PLAYED
    assert runtime.game_state.discard_pile == [player_1_attack, player_2_attack]
    assert runtime.game_state.players[0].hand_count == 0
    assert runtime.game_state.players[1].hand_count == 0
    assert runtime.game_state.current_player_id == "player-3"
    assert runtime.game_state.turn_number == 3
    assert runtime.game_state.pending_draws == 3


def test_play_skip_returns_game_finished_when_no_other_player_is_alive() -> None:
    runtime = build_runtime(
        pending_draws=1,
        statuses={
            "player-2": PlayerStatus.ELIMINATED,
            "player-3": PlayerStatus.ELIMINATED,
        },
        eliminated_player_ids=["player-2", "player-3"],
    )
    skip_card = runtime.player_private_states["player-1"].hand[0]
    service = build_service(runtime)

    result = service.play_skip("room-1", "player-1", skip_card.card_id)

    assert result.outcome is TurnLifecycleOutcome.GAME_FINISHED
    assert runtime.game_state.phase is GamePhase.FINISHED
    assert runtime.game_state.room_status is RoomStatus.FINISHED
    assert runtime.game_state.winner_player_id == "player-1"
    assert runtime.game_state.discard_pile == [skip_card]


def test_play_attack_returns_game_finished_when_no_other_player_is_alive() -> None:
    runtime = build_runtime(
        pending_draws=1,
        statuses={
            "player-2": PlayerStatus.ELIMINATED,
            "player-3": PlayerStatus.ELIMINATED,
        },
        eliminated_player_ids=["player-2", "player-3"],
    )
    attack_card = card("attack-card", CardType.ATTACK)
    runtime.player_private_states["player-1"].hand = [attack_card]
    service = build_service(runtime)

    result = service.play_attack("room-1", "player-1", attack_card.card_id)

    assert result.outcome is TurnLifecycleOutcome.GAME_FINISHED
    assert runtime.game_state.phase is GamePhase.FINISHED
    assert runtime.game_state.room_status is RoomStatus.FINISHED
    assert runtime.game_state.winner_player_id == "player-1"
    assert runtime.game_state.discard_pile == [attack_card]


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

    with pytest.raises(GameNotFoundError):
        service.play_skip("missing-room", "player-1", "card-1")

    with pytest.raises(GameNotFoundError):
        service.play_attack("missing-room", "player-1", "card-1")


def test_missing_player_is_rejected_without_state_mutation() -> None:
    runtime = build_runtime()

    assert_unchanged_after_error(runtime, PlayerNotFoundError, "missing-player")


def test_pending_explosion_card_rejects_draw_without_state_mutation() -> None:
    runtime = build_runtime()
    runtime.pending_explosion_card = card("pending-bomb", CardType.EXPLODING_KITTEN)

    assert_unchanged_after_error(runtime, PendingResolutionError, "player-1")


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
    ],
)
def test_invalid_action_card_requests_are_rejected_without_state_mutation(
    runtime: GameRuntimeState,
    player_id: str,
    error_type: type[Exception],
) -> None:
    assert_unchanged_after_action_error(runtime, error_type, player_id)


def test_missing_player_action_card_request_is_rejected_without_state_mutation() -> None:
    runtime = build_runtime()

    assert_unchanged_after_action_error(runtime, PlayerNotFoundError, "missing-player")


def test_pending_explosion_card_rejects_action_card_without_state_mutation() -> None:
    runtime = build_runtime()
    runtime.pending_explosion_card = card("pending-bomb", CardType.EXPLODING_KITTEN)

    assert_unchanged_after_action_error(runtime, PendingResolutionError, "player-1")


def test_card_not_in_hand_is_rejected_without_state_mutation() -> None:
    runtime = build_runtime()

    assert_unchanged_after_action_error(runtime, CardNotInHandError, "player-1", "missing-card")


def test_wrong_card_type_for_action_is_rejected_without_state_mutation() -> None:
    runtime = build_runtime()
    attack_card = card("attack-card", CardType.ATTACK)
    runtime.player_private_states["player-1"].hand = [attack_card]

    assert_unchanged_after_action_error(runtime, InvalidCardTypeError, "player-1", attack_card.card_id)


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


def test_resolving_explosion_with_defuse_consumes_one_defuse_and_advances_turn() -> None:
    bomb = card("bomb", CardType.EXPLODING_KITTEN)
    next_card = card("next-card", CardType.SKIP)
    defuse_card = card("defuse-card", CardType.DEFUSE)
    runtime = build_runtime(pending_draws=1, draw_pile=[next_card])
    prepare_pending_explosion(runtime, bomb)
    set_player_hand(runtime, "player-1", [defuse_card])
    service = build_service_with_random(runtime, index=1)

    result = service.resolve_pending_explosion("room-1", "player-1", request_id="request-1")

    assert result.outcome is TurnLifecycleOutcome.DEFUSED
    assert result.runtime is runtime
    assert result.player_id == "player-1"
    assert result.request_id == "request-1"
    assert runtime.pending_explosion_card is None
    assert runtime.player_private_states["player-1"].hand == []
    assert runtime.game_state.players[0].hand_count == 0
    assert runtime.game_state.discard_pile == [defuse_card]
    assert runtime.game_state.draw_pile == [next_card, bomb]
    assert runtime.game_state.action_lock is False
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.turn_number == 2
    assert runtime.game_state.pending_draws == 1
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_resolving_explosion_with_defuse_and_multiple_pending_draws_keeps_current_player() -> None:
    bomb = card("bomb", CardType.EXPLODING_KITTEN)
    next_card = card("next-card", CardType.SKIP)
    defuse_card = card("defuse-card", CardType.DEFUSE)
    second_defuse = card("second-defuse", CardType.DEFUSE)
    skip_card = card("skip-card", CardType.SKIP)
    runtime = build_runtime(pending_draws=3, draw_pile=[next_card])
    prepare_pending_explosion(runtime, bomb)
    set_player_hand(runtime, "player-1", [defuse_card, second_defuse, skip_card])
    service = build_service_with_random(runtime, index=0)

    result = service.resolve_pending_explosion("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.DEFUSED
    assert runtime.pending_explosion_card is None
    assert runtime.player_private_states["player-1"].hand == [second_defuse, skip_card]
    assert runtime.game_state.players[0].hand_count == 2
    assert runtime.game_state.discard_pile == [defuse_card]
    assert runtime.game_state.draw_pile == [bomb, next_card]
    assert runtime.game_state.action_lock is False
    assert runtime.game_state.current_player_id == "player-1"
    assert runtime.game_state.turn_number == 1
    assert runtime.game_state.pending_draws == 2
    assert runtime.game_state.phase is GamePhase.TURN_ACTION


def test_resolving_explosion_without_defuse_eliminates_player_and_advances_turn() -> None:
    bomb = card("bomb", CardType.EXPLODING_KITTEN)
    skip_card = card("skip-card", CardType.SKIP)
    favor_card = card("favor-card", CardType.FAVOR)
    runtime = build_runtime(pending_draws=2)
    prepare_pending_explosion(runtime, bomb)
    set_player_hand(runtime, "player-1", [skip_card, favor_card])
    runtime.player_private_states["player-1"].visible_future_cards = [CardType.ATTACK]
    service = build_service(runtime)

    result = service.resolve_pending_explosion("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.PLAYER_ELIMINATED
    assert runtime.pending_explosion_card is None
    assert runtime.game_state.players[0].status is PlayerStatus.ELIMINATED
    assert runtime.game_state.eliminated_player_ids == ["player-1"]
    assert runtime.game_state.discard_pile == [bomb, skip_card, favor_card]
    assert runtime.player_private_states["player-1"].hand == []
    assert runtime.player_private_states["player-1"].visible_future_cards is None
    assert runtime.game_state.players[0].hand_count == 0
    assert runtime.game_state.action_lock is False
    assert runtime.game_state.current_player_id == "player-2"
    assert runtime.game_state.turn_number == 2
    assert runtime.game_state.pending_draws == 1
    assert runtime.game_state.phase is GamePhase.TURN_ACTION
    assert runtime.game_state.room_status is RoomStatus.IN_GAME
    assert runtime.game_state.winner_player_id is None


def test_resolving_explosion_without_defuse_finishes_game_with_surviving_winner() -> None:
    bomb = card("bomb", CardType.EXPLODING_KITTEN)
    skip_card = card("skip-card", CardType.SKIP)
    runtime = build_runtime(
        statuses={"player-3": PlayerStatus.ELIMINATED},
        eliminated_player_ids=["player-3"],
    )
    prepare_pending_explosion(runtime, bomb)
    set_player_hand(runtime, "player-1", [skip_card])
    service = build_service(runtime)

    result = service.resolve_pending_explosion("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.GAME_FINISHED
    assert runtime.pending_explosion_card is None
    assert runtime.game_state.players[0].status is PlayerStatus.ELIMINATED
    assert runtime.game_state.eliminated_player_ids == ["player-3", "player-1"]
    assert runtime.game_state.discard_pile == [bomb, skip_card]
    assert runtime.player_private_states["player-1"].hand == []
    assert runtime.game_state.players[0].hand_count == 0
    assert runtime.game_state.action_lock is False
    assert runtime.game_state.phase is GamePhase.FINISHED
    assert runtime.game_state.room_status is RoomStatus.FINISHED
    assert runtime.game_state.winner_player_id == "player-2"
    assert runtime.game_state.current_player_id == "player-1"


def test_disconnected_current_player_still_resolves_pending_explosion() -> None:
    bomb = card("bomb", CardType.EXPLODING_KITTEN)
    defuse_card = card("defuse-card", CardType.DEFUSE)
    runtime = build_runtime(statuses={"player-1": PlayerStatus.DISCONNECTED})
    prepare_pending_explosion(runtime, bomb)
    set_player_hand(runtime, "player-1", [defuse_card])
    service = build_service_with_random(runtime, index=0)

    result = service.resolve_pending_explosion("room-1", "player-1")

    assert result.outcome is TurnLifecycleOutcome.DEFUSED
    assert runtime.pending_explosion_card is None
    assert runtime.game_state.discard_pile == [defuse_card]
    assert runtime.game_state.draw_pile[0] is bomb
    assert runtime.game_state.current_player_id == "player-2"


@pytest.mark.parametrize(
    ("runtime", "player_id", "error_type"),
    [
        (
            build_runtime(phase=GamePhase.RESOLVING_EXPLOSION, action_lock=True),
            "player-1",
            NoPendingExplosionError,
        ),
        (
            build_runtime(phase=GamePhase.TURN_ACTION, action_lock=True),
            "player-1",
            InvalidExplosionStateError,
        ),
        (
            build_runtime(phase=GamePhase.RESOLVING_EXPLOSION, action_lock=False),
            "player-1",
            InvalidExplosionStateError,
        ),
        (
            build_runtime(phase=GamePhase.RESOLVING_EXPLOSION, action_lock=True),
            "player-2",
            NotCurrentPlayerError,
        ),
        (
            build_runtime(
                phase=GamePhase.RESOLVING_EXPLOSION,
                action_lock=True,
                statuses={"player-1": PlayerStatus.ELIMINATED},
                eliminated_player_ids=["player-1"],
            ),
            "player-1",
            PlayerEliminatedError,
        ),
        (
            build_runtime(phase=GamePhase.RESOLVING_EXPLOSION, action_lock=True, pending_draws=0),
            "player-1",
            InvalidPendingDrawsError,
        ),
        (
            build_runtime(
                room_status=RoomStatus.FINISHED,
                phase=GamePhase.RESOLVING_EXPLOSION,
                action_lock=True,
            ),
            "player-1",
            GameNotInProgressError,
        ),
    ],
)
def test_invalid_explosion_resolution_requests_are_rejected_without_state_mutation(
    runtime: GameRuntimeState,
    player_id: str,
    error_type: type[Exception],
) -> None:
    if error_type is not NoPendingExplosionError:
        runtime.pending_explosion_card = card("pending-bomb", CardType.EXPLODING_KITTEN)

    assert_unchanged_after_explosion_error(runtime, error_type, player_id)


def test_missing_game_pending_explosion_resolution_raises_game_not_found() -> None:
    service = TurnLifecycleService(registry=GameRegistry())

    with pytest.raises(GameNotFoundError):
        service.resolve_pending_explosion("missing-room", "player-1")

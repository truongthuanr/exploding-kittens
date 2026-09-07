from collections import Counter
from copy import deepcopy

import pytest

from app.modules.game.errors import GameNotInProgressError, NotCurrentPlayerError
from app.modules.game.models import GameRuntimeState, TurnLifecycleOutcome
from app.modules.game.service import GameSetupService
from app.modules.room.registry import RoomRegistry
from app.modules.room.service import RoomService
from app.schemas.enums import CardType, GamePhase, PlayerStatus, RoomStatus
from test_turn_service import (
    build_runtime, build_service_with_random, build_service_with_reverse_shuffle,
    card, set_player_hand,
)


def inventory(runtime):
    cards = runtime.game_state.draw_pile + runtime.game_state.discard_pile + [
        card for private in runtime.player_private_states.values() for card in private.hand
    ]
    if runtime.pending_explosion_card is not None:
        cards = cards + [runtime.pending_explosion_card]
    return Counter(card.card_id for card in cards)


def assert_invariants(runtime, expected):
    state = runtime.game_state
    assert inventory(runtime) == expected
    assert all(count == 1 for count in expected.values())
    for player in state.players:
        assert player.hand_count == len(runtime.player_private_states[player.player_id].hand)
        if player.status is PlayerStatus.ELIMINATED:
            assert player.hand_count == 0
    if state.room_status is RoomStatus.IN_GAME:
        assert state.current_player_id not in state.eliminated_player_ids
        assert state.pending_draws >= 1
    if runtime.pending_explosion_card is None:
        assert not state.action_lock
    else:
        assert state.phase is GamePhase.RESOLVING_EXPLOSION
        assert state.action_lock


def test_attack_skip_draw_sequence_preserves_turns_and_cards():
    runtime = build_runtime()
    set_player_hand(runtime, "player-1", [card("attack", CardType.ATTACK)])
    service = build_service_with_random(runtime, 0)
    expected = inventory(runtime)
    service.play_attack("room-1", "player-1", "attack")
    assert_invariants(runtime, expected)
    assert (runtime.game_state.current_player_id, runtime.game_state.pending_draws,
            runtime.game_state.turn_number) == ("player-2", 2, 2)
    service.play_skip("room-1", "player-2", "player-2-hand")
    assert_invariants(runtime, expected)
    assert (runtime.game_state.current_player_id, runtime.game_state.pending_draws,
            runtime.game_state.turn_number) == ("player-2", 1, 2)
    service.draw_card("room-1", "player-2")
    assert_invariants(runtime, expected)
    assert (runtime.game_state.current_player_id, runtime.game_state.pending_draws,
            runtime.game_state.turn_number) == ("player-3", 1, 3)


def test_multiple_actions_before_draw_and_old_actor_rejected():
    runtime = build_runtime()
    set_player_hand(runtime, "player-1", [
        card("future", CardType.SEE_THE_FUTURE), card("shuffle", CardType.SHUFFLE),
    ])
    service = build_service_with_reverse_shuffle(runtime)
    expected = inventory(runtime)
    service.play_see_the_future("room-1", "player-1", "future")
    assert_invariants(runtime, expected)
    assert runtime.player_private_states["player-1"].visible_future_cards is not None
    service.play_shuffle("room-1", "player-1", "shuffle")
    assert_invariants(runtime, expected)
    assert runtime.player_private_states["player-1"].visible_future_cards is None
    assert runtime.game_state.current_player_id == "player-1"
    assert runtime.game_state.pending_draws == 1
    assert runtime.game_state.turn_number == 1
    assert [c.card_id for c in runtime.game_state.discard_pile] == ["future", "shuffle"]
    service.draw_card("room-1", "player-1")
    assert_invariants(runtime, expected)
    assert runtime.game_state.current_player_id == "player-2"
    before = deepcopy(runtime)
    with pytest.raises(NotCurrentPlayerError):
        service.play_skip("room-1", "player-1", runtime.player_private_states["player-1"].hand[0].card_id)
    assert runtime == before


@pytest.mark.parametrize("has_defuse", [True, False])
def test_attack_then_explosion_with_multiple_pending_draws(has_defuse):
    runtime = build_runtime(draw_pile=[card("bomb", CardType.EXPLODING_KITTEN)])
    set_player_hand(runtime, "player-1", [card("attack", CardType.ATTACK)])
    if has_defuse:
        set_player_hand(runtime, "player-2", [card("defuse", CardType.DEFUSE)])
    service = build_service_with_random(runtime, 0)
    expected = inventory(runtime)
    service.play_attack("room-1", "player-1", "attack")
    assert_invariants(runtime, expected)
    service.draw_card("room-1", "player-2")
    assert_invariants(runtime, expected)
    assert runtime.game_state.pending_draws == 2
    service.resolve_pending_explosion("room-1", "player-2")
    assert_invariants(runtime, expected)
    assert runtime.pending_explosion_card is None
    assert runtime.game_state.pending_draws == 1
    assert runtime.game_state.current_player_id == ("player-2" if has_defuse else "player-3")
    assert runtime.game_state.turn_number == (2 if has_defuse else 3)
    if has_defuse:
        assert [c.card_id for c in runtime.game_state.draw_pile] == ["bomb"]
        assert runtime.game_state.eliminated_player_ids == []
    else:
        assert runtime.game_state.draw_pile == []
        assert runtime.game_state.eliminated_player_ids == ["player-2"]


@pytest.mark.parametrize("player_count", [3, 4, 5])
def test_complete_match_through_services(player_count):
    rooms = RoomService(RoomRegistry())
    room = rooms.create_room("host").room
    for index in range(1, player_count):
        rooms.join_room(room.room_code, f"guest-{index}")
    for player in room.players:
        rooms.set_ready(room.room_id, player.player_id, True)
    rooms.transition_to_starting(room.room_id, room.host_player_id)
    runtime = GameRuntimeState.from_setup_result(
        GameSetupService(shuffler=lambda cards: cards.copy()).create_initial_game_state(room)
    )
    service = build_service_with_random(runtime, 0)
    expected = inventory(runtime)
    assert_invariants(runtime, expected)
    # Identity setup deals a Skip to the host for every supported player count.
    host_hand = runtime.player_private_states[room.host_player_id].hand
    skip = next(c for c in host_hand if c.card_type is CardType.SKIP)
    service.play_skip(room.room_id, room.host_player_id, skip.card_id)
    assert_invariants(runtime, expected)
    outcomes = []
    # Each draw either consumes a non-bomb, consumes a Defuse, or eliminates a player.
    for _ in range(100):
        actor = runtime.game_state.current_player_id
        service.draw_card(room.room_id, actor)
        assert_invariants(runtime, expected)
        if runtime.pending_explosion_card is not None:
            result = service.resolve_pending_explosion(room.room_id, actor)
            outcomes.append(result.outcome)
            assert_invariants(runtime, expected)
        if runtime.game_state.room_status is RoomStatus.FINISHED:
            break
    else:
        pytest.fail("Deterministic match did not finish within 100 draws")
    state = runtime.game_state
    survivors = [p.player_id for p in state.players if p.status is not PlayerStatus.ELIMINATED]
    assert survivors == [state.winner_player_id]
    assert len(state.eliminated_player_ids) == player_count - 1
    assert state.phase is GamePhase.FINISHED
    assert TurnLifecycleOutcome.DEFUSED in outcomes
    assert TurnLifecycleOutcome.PLAYER_ELIMINATED in outcomes
    assert outcomes[-1] is TurnLifecycleOutcome.GAME_FINISHED
    before = deepcopy(runtime)
    with pytest.raises(GameNotInProgressError):
        service.draw_card(room.room_id, state.winner_player_id)
    assert runtime == before

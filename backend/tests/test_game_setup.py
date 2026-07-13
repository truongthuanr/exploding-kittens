from app.modules.game.service import GameSetupService
from app.modules.room.models import RoomPlayerState, RoomState
from app.schemas.enums import CardType, GamePhase, RoomStatus


def identity_shuffler(cards):
    return cards.copy()


class StubGameSetupService(GameSetupService):
    def __init__(self) -> None:
        super().__init__(shuffler=identity_shuffler)
        self._card_ids = iter(f"card-{index}" for index in range(1, 128))

    def _generate_card_id(self) -> str:
        return next(self._card_ids)


def build_room(player_count: int) -> RoomState:
    players = [
        RoomPlayerState(
            player_id=f"player-{index}",
            nickname=f"player-{index}",
            is_ready=True,
        )
        for index in range(1, player_count + 1)
    ]
    return RoomState(
        room_id="room-1",
        room_code="ABCD12",
        host_player_id="player-1",
        players=players,
        status=RoomStatus.STARTING,
    )


def count_cards(card_type: CardType, cards) -> int:
    return sum(1 for card in cards if card.card_type is card_type)


def expected_draw_pile_size(player_count: int) -> int:
    return (2 * player_count + 22) - (5 * player_count)


def test_setup_uses_expected_exploding_kitten_count_for_supported_player_counts() -> None:
    for player_count, expected_bombs in [(3, 2), (4, 3), (5, 4)]:
        service = StubGameSetupService()

        result = service.create_initial_game_state(build_room(player_count))

        assert count_cards(CardType.EXPLODING_KITTEN, result.game_state.draw_pile) == expected_bombs


def test_setup_deals_five_cards_and_at_least_one_defuse_to_each_player() -> None:
    service = StubGameSetupService()

    result = service.create_initial_game_state(build_room(3))

    for player_private_state in result.player_private_states.values():
        assert len(player_private_state.hand) == 5
        assert count_cards(CardType.DEFUSE, player_private_state.hand) >= 1
        assert count_cards(CardType.EXPLODING_KITTEN, player_private_state.hand) == 0


def test_setup_appends_guaranteed_defuse_after_first_four_dealt_cards() -> None:
    service = StubGameSetupService()

    result = service.create_initial_game_state(build_room(3))

    for player_private_state in result.player_private_states.values():
        assert player_private_state.hand[-1].card_type is CardType.DEFUSE


def test_setup_allows_extra_defuse_in_initial_four_dealt_cards() -> None:
    service = StubGameSetupService()

    result = service.create_initial_game_state(build_room(3))
    host_hand = result.player_private_states["player-1"].hand

    assert host_hand[0].card_type is CardType.DEFUSE
    assert host_hand[-1].card_type is CardType.DEFUSE


def test_setup_initializes_turn_state_and_public_player_summaries() -> None:
    service = StubGameSetupService()

    result = service.create_initial_game_state(build_room(4))
    game_state = result.game_state

    assert game_state.room_status is RoomStatus.IN_GAME
    assert game_state.phase is GamePhase.TURN_ACTION
    assert game_state.turn_number == 1
    assert game_state.current_player_id == "player-1"
    assert game_state.pending_draws == 1
    assert game_state.discard_pile == []
    assert game_state.eliminated_player_ids == []
    assert game_state.winner_player_id is None
    assert game_state.action_lock is False
    assert game_state.players[0].is_host is True
    assert game_state.players[0].seat_index == 0
    assert game_state.players[0].hand_count == 5
    assert all(player.hand_count == 5 for player in game_state.players)
    assert game_state.created_at == game_state.updated_at


def test_setup_draw_pile_size_matches_remaining_cards_after_dealing() -> None:
    for player_count in (3, 4, 5):
        service = StubGameSetupService()

        result = service.create_initial_game_state(build_room(player_count))

        assert len(result.game_state.draw_pile) == expected_draw_pile_size(player_count)

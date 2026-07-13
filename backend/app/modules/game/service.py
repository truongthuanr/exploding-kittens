from __future__ import annotations

from dataclasses import dataclass, field
from random import SystemRandom
from typing import Callable
from uuid import uuid4

from app.modules.game.models import (
    CardInstance,
    GamePlayerSummary,
    GameSetupResult,
    PlayerPrivateState,
    ServerGameState,
    utc_now_iso,
)
from app.modules.room.constants import MAX_ROOM_PLAYERS, MIN_ROOM_PLAYERS
from app.modules.room.models import RoomState
from app.schemas.enums import CardType, GamePhase, RoomStatus

DEALT_NON_DEFUSE_CARDS_PER_PLAYER = 4
STARTING_DECK_EXTRA_DEFUSE = 2
STARTING_SKIP_CARDS = 4
STARTING_ATTACK_CARDS = 4
STARTING_SHUFFLE_CARDS = 4
STARTING_SEE_THE_FUTURE_CARDS = 5
STARTING_FAVOR_CARDS = 4

type Shuffler = Callable[[list[CardInstance]], list[CardInstance]]


def default_shuffler(cards: list[CardInstance]) -> list[CardInstance]:
    shuffled = cards.copy()
    SystemRandom().shuffle(shuffled)
    return shuffled


@dataclass(slots=True)
class GameSetupService:
    shuffler: Shuffler = field(default=default_shuffler)

    def create_initial_game_state(self, room: RoomState) -> GameSetupResult:
        """Create authoritative setup output for a new match.

        Returns both the initial ``ServerGameState`` and the per-player
        ``PlayerPrivateState`` values derived from the room state.
        """
        
        # Validate player count
        player_count = len(room.players)
        if player_count < MIN_ROOM_PLAYERS or player_count > MAX_ROOM_PLAYERS:
            raise ValueError(f"Unsupported player count for game setup: {player_count}")

        reserved_defuses = [self._create_card(CardType.DEFUSE) for _ in room.players]
        non_bomb_deck = self._build_non_bomb_deck(player_count)
        shuffled_non_bomb_deck = self.shuffler(non_bomb_deck)

        player_private_states: dict[str, PlayerPrivateState] = {}
        players: list[GamePlayerSummary] = []

        for seat_index, room_player in enumerate(room.players):
            # Deal each player four shuffled non-bomb cards, then add their
            # reserved defuse as the fifth starting card in hand.
            dealt_cards, shuffled_non_bomb_deck = self._draw_cards(
                shuffled_non_bomb_deck,
                DEALT_NON_DEFUSE_CARDS_PER_PLAYER,
            )
            hand = dealt_cards + [reserved_defuses[seat_index]]
            player_private_states[room_player.player_id] = PlayerPrivateState(
                player_id=room_player.player_id,
                hand=hand,
            )
            # Expose only summary data in the server game state; the actual
            # hand contents stay in each player's private state.
            players.append(
                GamePlayerSummary(
                    player_id=room_player.player_id,
                    nickname=room_player.nickname,
                    status=room_player.status,
                    hand_count=len(hand),
                    seat_index=seat_index,
                    is_host=room.is_host_player(room_player.player_id),
                    is_ready=room_player.is_ready,
                )
            )

        draw_pile = shuffled_non_bomb_deck + self._build_exploding_kittens(player_count)
        draw_pile = self.shuffler(draw_pile)
        now = utc_now_iso()

        game_state = ServerGameState(
            room_id=room.room_id,
            room_status=RoomStatus.IN_GAME,
            phase=GamePhase.TURN_ACTION,
            turn_number=1,
            current_player_id=room.host_player_id,
            pending_draws=1,
            players=players,
            draw_pile=draw_pile,
            discard_pile=[],
            eliminated_player_ids=[],
            winner_player_id=None,
            action_lock=False,
            created_at=now,
            updated_at=now,
        )
        return GameSetupResult(
            game_state=game_state,
            player_private_states=player_private_states,
        )

    def _build_non_bomb_deck(self, player_count: int) -> list[CardInstance]:
        deck: list[CardInstance] = []
        deck.extend(self._create_cards(CardType.DEFUSE, STARTING_DECK_EXTRA_DEFUSE))
        deck.extend(self._create_cards(CardType.SKIP, STARTING_SKIP_CARDS))
        deck.extend(self._create_cards(CardType.ATTACK, STARTING_ATTACK_CARDS))
        deck.extend(self._create_cards(CardType.SHUFFLE, STARTING_SHUFFLE_CARDS))
        deck.extend(self._create_cards(CardType.SEE_THE_FUTURE, STARTING_SEE_THE_FUTURE_CARDS))
        deck.extend(self._create_cards(CardType.FAVOR, STARTING_FAVOR_CARDS))
        required_cards = player_count * DEALT_NON_DEFUSE_CARDS_PER_PLAYER
        if len(deck) < required_cards:
            raise ValueError("Not enough non-bomb cards to deal the starting hands")
        return deck

    def _build_exploding_kittens(self, player_count: int) -> list[CardInstance]:
        return self._create_cards(CardType.EXPLODING_KITTEN, player_count - 1)

    def _draw_cards(
        self,
        deck: list[CardInstance],
        count: int,
    ) -> tuple[list[CardInstance], list[CardInstance]]:
        if len(deck) < count:
            raise ValueError(f"Not enough cards in deck to draw {count} cards")
        return deck[:count], deck[count:]

    def _create_cards(self, card_type: CardType, count: int) -> list[CardInstance]:
        return [self._create_card(card_type) for _ in range(count)]

    def _create_card(self, card_type: CardType) -> CardInstance:
        return CardInstance(card_id=self._generate_card_id(), card_type=card_type)

    def _generate_card_id(self) -> str:
        return str(uuid4())

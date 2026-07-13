from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.enums import CardType, GamePhase, PlayerStatus, RoomStatus


@dataclass(slots=True)
class CardInstance:
    card_id: str
    card_type: CardType


@dataclass(slots=True)
class PlayerPrivateState:
    player_id: str
    hand: list[CardInstance]
    visible_future_cards: list[CardType] | None = None


@dataclass(slots=True)
class GamePlayerSummary:
    player_id: str
    nickname: str
    status: PlayerStatus
    hand_count: int
    seat_index: int
    is_host: bool
    is_ready: bool


@dataclass(slots=True)
class ServerGameState:
    room_id: str
    room_status: RoomStatus
    phase: GamePhase
    turn_number: int
    current_player_id: str
    pending_draws: int
    players: list[GamePlayerSummary]
    draw_pile: list[CardInstance]
    discard_pile: list[CardInstance]
    eliminated_player_ids: list[str]
    winner_player_id: str | None
    action_lock: bool
    created_at: str
    updated_at: str


@dataclass(slots=True)
class GameSetupResult:
    game_state: ServerGameState
    player_private_states: dict[str, PlayerPrivateState]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()

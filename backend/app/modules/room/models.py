from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.schemas.enums import PlayerStatus, RoomStatus
from app.schemas.responses import RoomPlayer, RoomUpdatedEvent


@dataclass(slots=True)
class RoomPlayerState:
    player_id: str
    nickname: str
    is_ready: bool = False
    status: PlayerStatus = PlayerStatus.CONNECTED

    def to_room_player(self, *, is_host: bool) -> RoomPlayer:
        return RoomPlayer(
            playerId=self.player_id,
            nickname=self.nickname,
            isReady=self.is_ready,
            isHost=is_host,
            status=self.status,
        )


@dataclass(slots=True)
class RoomState:
    room_id: str
    room_code: str
    host_player_id: str
    players: list[RoomPlayerState]
    status: RoomStatus = RoomStatus.WAITING
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def get_player(self, player_id: str) -> RoomPlayerState | None:
        return next((player for player in self.players if player.player_id == player_id), None)

    def has_nickname(self, nickname: str) -> bool:
        return any(player.nickname == nickname for player in self.players)

    def is_joinable(self) -> bool:
        return self.status == RoomStatus.WAITING

    def is_host_player(self, player_id: str) -> bool:
        return self.host_player_id == player_id

    def to_room_updated_event(self) -> RoomUpdatedEvent:
        return RoomUpdatedEvent(
            roomId=self.room_id,
            roomCode=self.room_code,
            status=self.status,
            players=[
                player.to_room_player(is_host=self.is_host_player(player.player_id))
                for player in self.players
            ],
        )

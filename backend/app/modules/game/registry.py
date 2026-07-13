from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.game.models import ServerGameState


@dataclass(slots=True)
class GameRegistry:
    games_by_room_id: dict[str, ServerGameState] = field(default_factory=dict)

    def add(self, game_state: ServerGameState) -> None:
        self.games_by_room_id[game_state.room_id] = game_state

    def get(self, room_id: str) -> ServerGameState | None:
        return self.games_by_room_id.get(room_id)

    def remove(self, room_id: str) -> ServerGameState | None:
        return self.games_by_room_id.pop(room_id, None)

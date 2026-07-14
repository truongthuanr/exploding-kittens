from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.game.models import GameRuntimeState


@dataclass(slots=True)
class GameRegistry:
    games_by_room_id: dict[str, GameRuntimeState] = field(default_factory=dict)

    def add(self, runtime: GameRuntimeState) -> None:
        self.games_by_room_id[runtime.game_state.room_id] = runtime

    def get(self, room_id: str) -> GameRuntimeState | None:
        return self.games_by_room_id.get(room_id)

    def remove(self, room_id: str) -> GameRuntimeState | None:
        return self.games_by_room_id.pop(room_id, None)

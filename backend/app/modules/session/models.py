from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class PlayerSession:
    player_session_id: str
    player_id: str
    room_id: str
    socket_id: str | None = None
    connected: bool = False
    last_seen_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def bind_socket(self, socket_id: str) -> None:
        self.socket_id = socket_id

    def unbind_socket(self) -> None:
        self.socket_id = None

    def mark_connected(self) -> None:
        self.connected = True

    def mark_disconnected(self) -> None:
        self.connected = False

    def touch_last_seen(self) -> None:
        self.last_seen_at = datetime.now(UTC).isoformat()

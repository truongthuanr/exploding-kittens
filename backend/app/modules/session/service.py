from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.modules.session.models import PlayerSession
from app.modules.session.registry import SessionRegistry


@dataclass(slots=True)
class SessionService:
    registry: SessionRegistry

    def create_session(self, player_id: str, room_id: str) -> PlayerSession:
        session = PlayerSession(
            player_session_id=self._generate_session_id(),
            player_id=player_id,
            room_id=room_id,
        )
        self.registry.add(session)
        return session

    def bind_socket(self, player_session_id: str, socket_id: str) -> PlayerSession:
        session = self.registry.get_by_id(player_session_id)
        if session.socket_id is not None and session.connected:
            raise ValueError(f"Session already has an active socket binding: {player_session_id}")

        session = self.registry.bind_socket(player_session_id, socket_id)
        session.mark_connected()
        session.touch_last_seen()
        return session

    def unbind_socket(self, socket_id: str) -> PlayerSession | None:
        session = self.registry.unbind_socket(socket_id)
        if session is None:
            return None

        session.mark_disconnected()
        session.touch_last_seen()
        return session

    def rebind_socket(self, player_session_id: str, socket_id: str) -> PlayerSession:
        session = self.registry.get_by_id(player_session_id)
        old_socket_id = session.socket_id
        if old_socket_id is not None:
            self.registry.unbind_socket(old_socket_id)

        session = self.registry.bind_socket(player_session_id, socket_id)
        session.mark_connected()
        session.touch_last_seen()
        return session

    def get_session(self, player_session_id: str) -> PlayerSession:
        return self.registry.get_by_id(player_session_id)

    def get_session_by_socket(self, socket_id: str) -> PlayerSession | None:
        return self.registry.get_by_socket(socket_id)

    def get_session_by_player(self, room_id: str, player_id: str) -> PlayerSession | None:
        return self.registry.get_by_player(room_id, player_id)

    def _generate_session_id(self) -> str:
        return str(uuid4())

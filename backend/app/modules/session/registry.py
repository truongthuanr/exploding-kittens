from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.session.errors import SessionNotFoundError
from app.modules.session.models import PlayerSession


@dataclass(slots=True)
class SessionRegistry:
    sessions_by_id: dict[str, PlayerSession] = field(default_factory=dict)
    session_id_by_socket: dict[str, str] = field(default_factory=dict)

    def add(self, session: PlayerSession) -> None:
        self.sessions_by_id[session.player_session_id] = session

    def get_by_id(self, player_session_id: str) -> PlayerSession:
        session = self.sessions_by_id.get(player_session_id)
        if session is None:
            raise SessionNotFoundError(player_session_id)
        return session

    def get_by_socket(self, socket_id: str) -> PlayerSession | None:
        player_session_id = self.session_id_by_socket.get(socket_id)
        if player_session_id is None:
            return None
        return self.get_by_id(player_session_id)

    def get_by_player(self, room_id: str, player_id: str) -> PlayerSession | None:
        for session in self.sessions_by_id.values():
            if session.room_id == room_id and session.player_id == player_id:
                return session
        return None

    def remove(self, player_session_id: str) -> PlayerSession:
        session = self.get_by_id(player_session_id)
        if session.socket_id is not None:
            self.session_id_by_socket.pop(session.socket_id, None)
        del self.sessions_by_id[player_session_id]
        return session

    def bind_socket(self, player_session_id: str, socket_id: str) -> PlayerSession:
        session = self.get_by_id(player_session_id)
        session.bind_socket(socket_id)
        self.session_id_by_socket[socket_id] = player_session_id
        return session

    def unbind_socket(self, socket_id: str) -> PlayerSession | None:
        player_session_id = self.session_id_by_socket.pop(socket_id, None)
        if player_session_id is None:
            return None

        session = self.get_by_id(player_session_id)
        session.unbind_socket()
        return session

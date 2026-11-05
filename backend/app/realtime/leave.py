"""Bounded terminal leave results, independent of live room/session registries."""

from dataclasses import dataclass
from time import time

from app.schemas.responses import LeaveRoomAck

TTL_MS = 600_000
MAX_ENTRIES = 10_000


class LeaveReplayError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LeaveResult:
    player_session_id: str
    room_id: str
    request_id: str
    expires_at_ms: int
    ack: dict


class LeaveResultCache:
    def __init__(self) -> None:
        self.by_request_id: dict[str, LeaveResult] = {}
        self.by_session_id: dict[str, LeaveResult] = {}

    def _prune(self) -> None:
        now = int(time() * 1000)
        self.by_request_id = {key: result for key, result in self.by_request_id.items()
                              if result.expires_at_ms > now}
        self.by_session_id = {key: result for key, result in self.by_session_id.items()
                              if result.expires_at_ms > now}

    def lookup_request(self, player_session_id: str, request_id: str) -> LeaveResult | None:
        self._prune()
        result = self.by_request_id.get(request_id)
        if result and result.player_session_id != player_session_id:
            raise LeaveReplayError("request_conflict", "Request ID belongs to another player session")
        if result is None and len(self.by_request_id) >= MAX_ENTRIES:
            raise LeaveReplayError("post_game_busy", "Leave result cache is full; retry later")
        return result

    def lookup_session(self, player_session_id: str) -> LeaveResult | None:
        self._prune()
        return self.by_session_id.get(player_session_id)

    def remember(self, player_session_id: str, room_id: str, request_id: str) -> LeaveResult:
        expires_at = int(time() * 1000) + TTL_MS
        ack = LeaveRoomAck(requestId=request_id, roomId=room_id,
                           replayUntilMs=expires_at).model_dump(mode="json")
        result = LeaveResult(player_session_id, room_id, request_id, expires_at, ack)
        self.by_request_id[request_id] = result
        self.by_session_id[player_session_id] = result
        return result

"""Process-local rematch request replay, retained after the game runtime is reset."""

from dataclasses import dataclass
from time import time

TTL_MS = 600_000
MAX_ENTRIES = 10_000


class RematchReplayError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RematchResult:
    choice: str
    ack: dict
    expires_at_ms: int


class RematchReplayCache:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str, int, str], RematchResult] = {}

    def lookup(self, key: tuple[str, str, int, str], choice: str) -> RematchResult | None:
        now = int(time() * 1000)
        self.entries = {entry_key: result for entry_key, result in self.entries.items()
                        if result.expires_at_ms > now}
        result = self.entries.get(key)
        if result and result.choice != choice:
            raise RematchReplayError("request_conflict", "Request ID was used for a different rematch choice")
        if result is None and len(self.entries) >= MAX_ENTRIES:
            raise RematchReplayError("post_game_busy", "Rematch request cache is full; retry later")
        return result

    def remember(self, key: tuple[str, str, int, str], choice: str, ack: dict) -> None:
        self.entries[key] = RematchResult(choice, ack, int(time() * 1000) + TTL_MS)

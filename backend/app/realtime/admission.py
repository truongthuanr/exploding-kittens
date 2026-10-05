"""Bounded, process-local admission replay cache (not live game persistence)."""
from dataclasses import dataclass
from time import time
from uuid import UUID, uuid4

EPOCH = uuid4().hex
TTL_MS = 120_000
MAX_ENTRIES = 1_000


class AdmissionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Entry:
    fingerprint: tuple
    session_id: str
    expires_at: int


class AdmissionCache:
    def __init__(self):
        self.entries: dict[str, Entry] = {}

    def lookup(self, request_id: str, fingerprint: tuple) -> Entry | None:
        now = int(time() * 1000)
        self.entries = {key: value for key, value in self.entries.items() if value.expires_at > now}
        try:
            epoch, timestamp, nonce = request_id.split(":")
            issued = int(timestamp)
            UUID(nonce)
        except (ValueError, TypeError):
            raise AdmissionError("invalid_request_id", "Use the connection epoch, server time and a UUID") from None
        if epoch != EPOCH:
            raise AdmissionError("server_restarted", "Backend restarted; the previous admission cannot be recovered")
        if issued > now + 5_000 or issued + TTL_MS <= now:
            raise AdmissionError("request_expired", "Admission request expired; do not retry it as a new request")
        entry = self.entries.get(request_id)
        if entry and entry.fingerprint != fingerprint:
            raise AdmissionError("request_conflict", "Request ID belongs to a different payload or client")
        if entry is None and len(self.entries) >= MAX_ENTRIES:
            # Never evict a still-valid result, which could turn a replay into a new admission.
            raise AdmissionError("admission_busy", "Admission cache is full; try later")
        return entry

    def remember(self, request_id: str, fingerprint: tuple, session_id: str):
        self.entries[request_id] = Entry(fingerprint, session_id, int(request_id.split(":")[1]) + TTL_MS)

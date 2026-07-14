import asyncio

from app.realtime.server import validate_socket_payload
from app.schemas import RoomCreateRequest


def test_validate_socket_payload_accepts_valid_request() -> None:
    async def run_validation() -> RoomCreateRequest | None:
        return await validate_socket_payload(
            sid="sid-1",
            event_name="room:create",
            data={"nickname": "alice"},
        )

    payload = asyncio.run(run_validation())

    assert payload is not None
    assert isinstance(payload, RoomCreateRequest)
    assert payload.nickname == "alice"


def test_validate_socket_payload_emits_error_for_invalid_request(monkeypatch) -> None:
    captured: list[tuple[str, dict, str]] = []

    async def fake_emit(event: str, data: dict, to: str) -> None:
        captured.append((event, data, to))

    monkeypatch.setattr("app.realtime.server.sio.emit", fake_emit)

    async def run_validation() -> None:
        payload = await validate_socket_payload(
            sid="sid-2",
            event_name="room:create",
            data={},
        )
        assert payload is None

    asyncio.run(run_validation())

    assert captured == [
        (
            "error",
            {
                "code": "invalid_payload",
                "message": "Invalid payload for room:create (1 validation error(s))",
            },
            "sid-2",
        )
    ]

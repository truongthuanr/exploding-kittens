from copy import deepcopy

import pytest

from app.modules.session.errors import SessionNotFoundError
from app.modules.session.registry import SessionRegistry
from app.modules.session.service import SessionService


class StubSessionService(SessionService):
    def __init__(self) -> None:
        super().__init__(registry=SessionRegistry())
        self._session_ids = iter(["session-1", "session-2", "session-3"])

    def _generate_session_id(self) -> str:
        return next(self._session_ids)


def test_create_session_stores_session_in_registry() -> None:
    service = StubSessionService()

    session = service.create_session("player-1", "room-1")

    assert session.player_session_id == "session-1"
    assert session.player_id == "player-1"
    assert session.room_id == "room-1"
    assert service.registry.get_by_id("session-1") is session


def test_get_session_by_socket_returns_none_when_socket_is_not_bound() -> None:
    service = StubSessionService()

    assert service.get_session_by_socket("missing-socket") is None


def test_get_session_by_player_returns_matching_room_player_session() -> None:
    service = StubSessionService()
    session = service.create_session("player-1", "room-1")
    service.create_session("player-1", "room-2")

    assert service.get_session_by_player("room-1", "player-1") is session
    assert service.get_session_by_player("room-1", "missing-player") is None


def test_bind_socket_binds_session_and_marks_it_connected() -> None:
    service = StubSessionService()
    session = service.create_session("player-1", "room-1")

    bound = service.bind_socket(session.player_session_id, "sid-1")

    assert bound is session
    assert bound.socket_id == "sid-1"
    assert bound.connected is True
    assert service.get_session_by_socket("sid-1") is bound


def test_bind_socket_rejects_active_binding() -> None:
    service = StubSessionService()
    session = service.create_session("player-1", "room-1")
    service.bind_socket(session.player_session_id, "sid-1")

    with pytest.raises(ValueError):
        service.bind_socket(session.player_session_id, "sid-2")


def test_unbind_socket_clears_binding_without_deleting_session() -> None:
    service = StubSessionService()
    session = service.create_session("player-1", "room-1")
    service.bind_socket(session.player_session_id, "sid-1")

    unbound = service.unbind_socket("sid-1")

    assert unbound is session
    assert unbound.socket_id is None
    assert unbound.connected is False
    assert service.get_session(session.player_session_id) is session
    assert service.get_session_by_socket("sid-1") is None


def test_unbind_socket_returns_none_for_unknown_socket() -> None:
    service = StubSessionService()

    assert service.unbind_socket("missing-socket") is None


def test_rebind_socket_reassigns_same_session_to_new_socket() -> None:
    service = StubSessionService()
    session = service.create_session("player-1", "room-1")
    service.bind_socket(session.player_session_id, "sid-1")

    rebound = service.rebind_socket(session.player_session_id, "sid-2")

    assert rebound is session
    assert rebound.socket_id == "sid-2"
    assert rebound.connected is True
    assert service.get_session_by_socket("sid-1") is None
    assert service.get_session_by_socket("sid-2") is rebound


def test_get_session_raises_when_session_does_not_exist() -> None:
    service = StubSessionService()

    with pytest.raises(SessionNotFoundError):
        service.get_session("missing-session")


def test_old_socket_disconnect_after_takeover_preserves_new_binding() -> None:
    service = StubSessionService()
    session = service.create_session("player-1", "room-1")
    service.bind_socket(session.player_session_id, "old")
    service.rebind_socket(session.player_session_id, "new")
    before = deepcopy(service.registry)
    assert service.unbind_socket("old") is None
    assert service.registry == before
    assert service.get_session_by_socket("new") is session
    assert session.connected


@pytest.mark.parametrize("operation", ["bind_socket", "rebind_socket"])
def test_socket_conflict_is_rejected_without_changing_either_session(operation) -> None:
    service = StubSessionService()
    first = service.create_session("player-1", "room-1")
    second = service.create_session("player-2", "room-2")
    service.bind_socket(first.player_session_id, "occupied")
    if operation == "rebind_socket":
        service.bind_socket(second.player_session_id, "original")
    before = deepcopy(service.registry)
    with pytest.raises(ValueError, match="Socket already"):
        getattr(service, operation)(second.player_session_id, "occupied")
    assert service.registry == before


def test_remove_session_cleans_index_without_affecting_other_session() -> None:
    service = StubSessionService()
    first = service.create_session("player-1", "room-1")
    second = service.create_session("player-2", "room-1")
    service.bind_socket(first.player_session_id, "first")
    service.bind_socket(second.player_session_id, "second")
    before = deepcopy(second)
    assert service.registry.remove(first.player_session_id) is first
    with pytest.raises(SessionNotFoundError):
        service.get_session(first.player_session_id)
    assert service.get_session_by_socket("first") is None
    assert service.get_session_by_socket("second") is second
    assert second == before

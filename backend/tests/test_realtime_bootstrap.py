import asyncio
from collections import OrderedDict
from time import time
from uuid import uuid4

import pytest

from app.realtime import server
from app.realtime.admission import AdmissionCache, EPOCH, TTL_MS
from app.modules.room import RoomRegistry, RoomService
from app.modules.session import SessionRegistry, SessionService
from app.modules.game import GameRegistry


def request_id(timestamp=None, epoch=EPOCH):
    return f"{epoch}:{timestamp if timestamp is not None else int(time() * 1000)}:{uuid4()}"


def admission(nickname="Alice", instance="tab-a", **extra):
    return {"nickname": nickname, "clientInstanceId": instance, "requestId": request_id(), **extra}


def restore(result, instance="tab-a", takeover=False):
    return {"playerSessionId": result["playerSessionId"], "clientInstanceId": instance,
            "attemptId": str(uuid4()), "takeover": takeover}


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(server, "gateway_lock", asyncio.Lock())
    monkeypatch.setattr(server, "room_action_locks", {})
    monkeypatch.setattr(server, "processed_request_ids", OrderedDict())
    monkeypatch.setattr(server, "room_service", RoomService(RoomRegistry()))
    monkeypatch.setattr(server, "session_service", SessionService(SessionRegistry()))
    monkeypatch.setattr(server, "game_registry", GameRegistry())
    monkeypatch.setattr(server, "admission_cache", AdmissionCache())
    events = []
    async def emit(event, data, **target):
        events.append((event, data, target))
        await asyncio.sleep(0)  # expose ordering bugs at actual network await boundaries
    async def enter(*args):
        await asyncio.sleep(0)
    async def disconnect(sid):
        await server.disconnect(sid)
    monkeypatch.setattr(server.sio, "emit", emit)
    monkeypatch.setattr(server.sio, "enter_room", enter)
    monkeypatch.setattr(server.sio, "disconnect", disconnect)
    return events


def test_lost_ack_replay_is_idempotent_and_returns_current_snapshot(gateway):
    async def run():
        payload = admission()
        first, duplicate = await asyncio.gather(server.handle_room_create("a", payload), server.handle_room_create("a", payload))
        assert first["playerSessionId"] == duplicate["playerSessionId"]
        await server.handle_room_ready("a", {"isReady": True})
        await server.disconnect("a")
        recovered = await server.handle_room_create("new", payload)
        assert recovered["room"]["players"][0]["isReady"] is True
        assert recovered["room"]["players"][0]["status"] == "connected"
        assert recovered["stateVersion"] > first["stateVersion"]
        assert recovered["game"] is None and recovered["private"] is None
        assert len(server.session_service.registry.sessions_by_id) == 1
        assert server.session_service.get_session_by_socket("new").player_id == first["playerId"]
    asyncio.run(run())


def test_join_retry_and_conflicting_payload(gateway):
    async def run():
        host = await server.handle_room_create("a", admission())
        payload = admission("Bob", "tab-b", roomCode=host["roomCode"])
        joined = await server.handle_room_join("b", payload)
        replay = await server.handle_room_join("b", payload)
        assert replay["playerSessionId"] == joined["playerSessionId"]
        assert len(replay["room"]["players"]) == 2
        assert await server.handle_room_join("b", {**payload, "nickname": "Changed"}) is None
        assert gateway[-1][1]["code"] == "request_conflict"
        assert gateway[-1][1]["requestId"] == payload["requestId"]
    asyncio.run(run())


def test_request_expired_restart_and_capacity_do_not_create_players(gateway, monkeypatch):
    async def run():
        for key, code in [(request_id(int(time()*1000) - TTL_MS - 1), "request_expired"),
                          (request_id(epoch="previous-process"), "server_restarted")]:
            assert await server.handle_room_create("a", admission(requestId=key)) is None
            assert gateway[-1][1]["code"] == code
        assert not server.session_service.registry.sessions_by_id
        monkeypatch.setattr("app.realtime.admission.MAX_ENTRIES", 1)
        first = admission()
        result = await server.handle_room_create("a", first)
        assert await server.handle_room_create("b", admission("Bob", "tab-b")) is None
        assert gateway[-1][1]["code"] == "admission_busy"
        assert (await server.handle_room_create("a", first))["playerId"] == result["playerId"]
    asyncio.run(run())


def test_offline_owner_cannot_reclaim_after_takeover(gateway):
    async def run():
        first = await server.handle_room_create("a", admission())
        await server.disconnect("a")
        blocked = restore(first, "tab-b")
        assert await server.handle_player_reconnect("b", blocked) is None
        assert gateway[-1][1]["code"] == "session_in_use"
        assert gateway[-1][1]["requestId"] == blocked["attemptId"]
        result = await server.handle_player_reconnect("b", restore(first, "tab-b", True))
        assert result["playerId"] == first["playerId"]
        assert await server.handle_player_reconnect("a2", restore(first)) is None
        assert gateway[-1][1]["code"] == "session_in_use"
        assert server.session_service.get_session_by_socket("b") is not None
    asyncio.run(run())


def test_online_takeover_disconnect_does_not_unbind_new_owner(gateway):
    async def run():
        first = await server.handle_room_create("a", admission())
        assert await server.handle_player_reconnect("clone", restore(first)) is None
        result = await asyncio.wait_for(server.handle_player_reconnect("b", restore(first, "tab-b", True)), 2)
        assert result["playerId"] == first["playerId"]
        assert server.session_service.get_session_by_socket("a") is None
        assert server.session_service.get_session_by_socket("b") is not None
        assert any(event == "session:replaced" and target["to"] == "a" for event, _, target in gateway)
        # Omitting the modern fields must not bypass ownership.
        assert await server.handle_player_reconnect("legacy", {"playerSessionId": first["playerSessionId"]}) is None
    asyncio.run(run())


def test_admission_replay_recovers_identity_without_silent_takeover(gateway):
    async def run():
        payload = admission()
        first = await server.handle_room_create("a", payload)
        replay = await server.handle_room_create("new", payload)
        assert replay["requiresTakeover"] is True
        assert replay["playerSessionId"] == first["playerSessionId"]
        assert server.session_service.get_session_by_socket("a") is not None
        assert server.session_service.get_session_by_socket("new") is None
    asyncio.run(run())


def test_concurrent_takeovers_leave_one_binding(gateway):
    async def run():
        first = await server.handle_room_create("a", admission())
        await asyncio.gather(*(server.handle_player_reconnect(sid, restore(first, sid, True)) for sid in ["b", "c"]))
        session = server.session_service.get_session(first["playerSessionId"])
        assert session.socket_id in ("b", "c")
        assert len(server.session_service.registry.session_id_by_socket) == 1
    asyncio.run(run())


def test_bootstrap_serializes_with_actions_and_only_returns_own_hand(gateway):
    async def run():
        players = [await server.handle_room_create("a", admission())]
        for sid in ["b", "c"]:
            players.append(await server.handle_room_join(sid, admission(sid, sid, roomCode=players[0]["roomCode"])))
        for sid in ["a", "b", "c"]:
            await server.handle_room_ready(sid, {"isReady": True})
        await server.handle_game_start("a", {})
        initial = server.bootstrap(server.session_service.get_session(players[0]["playerSessionId"]))
        request = restore(players[0])
        result, _ = await asyncio.gather(server.handle_player_reconnect("a", request),
                                         server.handle_turn_draw_card("a", {"requestId": "draw-once"}))
        assert result["attemptId"] == request["attemptId"]
        assert result["stateVersion"] == result["game"]["stateVersion"] == result["private"]["stateVersion"]
        assert result["private"]["playerId"] == initial["playerId"]
        assert result["private"]["hand"] == initial["private"]["hand"]
        assert "hand" not in str(result["game"] .keys())
        assert "drawPile" not in result["game"]
        runtime = server.game_registry.get(initial["roomId"])
        other_ids = {card.card_id for pid, private in runtime.player_private_states.items()
                     if pid != initial["playerId"] for card in private.hand}
        assert not any(card_id in str(result) for card_id in other_ids)
        assert server.room_service.registry.get_by_id(initial["roomId"]).state_version > result["stateVersion"]
    asyncio.run(run())

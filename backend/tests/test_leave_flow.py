import asyncio
from time import time
from uuid import uuid4

import pytest

from app.modules.game import GameRegistry
from app.modules.room import RoomRegistry, RoomService
from app.modules.session import SessionRegistry, SessionService
from app.realtime import server
from app.realtime.admission import AdmissionCache, EPOCH
from app.realtime.leave import LeaveResultCache, TTL_MS
from app.realtime.rematch import RematchReplayCache
from app.schemas import GamePhase, RoomStatus


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(server, "gateway_lock", asyncio.Lock())
    monkeypatch.setattr(server, "room_action_locks", {})
    monkeypatch.setattr(server, "room_service", RoomService(RoomRegistry()))
    monkeypatch.setattr(server, "session_service", SessionService(SessionRegistry()))
    monkeypatch.setattr(server, "game_registry", GameRegistry())
    monkeypatch.setattr(server, "admission_cache", AdmissionCache())
    monkeypatch.setattr(server, "rematch_cache", RematchReplayCache())
    monkeypatch.setattr(server, "leave_cache", LeaveResultCache())
    monkeypatch.setattr(server, "rematch_timers", {})
    events = []

    async def emit(event, data=None, **target):
        events.append((event, data, target))

    async def enter_room(*args):
        pass

    async def leave_room(sid, room):
        events.append(("socket:left", {"sid": sid, "room": room}, {}))

    monkeypatch.setattr(server.sio, "emit", emit)
    monkeypatch.setattr(server.sio, "enter_room", enter_room)
    monkeypatch.setattr(server.sio, "leave_room", leave_room)
    return events


def admission(nickname, instance, room_code=None):
    request = {"nickname": nickname, "clientInstanceId": instance,
               "requestId": f"{EPOCH}:{int(time() * 1000)}:{uuid4()}"}
    if room_code:
        request["roomCode"] = room_code
    return request


async def finished_room():
    players = [await server.handle_room_create("a", admission("Alice", "a"))]
    for sid in ("b", "c"):
        players.append(await server.handle_room_join(
            sid, admission(sid, sid, players[0]["roomCode"])))
    for sid in ("a", "b", "c"):
        await server.handle_room_ready(sid, {"isReady": True})
    await server.handle_game_start("a", {})
    room = server.room_service.registry.get_by_id(players[0]["roomId"])
    runtime = server.game_registry.get(room.room_id)
    runtime.game_state.phase = GamePhase.FINISHED
    runtime.game_state.winner_player_id = players[0]["playerId"]
    room.status = RoomStatus.FINISHED
    return room, players


def leave_payload(player, request_id):
    return {"playerSessionId": player["playerSessionId"], "requestId": request_id}


def test_regular_leave_replay_and_room_left_restore(gateway):
    async def run():
        room, players = await finished_room()
        payload = leave_payload(players[2], "leave-c")
        before = room.state_version
        ack = await server.handle_room_leave("c", payload)
        assert ack["status"] == "room_left" and ack["requestId"] == "leave-c"
        assert ack["roomId"] == room.room_id and ack["replayUntilMs"] > int(time() * 1000)
        assert room.state_version == before + 1 and len(room.players) == 2
        assert server.session_service.get_session_by_socket("c") is None
        assert players[2]["playerSessionId"] not in server.session_service.registry.sessions_by_id
        assert any(event == "socket:left" and data["sid"] == "c" for event, data, _ in gateway)
        assert any(event == "room:updated" and data["stateVersion"] == room.state_version
                   for event, data, _ in gateway)
        assert await server.handle_room_leave("c", payload) == ack
        assert room.state_version == before + 1
        attempt_id = str(uuid4())
        restore = await server.handle_player_reconnect("c2", {
            "playerSessionId": players[2]["playerSessionId"], "clientInstanceId": "c",
            "attemptId": attempt_id, "takeover": False,
        })
        assert restore == {"status": "room_left", "roomId": room.room_id,
                           "playerSessionId": players[2]["playerSessionId"], "attemptId": attempt_id}
        assert server.session_service.get_session_by_socket("c2") is None
    asyncio.run(run())


def test_host_leave_transfers_host_and_last_member_closes_room(gateway):
    async def run():
        room, players = await finished_room()
        assert await server.handle_room_leave("a", leave_payload(players[0], "leave-a"))
        assert room.host_player_id == players[1]["playerId"]
        await server.disconnect("c")
        assert await server.handle_room_leave("b", leave_payload(players[1], "leave-b"))
        assert room.host_player_id == players[2]["playerId"]
        restored = await server.handle_player_reconnect("c", {
            "playerSessionId": players[2]["playerSessionId"], "clientInstanceId": "c",
            "attemptId": str(uuid4()), "takeover": False,
        })
        assert restored["room"]["players"][0]["isHost"] is True
        assert await server.handle_room_leave("c", leave_payload(players[2], "leave-last"))
        assert room.room_id not in server.room_service.registry.rooms_by_id
        assert room.room_code not in server.room_service.registry.room_id_by_code
        assert server.game_registry.get(room.room_id) is None
        assert not server.session_service.registry.sessions_by_id
    asyncio.run(run())


def test_host_transfer_falls_back_to_earliest_joined_disconnected(gateway):
    async def run():
        room, players = await finished_room()
        await server.disconnect("b")
        await server.disconnect("c")
        assert await server.handle_room_leave("a", leave_payload(players[0], "leave-a"))
        assert room.host_player_id == players[1]["playerId"]
        assert room.status is RoomStatus.FINISHED
    asyncio.run(run())


def test_leave_rechecks_rematch_consensus_and_rejects_late_vote(gateway):
    async def run():
        room, players = await finished_room()
        await server.handle_rematch_ready("a", {"requestId": "vote-a"})
        await server.handle_rematch_ready("b", {"requestId": "vote-b"})
        ack = await server.handle_room_leave("c", leave_payload(players[2], "leave-c"))
        assert ack["status"] == "room_left"
        assert room.status is RoomStatus.WAITING
        assert len(room.players) == 2
        assert server.game_registry.get(room.room_id) is None
        assert await server.handle_rematch_ready("a", {"requestId": "new-vote"}) is None
        assert gateway[-1][1]["code"] == "room_not_finished"
        assert (await server.handle_rematch_ready("a", {"requestId": "vote-a"}))["choice"] == "ready"
    asyncio.run(run())


def test_invalid_leave_session_and_request_conflict_do_not_mutate_room(gateway):
    async def run():
        room, players = await finished_room()
        before = room.state_version
        assert await server.handle_room_leave("b", leave_payload(players[0], "wrong-session")) is None
        assert gateway[-1][1]["code"] == "session_mismatch"
        assert room.state_version == before and len(room.players) == 3
        assert await server.handle_room_leave("a", leave_payload(players[0], "shared-id"))
        after = room.state_version
        assert await server.handle_room_leave("b", leave_payload(players[1], "shared-id")) is None
        assert gateway[-1][1]["code"] == "request_conflict"
        assert room.state_version == after and len(room.players) == 2
    asyncio.run(run())


def test_terminal_record_expiry_and_restart_become_invalid_session(gateway, monkeypatch):
    async def run():
        room, players = await finished_room()
        ack = await server.handle_room_leave("c", leave_payload(players[2], "leave-c"))
        monkeypatch.setattr("app.realtime.leave.time", lambda: (ack["replayUntilMs"] + 1) / 1000)
        assert await server.handle_player_reconnect("c2", {
            "playerSessionId": players[2]["playerSessionId"], "clientInstanceId": "c",
            "attemptId": "expired", "takeover": False,
        }) is None
        assert gateway[-1][1]["code"] == "invalid_session"
        assert await server.handle_room_leave("c2", leave_payload(players[2], "leave-c")) is None
        assert gateway[-1][1]["code"] == "session_not_bound"
        monkeypatch.setattr(server, "leave_cache", LeaveResultCache())
        assert await server.handle_player_reconnect("c3", {
            "playerSessionId": players[2]["playerSessionId"], "clientInstanceId": "c",
            "attemptId": "restart", "takeover": False,
        }) is None
        assert gateway[-1][1]["code"] == "invalid_session"
    asyncio.run(run())


def test_uncommitted_leave_can_retry_same_id_after_valid_restore(gateway):
    async def run():
        room, players = await finished_room()
        await server.disconnect("c")
        restore = await server.handle_player_reconnect("c2", {
            "playerSessionId": players[2]["playerSessionId"], "clientInstanceId": "c",
            "attemptId": str(uuid4()), "takeover": False,
        })
        assert restore["roomId"] == room.room_id
        ack = await server.handle_room_leave("c2", leave_payload(players[2], "same-id"))
        assert ack["status"] == "room_left"
        assert await server.handle_room_leave("c2", leave_payload(players[2], "same-id")) == ack
    asyncio.run(run())


def test_leave_before_finished_is_rejected_without_removing_membership(gateway):
    async def run():
        joined = await server.handle_room_create("a", admission("Alice", "a"))
        room = server.room_service.registry.get_by_id(joined["roomId"])
        before = room.state_version
        assert await server.handle_room_leave("a", leave_payload(joined, "too-early")) is None
        assert gateway[-1][1]["code"] == "room_not_finished"
        assert room.state_version == before and len(room.players) == 1
        assert server.session_service.get_session_by_socket("a") is not None
    asyncio.run(run())

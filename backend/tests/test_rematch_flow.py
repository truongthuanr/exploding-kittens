import asyncio
from time import time
from uuid import uuid4

import pytest

from app.modules.game import GameRegistry
from app.modules.room import RoomRegistry, RoomService
from app.modules.session import SessionRegistry, SessionService
from app.realtime import server
from app.realtime.admission import AdmissionCache, EPOCH
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
    monkeypatch.setattr(server, "rematch_timers", {})
    events = []

    async def emit(event, data=None, **target):
        events.append((event, data, target))

    async def enter_room(*args):
        pass

    monkeypatch.setattr(server.sio, "emit", emit)
    monkeypatch.setattr(server.sio, "enter_room", enter_room)
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


def test_rematch_votes_replay_and_clean_waiting_transition(gateway):
    async def run():
        room, players = await finished_room()
        request = {"requestId": "vote-a"}
        first = await server.handle_rematch_ready("a", request)
        assert first["choice"] == "ready"
        assert first["stateVersion"] == room.state_version
        assert server.bootstrap(server.session_service.get_session(players[0]["playerSessionId"]))["room"]["players"][0]["rematchReady"]
        assert await server.handle_rematch_ready("a", request) == first
        assert room.state_version == first["stateVersion"]
        assert await server.handle_rematch_withdraw("a", request) is None
        assert gateway[-1][1]["code"] == "request_conflict"
        assert await server.handle_rematch_ready("b", {"requestId": "vote-b"})
        final = await server.handle_rematch_ready("c", {"requestId": "vote-c"})
        assert final["stateVersion"] == room.state_version
        assert room.status is RoomStatus.WAITING
        assert server.game_registry.get(room.room_id) is None
        assert all(not member.is_ready and not member.rematch_ready for member in room.players)
        snapshot = server.bootstrap(server.session_service.get_session(players[0]["playerSessionId"]))
        assert snapshot["game"] is None and snapshot["private"] is None
        assert await server.handle_rematch_ready("a", request) == first
        assert await server.handle_rematch_ready("a", {"requestId": "new-vote"}) is None
        assert gateway[-1][1]["code"] == "room_not_finished"
        joined = await server.handle_room_join("d", admission("d", "d", room.room_code))
        assert joined["roomId"] == room.room_id
        await server.handle_game_start("a", {})
        assert gateway[-1][1]["code"] == "players_not_ready"
        for sid in ("a", "b", "c", "d"):
            await server.handle_room_ready(sid, {"isReady": True})
        await server.handle_game_start("a", {})
        next_runtime = server.game_registry.get(room.room_id)
        assert room.status is RoomStatus.IN_GAME
        assert next_runtime.game_state.winner_player_id is None
        assert len(next_runtime.action_history) == 1
        assert next_runtime.action_history[0].action_type.value == "start_game"
    asyncio.run(run())


def test_disconnect_grace_reconnect_and_withdraw(gateway):
    async def run():
        room, players = await finished_room()
        await server.disconnect("c")
        await server.handle_rematch_ready("a", {"requestId": "first"})
        deadline = room.get_player(players[2]["playerId"]).rematch_grace_deadline_ms
        assert deadline and deadline > int(time() * 1000)
        snapshot = server.bootstrap(server.session_service.get_session(players[0]["playerSessionId"]))
        assert snapshot["room"]["players"][2]["rematchGraceDeadlineMs"] == deadline
        assert snapshot["stateVersion"] == snapshot["game"]["stateVersion"] == snapshot["private"]["stateVersion"]
        restored = await server.handle_player_reconnect("c", {
            "playerSessionId": players[2]["playerSessionId"], "clientInstanceId": "c",
            "attemptId": str(uuid4()), "takeover": False,
        })
        assert restored["room"]["players"][2]["rematchGraceDeadlineMs"] is None
        assert (room.room_id, players[2]["playerId"]) not in server.rematch_timers
        await server.expire_rematch_member(room.room_id, players[2]["playerId"], int(time() * 1000) - 1)
        assert len(room.players) == 3
        await server.disconnect("c")
        assert room.get_player(players[2]["playerId"]).rematch_grace_deadline_ms is not None
        await server.handle_rematch_withdraw("a", {"requestId": "withdraw"})
        assert all(member.rematch_grace_deadline_ms is None for member in room.players)
        assert not server.rematch_timers
        await server.handle_rematch_ready("b", {"requestId": "new-first"})
        assert room.get_player(players[2]["playerId"]).rematch_grace_deadline_ms is not None
    asyncio.run(run())


def test_grace_expiry_revokes_session_and_rechecks_consensus(gateway):
    async def run():
        room, players = await finished_room()
        await server.disconnect("c")
        await server.handle_rematch_ready("a", {"requestId": "first"})
        await server.handle_rematch_ready("b", {"requestId": "second"})
        member = room.get_player(players[2]["playerId"])
        old_deadline = member.rematch_grace_deadline_ms
        member.rematch_grace_deadline_ms = int(time() * 1000) - 1
        await server.expire_rematch_member(room.room_id, member.player_id, member.rematch_grace_deadline_ms)
        assert old_deadline != member.rematch_grace_deadline_ms
        assert room.status is RoomStatus.WAITING
        assert len(room.players) == 2
        assert server.game_registry.get(room.room_id) is None
        assert players[2]["playerSessionId"] not in server.session_service.registry.sessions_by_id
        assert all(not player.rematch_ready for player in room.players)
        assert any(event == "room:updated" and data["status"] == "waiting" for event, data, _ in gateway)
        await server.handle_room_ready("a", {"isReady": True})
        await server.handle_room_ready("b", {"isReady": True})
        await server.handle_game_start("a", {})
        assert gateway[-1][1]["code"] == "not_enough_players"
        joined = await server.handle_room_join("d", admission("d", "d", room.room_code))
        assert joined["roomId"] == room.room_id
    asyncio.run(run())


def test_host_grace_expiry_transfers_host_to_earliest_connected_member(gateway):
    async def run():
        room, players = await finished_room()
        await server.disconnect("a")
        await server.handle_rematch_ready("b", {"requestId": "vote-b"})
        await server.handle_rematch_ready("c", {"requestId": "vote-c"})
        host = room.get_player(players[0]["playerId"])
        host.rematch_grace_deadline_ms = int(time() * 1000) - 1
        await server.expire_rematch_member(room.room_id, host.player_id, host.rematch_grace_deadline_ms)
        assert room.host_player_id == players[1]["playerId"]
        assert room.status is RoomStatus.WAITING
        assert players[0]["playerSessionId"] not in server.session_service.registry.sessions_by_id
    asyncio.run(run())


def test_timeout_of_last_voter_cancels_other_removal_deadlines(gateway):
    async def run():
        room, players = await finished_room()
        await server.disconnect("c")
        await server.handle_rematch_ready("a", {"requestId": "vote-a"})
        await server.disconnect("a")
        voter = room.get_player(players[0]["playerId"])
        voter.rematch_grace_deadline_ms = int(time() * 1000) - 1
        await server.expire_rematch_member(room.room_id, voter.player_id, voter.rematch_grace_deadline_ms)
        assert room.status is RoomStatus.FINISHED
        assert all(not member.rematch_ready and member.rematch_grace_deadline_ms is None
                   for member in room.players)
        assert not server.rematch_timers
        assert players[2]["playerSessionId"] in server.session_service.registry.sessions_by_id
    asyncio.run(run())

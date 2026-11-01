"""Deterministic game setup for Playwright's isolated backend process."""

import asyncio

from app.main import app
from app.modules.game.service import GameSetupService
from app.realtime import server


class FixedRandom:
    def shuffle(self, cards):
        return None

    def randint(self, start, stop):
        return start


server.game_setup_service = GameSetupService(shuffler=lambda cards: cards.copy())
server.turn_service.randomizer = FixedRandom()

# One room with this host name receives a delayed, correlated draw error once.
# The browser can verify the pending lock, nearby error, and subsequent retry.
original_draw_handler = server.sio.handlers["/"]["turn:draw-card"]
rejected_rooms: set[str] = set()


async def draw_with_test_error(sid, data):
    session = server.session_service.get_session_by_socket(sid)
    if session is not None:
        room = server.room_service.registry.get_by_id(session.room_id)
        if room.players[0].nickname == "ErrorHost" and room.room_id not in rejected_rooms:
            rejected_rooms.add(room.room_id)
            await asyncio.sleep(0.4)
            await server.emit_socket_error(sid, "invalid_turn_phase", "Injected test error", data.get("requestId"))
            return None
    return await original_draw_handler(sid, data)


server.sio.on("turn:draw-card", handler=draw_with_test_error)

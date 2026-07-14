from app.modules.room.models import RoomState
from app.schemas.responses import RoomPlayer, RoomUpdatedEvent


def to_room_updated_event(room: RoomState) -> RoomUpdatedEvent:
    return RoomUpdatedEvent(
        roomId=room.room_id,
        roomCode=room.room_code,
        status=room.status,
        players=[
            RoomPlayer(
                playerId=player.player_id,
                nickname=player.nickname,
                isReady=player.is_ready,
                isHost=room.is_host_player(player.player_id),
                status=player.status,
            )
            for player in room.players
        ],
    )

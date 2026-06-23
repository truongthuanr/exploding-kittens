from app.modules.room.models import RoomState
from app.schemas.responses import RoomUpdatedEvent


def to_room_updated_event(room: RoomState) -> RoomUpdatedEvent:
    return room.to_room_updated_event()

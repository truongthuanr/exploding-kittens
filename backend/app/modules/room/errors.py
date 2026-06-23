class RoomError(Exception):
    """Base error for room module failures."""


class RoomNotFoundError(RoomError):
    def __init__(self, room_ref: str) -> None:
        super().__init__(f"Room not found: {room_ref}")
        self.room_ref = room_ref


class DuplicateRoomCodeError(RoomError):
    def __init__(self, room_code: str) -> None:
        super().__init__(f"Duplicate room code: {room_code}")
        self.room_code = room_code


class DuplicateNicknameError(RoomError):
    def __init__(self, nickname: str) -> None:
        super().__init__(f"Duplicate nickname in room: {nickname}")
        self.nickname = nickname


class RoomNotJoinableError(RoomError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Room is not joinable: {room_id}")
        self.room_id = room_id


class NotHostError(RoomError):
    def __init__(self, player_id: str) -> None:
        super().__init__(f"Player is not host: {player_id}")
        self.player_id = player_id


class RoomNotWaitingError(RoomError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Room is not waiting: {room_id}")
        self.room_id = room_id


class PlayerNotInRoomError(RoomError):
    def __init__(self, player_id: str, room_id: str) -> None:
        super().__init__(f"Player {player_id} is not in room {room_id}")
        self.player_id = player_id
        self.room_id = room_id

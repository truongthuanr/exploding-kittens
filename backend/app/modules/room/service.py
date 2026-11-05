from __future__ import annotations

from dataclasses import dataclass
from random import SystemRandom
from string import ascii_uppercase, digits
from uuid import uuid4

from app.modules.room.constants import MAX_ROOM_PLAYERS, MIN_ROOM_PLAYERS
from app.modules.room.errors import (
    DuplicateNicknameError,
    DuplicateRoomCodeError,
    NotEnoughPlayersError,
    NotHostError,
    PlayerNotInRoomError,
    PlayersDisconnectedError,
    PlayersNotReadyError,
    RoomFullError,
    RoomNotFoundError,
    RoomNotFinishedError,
    RoomNotJoinableError,
    RoomNotWaitingError,
)
from app.modules.room.models import RoomPlayerState, RoomState
from app.modules.room.registry import RoomRegistry
from app.schemas.enums import PlayerStatus, RoomStatus

ROOM_CODE_LENGTH = 6
ROOM_CODE_ALPHABET = ascii_uppercase + digits
ROOM_CODE_GENERATION_ATTEMPTS = 32


@dataclass(slots=True)
class RoomOperationResult:
    room: RoomState
    player: RoomPlayerState


@dataclass(slots=True)
class RoomService:
    registry: RoomRegistry

    def create_room(self, nickname: str) -> RoomOperationResult:
        host_player = RoomPlayerState(player_id=self._generate_player_id(), nickname=nickname)
        room = RoomState(
            room_id=self._generate_room_id(),
            room_code=self._generate_unique_room_code(),
            host_player_id=host_player.player_id,
            players=[host_player],
        )
        self.registry.add(room)
        return RoomOperationResult(room=room, player=host_player)

    def join_room(self, room_code: str, nickname: str) -> RoomOperationResult:
        normalized_room_code = room_code.upper()
        room = self.registry.get_by_code(normalized_room_code)
        if room.status is not RoomStatus.WAITING:
            raise RoomNotJoinableError(room.room_id)
        if len(room.players) >= MAX_ROOM_PLAYERS:
            raise RoomFullError(room.room_id)
        if room.has_nickname(nickname):
            raise DuplicateNicknameError(nickname)

        player = RoomPlayerState(player_id=self._generate_player_id(), nickname=nickname)
        room.players.append(player)
        return RoomOperationResult(room=room, player=player)

    def set_ready(self, room_id: str, player_id: str, is_ready: bool) -> RoomState:
        room = self.registry.get_by_id(room_id)
        if room.status is not RoomStatus.WAITING:
            raise RoomNotWaitingError(room.room_id)

        player = room.get_player(player_id)
        if player is None:
            raise PlayerNotInRoomError(player_id, room.room_id)

        player.is_ready = is_ready
        return room

    def validate_start_preconditions(self, room_id: str, player_id: str) -> RoomState:
        room = self.registry.get_by_id(room_id)
        if room.status is not RoomStatus.WAITING:
            raise RoomNotWaitingError(room.room_id)
        if not room.is_host_player(player_id):
            raise NotHostError(player_id)

        player_count = len(room.players)
        if player_count < MIN_ROOM_PLAYERS or player_count > MAX_ROOM_PLAYERS:
            raise NotEnoughPlayersError(room.room_id, player_count)
        if any(not player.is_ready for player in room.players):
            raise PlayersNotReadyError(room.room_id)
        if any(player.status is not PlayerStatus.CONNECTED for player in room.players):
            raise PlayersDisconnectedError(room.room_id)

        return room

    def transition_to_starting(self, room_id: str, player_id: str) -> RoomState:
        room = self.validate_start_preconditions(room_id, player_id)
        room.status = RoomStatus.STARTING
        return room

    def set_rematch_vote(self, room_id: str, player_id: str, ready: bool, now_ms: int, grace_ms: int) -> RoomState:
        room = self.registry.get_by_id(room_id)
        if room.status is not RoomStatus.FINISHED:
            raise RoomNotFinishedError(room_id)
        player = room.get_player(player_id)
        if player is None:
            raise PlayerNotInRoomError(player_id, room_id)
        had_votes = any(member.rematch_ready for member in room.players)
        player.rematch_ready = ready
        has_votes = any(member.rematch_ready for member in room.players)
        if not has_votes:
            for member in room.players:
                member.rematch_grace_deadline_ms = None
        elif not had_votes:
            for member in room.players:
                if member.status is PlayerStatus.DISCONNECTED:
                    member.rematch_grace_deadline_ms = now_ms + grace_ms
        return room

    def rematch_consensus(self, room: RoomState) -> bool:
        return bool(room.players) and all(member.rematch_ready for member in room.players)

    def remove_player(self, room_id: str, player_id: str) -> RoomState:
        room = self.registry.get_by_id(room_id)
        if room.get_player(player_id) is None:
            raise PlayerNotInRoomError(player_id, room_id)
        room.players = [member for member in room.players if member.player_id != player_id]
        if not any(member.rematch_ready for member in room.players):
            for member in room.players:
                member.rematch_grace_deadline_ms = None
        if room.players and room.host_player_id == player_id:
            room.host_player_id = next(
                (member.player_id for member in room.players if member.status is PlayerStatus.CONNECTED),
                room.players[0].player_id,
            )
        return room

    def _generate_room_id(self) -> str:
        return str(uuid4())

    def _generate_player_id(self) -> str:
        return str(uuid4())

    def _generate_unique_room_code(self) -> str:
        for _ in range(ROOM_CODE_GENERATION_ATTEMPTS):
            room_code = self._generate_room_code()
            try:
                self.registry.get_by_code(room_code)
            except RoomNotFoundError:
                return room_code

        raise DuplicateRoomCodeError("Unable to generate a unique room code")

    def _generate_room_code(self) -> str:
        random = SystemRandom()
        return "".join(random.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))

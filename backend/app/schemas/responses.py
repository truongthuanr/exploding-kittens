from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import ActionType, CardType, GamePhase, PlayerStatus, RoomStatus


class SocketResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoomCreateResponse(SocketResponseModel):
    roomId: str
    roomCode: str
    playerId: str
    playerSessionId: str


class RoomJoinResponse(SocketResponseModel):
    roomId: str
    roomCode: str
    playerId: str
    playerSessionId: str


class RoomPlayer(SocketResponseModel):
    playerId: str
    nickname: str
    isReady: bool
    isHost: bool
    status: PlayerStatus
    rematchReady: bool = False
    rematchGraceDeadlineMs: int | None = None


class RoomUpdatedEvent(SocketResponseModel):
    stateVersion: int = 0
    roomId: str
    roomCode: str
    status: RoomStatus
    players: list[RoomPlayer]


class GameStartedEvent(SocketResponseModel):
    roomId: str
    currentPlayerId: str
    turnNumber: int


class TurnStartedEvent(SocketResponseModel):
    currentPlayerId: str
    pendingDraws: int
    turnNumber: int


class PublicGamePlayer(SocketResponseModel):
    playerId: str
    nickname: str
    handCount: int
    status: PlayerStatus


class RecentAction(SocketResponseModel):
    actorPlayerId: str
    actionType: ActionType
    targetPlayerId: str | None = None
    summary: str


class ActionHistoryEntry(RecentAction):
    stateVersion: int


class GameActionAck(SocketResponseModel):
    requestId: str
    stateVersion: int


class RematchVoteAck(SocketResponseModel):
    requestId: str
    stateVersion: int
    choice: Literal["ready", "withdrawn"]


class LeaveRoomAck(SocketResponseModel):
    requestId: str
    roomId: str
    status: Literal["room_left"] = "room_left"


class PublicGameStateEvent(SocketResponseModel):
    stateVersion: int = 0
    roomId: str
    phase: GamePhase
    currentPlayerId: str
    pendingDraws: int
    turnNumber: int
    players: list[PublicGamePlayer]
    discardTopCardType: CardType | None
    discardCount: int
    winnerPlayerId: str | None
    recentAction: RecentAction | None
    actionHistory: list[ActionHistoryEntry]


class PrivateCardView(SocketResponseModel):
    cardId: str
    cardType: CardType


class PlayerPrivateStateEvent(SocketResponseModel):
    stateVersion: int = 0
    playerId: str
    hand: list[PrivateCardView]
    visibleFutureCards: list[CardType] | None


class PlayerEliminatedEvent(SocketResponseModel):
    playerId: str
    eliminatedBy: Literal["exploding_kitten"]


class GameEndedEvent(SocketResponseModel):
    winnerPlayerId: str


class ErrorEvent(SocketResponseModel):
    code: str
    message: str
    requestId: str | None = None


class BootstrapResponse(RoomCreateResponse):
    requiresTakeover: bool = False
    stateVersion: int
    room: RoomUpdatedEvent
    game: PublicGameStateEvent | None
    private: PlayerPrivateStateEvent | None
    attemptId: str | None = None


class SessionReplacedEvent(SocketResponseModel):
    message: str

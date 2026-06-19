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


class RoomUpdatedEvent(SocketResponseModel):
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


class PublicGameStateEvent(SocketResponseModel):
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


class PrivateCardView(SocketResponseModel):
    cardId: str
    cardType: CardType


class PlayerPrivateStateEvent(SocketResponseModel):
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

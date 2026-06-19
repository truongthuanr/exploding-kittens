from pydantic import BaseModel, ConfigDict


class SocketRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoomCreateRequest(SocketRequestModel):
    nickname: str


class RoomJoinRequest(SocketRequestModel):
    roomCode: str
    nickname: str


class RoomReadyRequest(SocketRequestModel):
    isReady: bool


class GameStartRequest(SocketRequestModel):
    requestId: str | None = None


class PlayCardRequest(SocketRequestModel):
    requestId: str | None = None
    cardId: str
    targetPlayerId: str | None = None


class DrawCardRequest(SocketRequestModel):
    requestId: str | None = None


class ReconnectRequest(SocketRequestModel):
    playerSessionId: str

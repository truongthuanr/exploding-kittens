from pydantic import BaseModel, ConfigDict, Field, model_validator


class SocketRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoomAdmissionRequest(SocketRequestModel):
    # Optional only for the existing backend-only clients. Modern clients send both.
    requestId: str | None = Field(default=None, min_length=1, max_length=180)
    clientInstanceId: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def paired_identity(self):
        if (self.requestId is None) != (self.clientInstanceId is None):
            raise ValueError("requestId and clientInstanceId must be supplied together")
        return self


class RoomCreateRequest(RoomAdmissionRequest):
    nickname: str


class RoomJoinRequest(RoomAdmissionRequest):
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
    clientInstanceId: str | None = Field(default=None, min_length=1, max_length=128)
    takeover: bool = False
    attemptId: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def paired_reconnect_identity(self):
        if (self.clientInstanceId is None) != (self.attemptId is None):
            raise ValueError("clientInstanceId and attemptId must be supplied together")
        if self.takeover and self.clientInstanceId is None:
            raise ValueError("Explicit takeover requires a client instance")
        return self

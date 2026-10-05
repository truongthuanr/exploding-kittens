export type RoomCreateRequest = {
  requestId: string;
  clientInstanceId: string;
  nickname: string;
};

export type RoomJoinRequest = {
  requestId: string;
  clientInstanceId: string;
  roomCode: string;
  nickname: string;
};

export type RoomReadyRequest = {
  isReady: boolean;
};

export type GameStartRequest = {
  requestId?: string;
};

export type PlayCardRequest = {
  requestId?: string;
  cardId: string;
  targetPlayerId?: string;
};

export type DrawCardRequest = {
  requestId?: string;
};

export type ReconnectRequest = {
  playerSessionId: string;
  clientInstanceId: string;
  takeover: boolean;
  attemptId: string;
};

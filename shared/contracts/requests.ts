export type RoomCreateRequest = {
  nickname: string;
};

export type RoomJoinRequest = {
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
};

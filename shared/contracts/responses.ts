import type { ActionType, CardType, GamePhase, PlayerStatus, RoomStatus } from "./enums";

export type RoomCreateResponse = {
  roomId: string;
  roomCode: string;
  playerId: string;
  playerSessionId: string;
};

export type RoomJoinResponse = {
  roomId: string;
  roomCode: string;
  playerId: string;
  playerSessionId: string;
};

export type RoomPlayer = {
  playerId: string;
  nickname: string;
  isReady: boolean;
  isHost: boolean;
  status: PlayerStatus;
};

export type RoomUpdatedEvent = {
  roomId: string;
  roomCode: string;
  status: RoomStatus;
  players: RoomPlayer[];
};

export type GameStartedEvent = {
  roomId: string;
  currentPlayerId: string;
  turnNumber: number;
};

export type TurnStartedEvent = {
  currentPlayerId: string;
  pendingDraws: number;
  turnNumber: number;
};

export type PublicGamePlayer = {
  playerId: string;
  nickname: string;
  handCount: number;
  status: PlayerStatus;
};

export type RecentAction = {
  actorPlayerId: string;
  actionType: ActionType;
  targetPlayerId?: string;
  summary: string;
};

export type PublicGameStateEvent = {
  roomId: string;
  phase: GamePhase;
  currentPlayerId: string;
  pendingDraws: number;
  turnNumber: number;
  players: PublicGamePlayer[];
  discardTopCardType: CardType | null;
  discardCount: number;
  winnerPlayerId: string | null;
  recentAction: RecentAction | null;
};

export type PrivateCardView = {
  cardId: string;
  cardType: CardType;
};

export type PlayerPrivateStateEvent = {
  playerId: string;
  hand: PrivateCardView[];
  visibleFutureCards: CardType[] | null;
};

export type PlayerEliminatedEvent = {
  playerId: string;
  eliminatedBy: "exploding_kitten";
};

export type GameEndedEvent = {
  winnerPlayerId: string;
};

export type ErrorEvent = {
  code: string;
  message: string;
  requestId?: string;
};

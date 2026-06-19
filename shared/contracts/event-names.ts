export const CLIENT_EVENTS = {
  ROOM_CREATE: "room:create",
  ROOM_JOIN: "room:join",
  ROOM_READY: "room:ready",
  GAME_START: "game:start",
  TURN_PLAY_CARD: "turn:play-card",
  TURN_DRAW_CARD: "turn:draw-card",
  PLAYER_RECONNECT: "player:reconnect",
} as const;

export const SERVER_EVENTS = {
  ROOM_UPDATED: "room:updated",
  GAME_STARTED: "game:started",
  TURN_STARTED: "turn:started",
  GAME_STATE: "game:state",
  PLAYER_PRIVATE_STATE: "player:private-state",
  PLAYER_ELIMINATED: "player:eliminated",
  GAME_ENDED: "game:ended",
  ERROR: "error",
} as const;

export type ClientEventName =
  (typeof CLIENT_EVENTS)[keyof typeof CLIENT_EVENTS];

export type ServerEventName =
  (typeof SERVER_EVENTS)[keyof typeof SERVER_EVENTS];

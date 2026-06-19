export const ROOM_STATUSES = [
  "waiting",
  "starting",
  "in_game",
  "finished",
] as const;

export type RoomStatus = (typeof ROOM_STATUSES)[number];

export const GAME_PHASES = [
  "lobby",
  "setup",
  "turn_action",
  "turn_draw",
  "resolving_explosion",
  "finished",
] as const;

export type GamePhase = (typeof GAME_PHASES)[number];

export const CARD_TYPES = [
  "exploding_kitten",
  "defuse",
  "skip",
  "attack",
  "shuffle",
  "see_the_future",
  "favor",
] as const;

export type CardType = (typeof CARD_TYPES)[number];

export const PLAYER_STATUSES = [
  "connected",
  "disconnected",
  "eliminated",
] as const;

export type PlayerStatus = (typeof PLAYER_STATUSES)[number];

export const ACTION_TYPES = [
  "start_game",
  "play_skip",
  "play_attack",
  "play_shuffle",
  "play_see_the_future",
  "play_favor",
  "draw_card",
  "defuse",
  "explode",
  "eliminate",
  "turn_advanced",
] as const;

export type ActionType = (typeof ACTION_TYPES)[number];

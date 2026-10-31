import type { RealtimeState } from "./client";

export type RoomView =
  | "home"
  | "admission_home"
  | "admission_conflict"
  | "restoring"
  | "restore_failed"
  | "replaced"
  | "read_only_lobby"
  | "lobby"
  | "game_loading"
  | "game"
  | "finished"
  | "safe_recovery";

export type LobbyBlocker =
  | "connection_unavailable"
  | "session_unavailable"
  | "admission_conflict"
  | "synchronizing"
  | "room_unavailable"
  | "room_not_waiting"
  | "player_missing"
  | "ready_pending"
  | "start_pending"
  | "not_host"
  | "player_count"
  | "players_not_ready"
  | "players_disconnected";

export type LobbyPending = { ready?: boolean; start?: boolean };
export type LobbyActions = {
  canToggleReady: boolean;
  readyBlocker: LobbyBlocker | null;
  canStart: boolean;
  startBlockers: LobbyBlocker[];
};

export function hasUsableRoom(state: RealtimeState): boolean {
  const { identity, room } = state;
  return !!identity && !!room && room.roomId === identity.roomId &&
    room.players.some(player => player.playerId === identity.playerId);
}

export function hasCurrentGamePair(state: RealtimeState): boolean {
  const { identity, room, game, private: privateState } = state;
  return hasUsableRoom(state) && !!identity && !!room && !!game && !!privateState &&
    game.roomId === identity.roomId && privateState.playerId === identity.playerId &&
    game.stateVersion === privateState.stateVersion &&
    game.stateVersion >= room.stateVersion;
}

/** Evaluate in the same priority order as the UI design matrix. */
export function selectRoomView(state: RealtimeState): RoomView {
  if (state.session === "replaced") return "replaced";
  if (state.session === "invalid") return "home";
  if (state.identity && (state.pendingAdmission || state.session === "joining" || state.session === "join_failed")) {
    return "admission_conflict";
  }
  if (!state.identity && (state.pendingAdmission || state.session === "joining" || state.session === "join_failed")) {
    return "admission_home";
  }
  if (!state.identity) return "home";

  if (state.session === "restore_failed" &&
      (state.connection === "disconnected" || state.connection === "reconnecting") &&
      hasUsableRoom(state) && state.room?.status === "waiting") {
    return "read_only_lobby";
  }
  if (state.session === "none" || state.session === "restoring") return "restoring";
  if (state.session === "restore_failed") return "restore_failed";
  if (state.session !== "ready" || !hasUsableRoom(state)) return "safe_recovery";

  if (state.room!.status === "waiting") return "lobby";
  if (state.room!.status === "in_game" || state.room!.status === "finished") {
    if (state.syncing || !hasCurrentGamePair(state)) return "game_loading";
    if (state.room!.status === "finished" && state.game!.phase !== "finished") return "game_loading";
    if (state.game!.phase === "finished") return "finished";
    return state.room!.status === "in_game" ? "game" : "safe_recovery";
  }
  return "safe_recovery";
}

function lobbyBlocker(state: RealtimeState): LobbyBlocker | null {
  if (state.connection !== "connected") return "connection_unavailable";
  if (state.session !== "ready") return "session_unavailable";
  if (state.pendingAdmission) return "admission_conflict";
  if (state.syncing) return "synchronizing";
  if (!hasUsableRoom(state)) return "room_unavailable";
  if (state.room!.status !== "waiting") return "room_not_waiting";
  return null;
}

export function selectLobbyActions(state: RealtimeState, pending: LobbyPending = {}): LobbyActions {
  const baseBlocker = lobbyBlocker(state);
  const player = state.room?.players.find(candidate => candidate.playerId === state.identity?.playerId);
  const readyBlocker: LobbyBlocker | null =
    baseBlocker ?? (!player ? "player_missing" : pending.start ? "start_pending" : pending.ready ? "ready_pending" : null);

  const startBlockers: LobbyBlocker[] = [];
  if (baseBlocker) startBlockers.push(baseBlocker);
  else if (!player) startBlockers.push("player_missing");
  else if (!player.isHost) startBlockers.push("not_host");

  if (!baseBlocker && state.room) {
    if (state.room.players.length < 3 || state.room.players.length > 5) startBlockers.push("player_count");
    if (state.room.players.some(candidate => !candidate.isReady)) startBlockers.push("players_not_ready");
    if (state.room.players.some(candidate => candidate.status !== "connected")) startBlockers.push("players_disconnected");
  }
  if (pending.start) startBlockers.push("start_pending");
  else if (pending.ready) startBlockers.push("ready_pending");

  return {
    canToggleReady: readyBlocker === null,
    readyBlocker,
    canStart: startBlockers.length === 0,
    startBlockers,
  };
}

import { describe, expect, it } from "vitest";
import { EMPTY_STATE, type RealtimeState } from "../lib/socket/client";
import {
  GAME_ACTION_BLOCKER_TEXT, hasCurrentGamePair, selectCurrentPlayer, selectGameActions,
  selectIsEliminated, selectIsOwnTurn, selectLobbyActions, selectLocalPlayer,
  selectRoomView, selectValidFavorTargets,
} from "../lib/socket/selectors";
import type { PlayerPrivateStateEvent, PublicGameStateEvent, RoomUpdatedEvent } from "../../shared/contracts";

const identity = { version: 1 as const, roomId: "room", roomCode: "ROOM01", playerId: "self", playerSessionId: "session" };
const players: RoomUpdatedEvent["players"] = [
  { playerId: "self", nickname: "Alice", isReady: true, isHost: true, status: "connected" },
  { playerId: "b", nickname: "Bob", isReady: true, isHost: false, status: "connected" },
  { playerId: "c", nickname: "Cat", isReady: true, isHost: false, status: "connected" },
];

function waiting(overrides: Partial<RealtimeState> = {}): RealtimeState {
  return {
    ...EMPTY_STATE,
    connection: "connected",
    session: "ready",
    identity,
    room: { roomId: "room", roomCode: "ROOM01", status: "waiting", stateVersion: 1, players },
    ...overrides,
  };
}

function inGame(roomVersion = 2, pairVersion = roomVersion): RealtimeState {
  const game: PublicGameStateEvent = {
    roomId: "room", stateVersion: pairVersion, phase: "turn_action", currentPlayerId: "self",
    pendingDraws: 1, turnNumber: 1,
    players: players.map(player => ({
      playerId: player.playerId, nickname: player.nickname, handCount: 2, status: player.status,
    })),
    discardTopCardType: null,
    discardCount: 0, winnerPlayerId: null, recentAction: null, actionHistory: [],
  };
  const privateState: PlayerPrivateStateEvent = {
    playerId: "self", stateVersion: pairVersion, hand: [], visibleFutureCards: null,
  };
  return waiting({
    room: { roomId: "room", roomCode: "ROOM01", status: "in_game", stateVersion: roomVersion, players },
    game,
    private: privateState,
  });
}

describe("selectRoomView", () => {
  it("gives session recovery priority over retained room data", () => {
    const state = waiting({ session: "replaced", connection: "disconnected" });
    expect(selectRoomView(state)).toBe("replaced");
    expect(selectRoomView({ ...state, session: "invalid" })).toBe("home");
    expect(selectRoomView({ ...state, session: "restoring" })).toBe("restoring");
    expect(selectRoomView({ ...state, session: "restore_failed", connection: "connected" })).toBe("restore_failed");
  });

  it("keeps admission on Home and blocks contradictory saved identity", () => {
    expect(selectRoomView(waiting({ identity: null, room: null, session: "joining", pendingAdmission: true }))).toBe("admission_home");
    expect(selectRoomView(waiting({ session: "join_failed", pendingAdmission: true }))).toBe("admission_conflict");
  });

  it("shows a retained waiting room read-only while offline, then restores", () => {
    const state = waiting({ connection: "disconnected", session: "restore_failed", syncing: true });
    expect(selectRoomView(state)).toBe("read_only_lobby");
    expect(selectRoomView({ ...state, connection: "reconnecting" })).toBe("read_only_lobby");
    expect(selectRoomView({ ...state, session: "restoring" })).toBe("restoring");
    expect(selectRoomView({ ...state, room: null })).toBe("restore_failed");
  });

  it("rejects room snapshots from another room or without the current player", () => {
    const state = waiting();
    expect(selectRoomView({ ...state, room: { ...state.room!, roomId: "other" } })).toBe("safe_recovery");
    expect(selectRoomView({ ...state, room: { ...state.room!, players: players.slice(1) } })).toBe("safe_recovery");
  });

  it("keeps the waiting lobby visible while syncing", () => {
    expect(selectRoomView(waiting({ syncing: true }))).toBe("lobby");
  });

  it("waits for a matched, current game pair", () => {
    const state = inGame(3, 2);
    expect(hasCurrentGamePair(state)).toBe(false);
    expect(selectRoomView(state)).toBe("game_loading");
    expect(selectRoomView({ ...state, game: { ...state.game!, stateVersion: 3 } })).toBe("game_loading");
    expect(selectRoomView({ ...state, private: { ...state.private!, playerId: "other" } })).toBe("game_loading");
    expect(selectRoomView(inGame(2, 3))).toBe("game");
    expect(selectRoomView({ ...inGame(), syncing: true })).toBe("game_loading");
    expect(selectRoomView({ ...inGame(), connection: "disconnected" })).toBe("restoring");
  });

  it("waits for a current finished pair before showing Finished", () => {
    const stale = inGame(4, 3);
    const finishedRoom = { ...stale.room!, status: "finished" as const };
    expect(selectRoomView({ ...stale, room: finishedRoom })).toBe("game_loading");
    const current = inGame(4, 4);
    expect(selectRoomView({ ...current, room: { ...current.room!, status: "finished" } })).toBe("game_loading");
    expect(selectRoomView({ ...current, game: { ...current.game!, phase: "finished" } })).toBe("finished");
    expect(selectRoomView({
      ...current, room: { ...current.room!, status: "finished" },
      game: { ...current.game!, phase: "finished" },
    })).toBe("finished");
  });
});

describe("selectLobbyActions", () => {
  it("allows Ready and Start only for a synchronized eligible host", () => {
    expect(selectLobbyActions(waiting())).toEqual({
      canToggleReady: true, readyBlocker: null, canStart: true, startBlockers: [],
    });
    expect(selectLobbyActions(waiting({ connection: "reconnecting" })).readyBlocker).toBe("connection_unavailable");
    expect(selectLobbyActions(waiting({ session: "restoring" })).startBlockers).toEqual(["session_unavailable"]);
    expect(selectLobbyActions(waiting({ syncing: true })).startBlockers).toEqual(["synchronizing"]);
  });

  it("explains every unmet start condition without blocking a non-host from Ready", () => {
    const room = waiting().room!;
    const state = waiting({ room: { ...room, players: [
      { ...players[0], isHost: false },
      { ...players[1], isReady: false, status: "disconnected" },
    ] } });
    expect(selectLobbyActions(state)).toEqual({
      canToggleReady: true, readyBlocker: null, canStart: false,
      startBlockers: ["not_host", "player_count", "players_not_ready", "players_disconnected"],
    });
  });

  it("locks actions while requests are pending and rejects invalid room identity", () => {
    expect(selectLobbyActions(waiting(), { ready: true }).readyBlocker).toBe("ready_pending");
    expect(selectLobbyActions(waiting(), { ready: true }).startBlockers).toEqual(["ready_pending"]);
    expect(selectLobbyActions(waiting({ pendingAdmission: true })).startBlockers).toEqual(["admission_conflict"]);
    const locked = selectLobbyActions(waiting(), { start: true });
    expect(locked.readyBlocker).toBe("start_pending");
    expect(locked.startBlockers).toContain("start_pending");
    const wrongRoom = waiting({ room: { ...waiting().room!, roomId: "other" } });
    expect(selectLobbyActions(wrongRoom).startBlockers).toEqual(["room_unavailable"]);
    expect(selectLobbyActions(wrongRoom).canToggleReady).toBe(false);
  });
});

describe("game action selectors", () => {
  const hand: PlayerPrivateStateEvent["hand"] = [
    { cardId: "skip-1", cardType: "skip" },
    { cardId: "attack-1", cardType: "attack" },
    { cardId: "shuffle-1", cardType: "shuffle" },
    { cardId: "future-1", cardType: "see_the_future" },
    { cardId: "favor-1", cardType: "favor" },
    { cardId: "defuse-1", cardType: "defuse" },
    { cardId: "bomb-1", cardType: "exploding_kitten" },
  ];
  const ready = () => {
    const state = inGame();
    return { ...state, private: { ...state.private!, hand } };
  };

  it("identifies players, turn, legal cards and Favor targets from the current pair", () => {
    const state = ready();
    expect(selectCurrentPlayer(state)?.playerId).toBe("self");
    expect(selectLocalPlayer(state)?.playerId).toBe("self");
    expect(selectIsOwnTurn(state)).toBe(true);
    expect(selectIsEliminated(state)).toBe(false);
    expect(selectValidFavorTargets(state).map(player => player.playerId)).toEqual(["b", "c"]);
    const actions = selectGameActions(state);
    expect(actions.canDraw).toBe(true);
    expect(actions.drawBlocker).toBeNull();
    expect(actions.cards.map(card => [card.cardId, card.canPlay])).toEqual([
      ["skip-1", true], ["attack-1", true], ["shuffle-1", true],
      ["future-1", true], ["favor-1", true], ["defuse-1", false], ["bomb-1", false],
    ]);
    expect(actions.cards.slice(-2).map(card => card.blocker)).toEqual([
      "card_not_playable", "card_not_playable",
    ]);
    expect(GAME_ACTION_BLOCKER_TEXT.wrong_turn).toMatch(/lượt/);
  });

  it.each([
    ["disconnected", (state: RealtimeState) => ({ ...state, connection: "disconnected" as const }), "connection_unavailable"],
    ["restoring", (state: RealtimeState) => ({ ...state, session: "restoring" as const }), "session_unavailable"],
    ["admission", (state: RealtimeState) => ({ ...state, pendingAdmission: true }), "session_unavailable"],
    ["syncing", (state: RealtimeState) => ({ ...state, syncing: true }), "synchronizing"],
    ["stale pair", (state: RealtimeState) => ({ ...state, room: { ...state.room!, stateVersion: 3 } }), "synchronizing"],
    ["wrong turn", (state: RealtimeState) => ({ ...state, game: { ...state.game!, currentPlayerId: "b" } }), "wrong_turn"],
    ["draw phase", (state: RealtimeState) => ({ ...state, game: { ...state.game!, phase: "turn_draw" as const } }), "phase_unavailable"],
    ["pending action", (state: RealtimeState) => ({ ...state, pendingAction: {
      requestId: "request", kind: "draw-card" as const, status: "pending" as const, confirmedStateVersion: null,
    } }), "action_pending"],
    ["unknown outcome", (state: RealtimeState) => ({ ...state, pendingAction: {
      requestId: "request", kind: "draw-card" as const, status: "unknown" as const, confirmedStateVersion: null,
    } }), "action_pending"],
    ["finished", (state: RealtimeState) => ({ ...state,
      room: { ...state.room!, status: "finished" as const },
      game: { ...state.game!, phase: "finished" as const },
    }), "game_not_in_progress"],
  ] as const)("blocks %s actions with a reason", (_name, change, blocker) => {
    const actions = selectGameActions(change(ready()));
    expect(actions.canDraw).toBe(false);
    expect(actions.drawBlocker).toBe(blocker);
    if (["disconnected", "restoring", "syncing", "stale pair"].includes(_name)) {
      expect(actions.cards).toEqual([]);
    } else {
      expect(actions.cards[0].canPlay).toBe(false);
      expect(actions.cards[0].blocker).toBe(blocker);
    }
  });

  it("locks an eliminated player's actions and excludes eliminated or empty Favor targets", () => {
    const state = ready();
    const game = { ...state.game!, players: state.game!.players.map(player =>
      player.playerId === "self" ? { ...player, status: "eliminated" as const } :
      player.playerId === "b" ? { ...player, status: "eliminated" as const } :
      { ...player, handCount: 0 }) };
    const eliminated = { ...state, game };
    expect(selectIsEliminated(eliminated)).toBe(true);
    expect(selectValidFavorTargets(eliminated)).toEqual([]);
    expect(selectGameActions(eliminated).drawBlocker).toBe("player_eliminated");

    const noTargets = { ...state, game: { ...game, players: game.players.map(player =>
      player.playerId === "self" ? { ...player, status: "connected" as const } : player) } };
    expect(selectGameActions(noTargets).cards.find(card => card.cardType === "favor")?.blocker)
      .toBe("favor_target_unavailable");
    expect(selectGameActions(noTargets).cards.find(card => card.cardType === "skip")?.canPlay)
      .toBe(true);
  });

  it("does not expose stale player data or private cards", () => {
    const stale = { ...ready(), private: { ...ready().private!, stateVersion: 1 } };
    expect(selectCurrentPlayer(stale)).toBeNull();
    expect(selectLocalPlayer(stale)).toBeNull();
    expect(selectIsOwnTurn(stale)).toBe(false);
    expect(selectValidFavorTargets(stale)).toEqual([]);
    expect(selectGameActions(stale).cards).toEqual([]);
    expect(selectGameActions(stale).drawBlocker).toBe("synchronizing");
  });
});

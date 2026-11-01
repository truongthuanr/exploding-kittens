import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RealtimeClient, type GameSocket } from "../lib/socket/client";
import { selectFinishedResult, selectRoomView } from "../lib/socket/selectors";
import { IDENTITY_KEY, INSTANCE_KEY, PENDING_KEY, SessionStorage } from "../lib/socket/storage";
import type { BootstrapResponse } from "../../shared/contracts";
class Memory {
  values = new Map<string, string>();
  getItem(k: string) { return this.values.get(k) ?? null; }
  setItem(k: string, v: string) { this.values.set(k, v); }
  removeItem(k: string) { this.values.delete(k); }
}
class FakeSocket {
  connected = false;
  handlers = new Map<string, Set<(...args: any[]) => void>>();
  sent: { event: string; data: any; ack?: (data?: any) => void }[] = [];
  io = { on: vi.fn(), off: vi.fn(), reconnection: vi.fn() };
  on(e: string, fn: (...args: any[]) => void) { const list = this.handlers.get(e) ?? new Set(); list.add(fn); this.handlers.set(e, list); return this; }
  off(e: string, fn: (...args: any[]) => void) { this.handlers.get(e)?.delete(fn); return this; }
  receive(e: string, ...args: any[]) { this.handlers.get(e)?.forEach(fn => fn(...args)); }
  emit(event: string, data: any, ack?: (data?: any) => void) { this.sent.push({ event, data, ack }); return this; }
  connect() { this.connected = true; this.receive("system:connected", { serverEpoch: "epoch", serverTime: Date.now(), idempotencyTtlMs: 120000 }); this.receive("connect"); return this; }
  disconnect() { if (this.connected) { this.connected = false; this.receive("disconnect"); } return this; }
}
function bootstrap(version = 1, game = false): BootstrapResponse {
  return {
    roomId: "room", roomCode: "ROOM01", playerId: "player", playerSessionId: "session", stateVersion: version, attemptId: null, requiresTakeover: false,
    room: { roomId: "room", roomCode: "ROOM01", stateVersion: version, status: game ? "in_game" : "waiting",
      players: [{ playerId: "player", nickname: "Alice", isReady: true, isHost: true, status: "connected" }] },
    game: game ? { roomId: "room", stateVersion: version, phase: "turn_action", currentPlayerId: "player", pendingDraws: 1, turnNumber: 1,
      players: [{ playerId: "player", nickname: "Alice", handCount: 1, status: "connected" }], discardTopCardType: null, discardCount: 0, winnerPlayerId: null, recentAction: null, actionHistory: [] } : null,
    private: game ? { stateVersion: version, playerId: "player", hand: [{ cardId: "card", cardType: "skip" }], visibleFutureCards: null } : null,
  };
}
function setup(identity = false, local = new Memory(), tab = new Memory()) {
  if (identity) local.setItem(IDENTITY_KEY, JSON.stringify({ version: 1, roomId: "room", roomCode: "ROOM01", playerId: "player", playerSessionId: "session" }));
  const storage = new SessionStorage(local, tab), socket = new FakeSocket();
  const client = new RealtimeClient(socket as unknown as GameSocket, storage, 100);
  client.start(); return { client, socket, local, tab };
}
function complete(socket: FakeSocket, value = bootstrap()) {
  const request = socket.sent.at(-1)!; request.ack?.({ ...value, attemptId: request.data.attemptId ?? null });
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

it("handles room event before ack, becomes ready and only persists identity", () => {
  const { client, socket, local, tab } = setup(); client.createRoom("Alice");
  expect(client.getSnapshot().session).toBe("joining");
  socket.receive("room:updated", bootstrap().room); complete(socket);
  expect(client.getSnapshot().session).toBe("ready");
  expect(client.getSnapshot().room?.roomId).toBe("room");
  expect(JSON.parse(local.getItem(IDENTITY_KEY)!)).not.toHaveProperty("hand");
  expect(tab.getItem(PENDING_KEY)).toBeNull();
});
it("recovers pending admission after reload with the same request ID", () => {
  const a = setup(); a.client.createRoom("Alice"); const id = a.socket.sent[0].data.requestId;
  vi.advanceTimersByTime(101);
  expect(a.client.getSnapshot()).toMatchObject({ session: "join_failed", outcome: "unknown" }); a.client.stop();
  const b = setup(false, a.local, a.tab); b.client.retryAdmission();
  expect(b.socket.sent[0].data.requestId).toBe(id); complete(b.socket);
  expect(b.client.getSnapshot().session).toBe("ready");
});
it("handles empty ack, ignores unrelated error, rejects expired admission", () => {
  const { client, socket } = setup(); client.createRoom("Alice"); client.createRoom("Alice");
  socket.receive("error", { code: "old", message: "old", requestId: "other" });
  expect(client.getSnapshot().session).toBe("joining");
  socket.sent[0].ack?.(); expect(client.getSnapshot().error?.code).toBe("invalid_ack");
  vi.advanceTimersByTime(120001); client.retryAdmission();
  expect(client.getSnapshot().error?.code).toBe("request_expired"); expect(socket.sent).toHaveLength(1);
});
it("explicitly keeps saved identity when an admission is pending and ignores its late ack", () => {
  const local = new Memory(), tab = new Memory();
  local.setItem(IDENTITY_KEY, JSON.stringify({ version: 1, roomId: "room", roomCode: "ROOM01", playerId: "player", playerSessionId: "session" }));
  tab.setItem(PENDING_KEY, JSON.stringify({
    event: "room:create", createdAt: Date.now(), expiresAt: Date.now() + 120000,
    payload: { nickname: "Other", clientInstanceId: "instance", requestId: "pending-request" },
  }));
  const { client, socket } = setup(false, local, tab);
  expect(client.getSnapshot()).toMatchObject({ pendingAdmission: true, session: "join_failed" });
  expect(socket.sent).toHaveLength(0);
  client.retryAdmission();
  const old = socket.sent.at(-1)!;
  client.continueSavedSession();
  expect(tab.getItem(PENDING_KEY)).toBeNull();
  expect(client.getSnapshot()).toMatchObject({ pendingAdmission: false, session: "restoring", room: null, private: null });
  expect(socket.sent.at(-1)?.event).toBe("player:reconnect");
  old.ack?.({ ...bootstrap(9), playerSessionId: "other-session" });
  expect(client.getSnapshot().identity?.playerSessionId).toBe("session");
  expect(client.getSnapshot().session).toBe("restoring");
  complete(socket);
  expect(client.getSnapshot()).toMatchObject({ session: "ready", pendingAdmission: false });
  expect(client.getSnapshot().identity?.playerSessionId).toBe("session");
});
it("recovers identity without silently taking over another socket", () => {
  const { client, socket } = setup(); client.createRoom("Alice"); complete(socket, { ...bootstrap(), requiresTakeover: true });
  expect(client.getSnapshot().identity?.playerSessionId).toBe("session");
  expect(client.getSnapshot().session).toBe("replaced"); expect(socket.connected).toBe(false);
});
it("restore timeout and retry ignore old ack and old error", () => {
  const { client, socket } = setup(true); const old = socket.sent[0]; vi.advanceTimersByTime(101);
  expect(client.getSnapshot().session).toBe("restore_failed"); client.retryRestore();
  old.ack?.({ ...bootstrap(), attemptId: old.data.attemptId });
  socket.receive("error", { code: "invalid_session", message: "late", requestId: old.data.attemptId });
  expect(client.getSnapshot().session).toBe("restoring"); complete(socket, bootstrap(2, true));
  expect(client.getSnapshot().session).toBe("ready");
});
it("newer updates arriving before bootstrap are preserved", () => {
  const { client, socket } = setup(true);
  socket.receive("game:state", bootstrap(3, true).game); socket.receive("player:private-state", bootstrap(3, true).private);
  complete(socket, bootstrap(2, true));
  expect(client.getSnapshot().game?.stateVersion).toBe(3); expect(client.getSnapshot().private?.stateVersion).toBe(3);
});
it("pairs equal-version public/private state in reverse order and prevents regressions", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(2, true));
  socket.receive("player:private-state", bootstrap(4, true).private);
  expect(client.getSnapshot().syncing).toBe(true); client.drawCard(); expect(socket.sent).toHaveLength(1);
  socket.receive("game:state", bootstrap(4, true).game);
  socket.receive("game:state", bootstrap(3, true).game); socket.receive("player:private-state", bootstrap(3, true).private);
  expect(client.getSnapshot().game?.stateVersion).toBe(4); expect(client.getSnapshot().syncing).toBe(false);
});
it("never queues or replays offline game actions", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(1, true)); socket.disconnect(); client.drawCard(); client.playCard("card"); socket.connect();
  expect(socket.sent.map(x => x.event)).toEqual(["player:reconnect", "player:reconnect"]);
});
it("invalid session does not erase a different identity saved by another tab", () => {
  const { client, socket, local } = setup(true);
  local.setItem(IDENTITY_KEY, JSON.stringify({ version: 1, roomId: "new", roomCode: "NEW", playerId: "other", playerSessionId: "new-session" }));
  socket.receive("error", { code: "invalid_session", message: "missing", requestId: socket.sent[0].data.attemptId });
  expect(client.getSnapshot()).toMatchObject({ session: "invalid", identity: null, private: null });
  expect(JSON.parse(local.getItem(IDENTITY_KEY)!).playerSessionId).toBe("new-session");
});
it("finished-game restore does not wait for turn:started", () => {
  const { client, socket } = setup(true); const b = bootstrap(1, true); b.room.status = "finished"; b.game!.phase = "finished"; complete(socket, b);
  expect(client.getSnapshot().session).toBe("ready");
});
it("shows finished result only from a paired snapshot for either room/game arrival order", () => {
  const final = bootstrap(2, true);
  final.room.status = "finished";
  final.game!.phase = "finished";
  final.game!.winnerPlayerId = "player";

  const roomFirst = setup(true);
  complete(roomFirst.socket, bootstrap(1, true));
  roomFirst.socket.receive("game:ended", { winnerPlayerId: "player" });
  expect(selectRoomView(roomFirst.client.getSnapshot())).toBe("game");
  roomFirst.socket.receive("room:updated", final.room);
  expect(selectRoomView(roomFirst.client.getSnapshot())).toBe("game_loading");
  roomFirst.socket.receive("game:state", final.game);
  expect(selectRoomView(roomFirst.client.getSnapshot())).toBe("game_loading");
  roomFirst.socket.receive("player:private-state", final.private);
  expect(selectRoomView(roomFirst.client.getSnapshot())).toBe("finished");
  expect(selectFinishedResult(roomFirst.client.getSnapshot())?.outcome).toBe("win");

  const gameFirst = setup(true);
  complete(gameFirst.socket, bootstrap(1, true));
  gameFirst.socket.receive("player:private-state", final.private);
  gameFirst.socket.receive("game:state", final.game);
  expect(selectRoomView(gameFirst.client.getSnapshot())).toBe("finished");
  gameFirst.socket.receive("room:updated", final.room);
  expect(selectFinishedResult(gameFirst.client.getSnapshot())?.winner?.nickname).toBe("Alice");
});

it("rejects bootstrap containing another player's hand", () => {
  const { client, socket } = setup(true); const b = bootstrap(1, true); b.private!.playerId = "other"; complete(socket, b);
  expect(client.getSnapshot().session).toBe("restore_failed");
});
it("replacement stops auto-restore, preserves shared storage, rotates instance on takeover", () => {
  const { client, socket, local, tab } = setup(true); complete(socket); const instance = tab.getItem(INSTANCE_KEY);
  socket.receive("session:replaced", { message: "other tab" }); client.retryRestore();
  expect(socket.sent).toHaveLength(1); expect(local.getItem(IDENTITY_KEY)).not.toBeNull(); expect(socket.io.reconnection).toHaveBeenCalledWith(false);
  client.takeOver(); expect(socket.sent.at(-1)!.data.takeover).toBe(true); expect(tab.getItem(INSTANCE_KEY)).not.toBe(instance);
  complete(socket); expect(client.getSnapshot().session).toBe("ready");
});
it("mount/unmount owns exactly its listeners", () => {
  const { client, socket } = setup(); socket.on("room:updated", vi.fn()); client.start(); expect(socket.handlers.get("room:updated")?.size).toBe(2);
  client.stop(); expect(socket.handlers.get("room:updated")?.size).toBe(1); client.start(); expect(socket.handlers.get("room:updated")?.size).toBe(2);
  client.stop(); expect(socket.handlers.get("room:updated")?.size).toBe(1);
});
it("invalid storage is rejected and unavailable storage falls back to memory", () => {
  const local = new Memory(); local.setItem(IDENTITY_KEY, '{"version":99}'); expect(new SessionStorage(local, local).identity()).toBeNull();
  const blocked = { getItem() { throw Error("blocked"); }, setItem() { throw Error("blocked"); }, removeItem() { throw Error("blocked"); } };
  const storage = new SessionStorage(blocked, blocked); const id = storage.instance(); expect(storage.instance()).toBe(id); expect(storage.degraded).toBe(true);
});

it("write-only storage failures preserve in-memory identity instead of reading stale disk state", () => {
  const quota = { getItem() { return null; }, setItem() { throw Error("quota"); }, removeItem() {} };
  const storage = new SessionStorage(quota, quota);
  storage.write(IDENTITY_KEY, { version: 1, roomId: "room", roomCode: "ROOM", playerId: "player", playerSessionId: "session" });
  expect(storage.identity()?.playerSessionId).toBe("session"); expect(storage.degraded).toBe(true);
});
it("corrupt JSON is cleared rather than crashing startup", () => {
  const local = new Memory(); local.setItem(IDENTITY_KEY, '{broken');
  const storage = new SessionStorage(local, local);
  expect(storage.identity()).toBeNull(); expect(local.getItem(IDENTITY_KEY)).toBeNull();
});


it("keeps one action pending until its ack and matching public/private pair arrive", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(1, true));
  const id = client.drawCard();
  expect(id).toBeTruthy();
  expect(client.getSnapshot().pendingAction).toMatchObject({ requestId: id, kind: "draw-card", status: "pending" });
  expect(client.playCard("card")).toBeNull();
  expect(socket.sent.filter(item => item.event === "turn:play-card")).toHaveLength(0);

  const action = socket.sent.at(-1)!;
  action.ack?.({ requestId: id, stateVersion: 2 });
  expect(client.getSnapshot().pendingAction?.confirmedStateVersion).toBe(2);
  socket.receive("game:state", bootstrap(2, true).game);
  expect(client.getSnapshot().pendingAction?.requestId).toBe(id);
  socket.receive("player:private-state", bootstrap(2, true).private);
  expect(client.getSnapshot().pendingAction).toBeNull();
  expect(client.getSnapshot().outcome).toBe("known");
  expect(client.playCard("card")).toBeTruthy();
});

it("accepts the matching pair before the action ack and ignores a late error", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(1, true));
  const id = client.playCard("card")!;
  const action = socket.sent.at(-1)!;
  expect(action.data).toMatchObject({ requestId: id, cardId: "card" });
  socket.receive("player:private-state", bootstrap(2, true).private);
  socket.receive("game:state", bootstrap(2, true).game);
  expect(client.getSnapshot().pendingAction?.requestId).toBe(id);
  action.ack?.({ requestId: id, stateVersion: 2 });
  expect(client.getSnapshot().pendingAction).toBeNull();
  socket.receive("error", { code: "card_not_in_hand", message: "late", requestId: id });
  expect(client.getSnapshot().error).toBeNull();
});

it("only a correlated action error releases pending status", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(1, true));
  const id = client.playCard("card", "target")!;
  const action = socket.sent.at(-1)!;
  socket.receive("error", { code: "not_current_player", message: "other", requestId: "unrelated" });
  action.ack?.();
  expect(client.getSnapshot().pendingAction?.requestId).toBe(id);
  socket.receive("error", { code: "card_not_in_hand", message: "missing", requestId: id });
  expect(client.getSnapshot().pendingAction).toBeNull();
  expect(client.getSnapshot().error).toMatchObject({ code: "card_not_in_hand", requestId: id });
  action.ack?.({ requestId: id, stateVersion: 2 });
  expect(client.getSnapshot().error?.code).toBe("card_not_in_hand");
  expect(client.drawCard()).toBeTruthy();
});

it("timeout keeps outcome unknown until restore; late ack and snapshots do not replay", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(1, true));
  const id = client.drawCard()!;
  const action = socket.sent.at(-1)!;
  vi.advanceTimersByTime(101);
  expect(client.getSnapshot().pendingAction).toMatchObject({ requestId: id, status: "unknown" });
  expect(client.getSnapshot().error?.code).toBe("action_outcome_unknown");
  socket.receive("game:state", bootstrap(2, true).game);
  socket.receive("player:private-state", bootstrap(2, true).private);
  action.ack?.({ requestId: id, stateVersion: 2 });
  expect(client.getSnapshot().pendingAction?.status).toBe("unknown");
  expect(client.drawCard()).toBeNull();

  client.retryRestore();
  expect(socket.sent.at(-1)?.event).toBe("player:reconnect");
  complete(socket, bootstrap(2, true));
  expect(client.getSnapshot().pendingAction).toBeNull();
  expect(client.getSnapshot().error).toBeNull();
  expect(socket.sent.filter(item => item.event === "turn:draw-card")).toHaveLength(1);
});

it("disconnect and invalid ack require restore before another action", () => {
  const { client, socket } = setup(true); complete(socket, bootstrap(1, true));
  const firstId = client.drawCard()!;
  const first = socket.sent.at(-1)!;
  first.ack?.({ requestId: "wrong", stateVersion: 2 });
  expect(client.getSnapshot().error?.code).toBe("invalid_action_ack");
  expect(client.playCard("card")).toBeNull();
  client.retryRestore(); complete(socket, bootstrap(2, true));
  expect(client.getSnapshot().pendingAction).toBeNull();

  const secondId = client.playCard("card")!;
  const second = socket.sent.at(-1)!;
  socket.disconnect();
  expect(client.getSnapshot().pendingAction).toMatchObject({ requestId: secondId, status: "unknown" });
  socket.connect();
  second.ack?.({ requestId: secondId, stateVersion: 3 });
  expect(client.getSnapshot().pendingAction?.status).toBe("unknown");
  complete(socket, bootstrap(3, true));
  expect(client.getSnapshot().pendingAction).toBeNull();
  expect(socket.sent.filter(item => item.event === "turn:play-card")).toHaveLength(1);
  expect(firstId).not.toBe(secondId);
});

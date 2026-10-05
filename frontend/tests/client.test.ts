import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RealtimeClient, type GameSocket } from "../lib/socket/client";
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
      players: [{ playerId: "player", nickname: "Alice", handCount: 1, status: "connected" }], discardTopCardType: null, discardCount: 0, winnerPlayerId: null, recentAction: null } : null,
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

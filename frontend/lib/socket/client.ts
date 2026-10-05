import { io, type Socket } from "socket.io-client";
import type {
  BootstrapResponse, ClientToServerEvents, ErrorEvent, PlayerPrivateStateEvent,
  PublicGameStateEvent, RoomUpdatedEvent, ServerToClientEvents, SystemConnectedEvent,
} from "../../../shared/contracts";
import { IDENTITY_KEY, INSTANCE_KEY, PENDING_KEY, SessionStorage, type Identity, type PendingAdmission } from "./storage";

export type GameSocket = Socket<ServerToClientEvents, ClientToServerEvents>;
export type SessionStatus = "none" | "joining" | "join_failed" | "ready" | "restoring" | "restore_failed" | "invalid" | "replaced";
export type RealtimeState = {
  connection: "disconnected" | "connecting" | "connected" | "reconnecting";
  session: SessionStatus;
  identity: Identity | null;
  room: RoomUpdatedEvent | null;
  game: PublicGameStateEvent | null;
  private: PlayerPrivateStateEvent | null;
  syncing: boolean;
  error: ErrorEvent | null;
  connectionError: string | null;
  outcome: "known" | "unknown" | null;
  storageDegraded: boolean;
  pendingAdmission: boolean;
  lastEvent: string | null;
};
export const EMPTY_STATE: RealtimeState = {
  connection: "disconnected", session: "none", identity: null, room: null, game: null, private: null,
  syncing: false, error: null, connectionError: null, outcome: null, storageDegraded: false,
  pendingAdmission: false, lastEvent: null,
};
type Pair = { game?: PublicGameStateEvent; private?: PlayerPrivateStateEvent };
type Operation = { id: string; generation: number; kind: "join" | "restore"; timer: ReturnType<typeof setTimeout> };

export function validBootstrap(value: unknown): value is BootstrapResponse {
  if (!value || typeof value !== "object") return false;
  const b = value as BootstrapResponse;
  if (![b.roomId, b.roomCode, b.playerId, b.playerSessionId].every(v => typeof v === "string" && v.length > 0) ||
      !Number.isSafeInteger(b.stateVersion) || b.stateVersion < 0 || !b.room || b.room.roomId !== b.roomId ||
      b.room.roomCode !== b.roomCode || b.room.stateVersion !== b.stateVersion ||
      !Array.isArray(b.room.players) || !b.room.players.some(p => p.playerId === b.playerId)) return false;
  if (b.game === null && b.private === null) return b.room.status === "waiting";
  return !!b.game && !!b.private && b.game.roomId === b.roomId && b.private.playerId === b.playerId &&
    b.game.stateVersion === b.stateVersion && b.private.stateVersion === b.stateVersion &&
    Array.isArray(b.game.players) && Array.isArray(b.private.hand);
}

export class RealtimeClient {
  private state: RealtimeState;
  private listeners = new Set<() => void>();
  private cleanup: (() => void)[] = [];
  private running = false;
  private generation = 0;
  private operation?: Operation;
  private hello?: SystemConnectedEvent;
  private helloReceivedAt = 0;
  private pending: PendingAdmission | null;
  private instance: string;
  private pairs = new Map<number, Pair>();
  private queuedRoom: RoomUpdatedEvent | null = null;
  private actionIds = new Set<string>();
  private takeoverOnConnect = false;

  constructor(readonly socket: GameSocket, private storage: SessionStorage, private timeoutMs = 10_000) {
    this.instance = storage.instance();
    this.pending = storage.pending();
    this.state = { ...EMPTY_STATE, identity: storage.identity(),
      session: this.pending ? "join_failed" : "none", pendingAdmission: !!this.pending,
      outcome: this.pending ? "unknown" : null, storageDegraded: storage.degraded };
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<RealtimeState>) {
    this.state = { ...this.state, ...patch, storageDegraded: this.storage.degraded };
    this.listeners.forEach(listener => listener());
  }
  private cancel() {
    if (this.operation) clearTimeout(this.operation.timer);
    this.operation = undefined;
    this.generation++;
  }
  private fail(code: string, message: string, kind?: "join" | "restore", unknown = false) {
    this.cancel();
    this.update({ error: { code, message }, outcome: unknown ? "unknown" : "known",
      ...(kind ? { session: kind === "join" ? "join_failed" as const : "restore_failed" as const } : {}) });
  }
  private begin(id: string, kind: "join" | "restore") {
    this.cancel();
    const generation = this.generation;
    this.operation = { id, kind, generation, timer: setTimeout(() => {
      if (this.operation?.generation === generation) this.fail("timeout", "No response; the server may have processed this request", kind, true);
    }, this.timeoutMs) };
    this.pairs.clear(); this.queuedRoom = null;
    this.update({ session: kind === "join" ? "joining" : "restoring", error: null, outcome: null, syncing: true });
    return generation;
  }
  private listen<E extends keyof ServerToClientEvents>(event: E, handler: ServerToClientEvents[E]) {
    this.socket.on(event, handler as never);
    this.cleanup.push(() => this.socket.off(event, handler as never));
  }
  start() {
    if (this.running) return;
    this.running = true;
    const connected = () => {
      this.update({ connection: "connected", connectionError: null });
      if (this.takeoverOnConnect) { this.takeoverOnConnect = false; this.restore(true); }
      else if (this.state.identity && this.state.session !== "replaced" && !this.pending) this.restore(false);
    };
    const disconnected = () => {
      const kind = this.operation?.kind;
      this.cancel(); this.hello = undefined;
      this.update({ connection: "disconnected", syncing: true,
        ...(this.state.session !== "replaced" ? { session: kind === "join" ? "join_failed" as const :
          this.state.identity ? "restore_failed" as const : this.state.session } : {}),
        ...(kind ? { outcome: "unknown" as const } : {}) });
    };
    const connectError = (error: Error) => this.update({ connectionError: error.message, connection: "disconnected" });
    const reconnecting = () => this.update({ connection: "reconnecting" });
    this.socket.on("connect", connected).on("disconnect", disconnected).on("connect_error", connectError);
    this.socket.io.on("reconnect_attempt", reconnecting);
    this.cleanup.push(() => { this.socket.off("connect", connected).off("disconnect", disconnected).off("connect_error", connectError); this.socket.io.off("reconnect_attempt", reconnecting); });
    this.listen("system:connected", hello => { this.hello = hello; this.helloReceivedAt = Date.now(); });
    this.listen("room:updated", room => {
      this.update({ lastEvent: "room:updated" });
      if (this.operation) { if (!this.queuedRoom || room.stateVersion >= this.queuedRoom.stateVersion) this.queuedRoom = room; }
      else if (this.state.session === "ready") this.applyRoom(room);
    });
    this.listen("game:state", game => this.receivePair(game.stateVersion, { game }));
    this.listen("player:private-state", privateState => this.receivePair(privateState.stateVersion, { private: privateState }));
    this.listen("error", error => this.receiveError(error));
    this.listen("session:replaced", event => this.replaced(event.message));
    this.listen("game:started", () => this.update({ lastEvent: "game:started" }));
    this.listen("turn:started", () => this.update({ lastEvent: "turn:started" }));
    this.listen("player:eliminated", () => this.update({ lastEvent: "player:eliminated" }));
    this.listen("game:ended", () => this.update({ lastEvent: "game:ended" }));
    this.update({ connection: "connecting" });
    this.socket.connect();
  }
  stop() {
    this.cancel(); this.running = false;
    this.cleanup.splice(0).forEach(fn => fn());
    this.socket.disconnect(); this.hello = undefined;
    this.update({ connection: "disconnected" });
  }
  private applyRoom(room: RoomUpdatedEvent) {
    if (room.roomId !== this.state.identity?.roomId || room.stateVersion < (this.state.room?.stateVersion ?? -1)) return;
    this.update({ room });
  }
  private receivePair(version: number, incoming: Pair) {
    if (this.state.session !== "ready" && !this.operation) return;
    if (!Number.isSafeInteger(version) || version < (this.state.game?.stateVersion ?? -1)) return;
    this.pairs.set(version, { ...this.pairs.get(version), ...incoming });
    if (this.pairs.size > 64) { this.pairs.clear(); this.fail("sync_overflow", "State updates require a fresh restore", "restore"); return; }
    if (!this.operation) this.flushPairs();
  }
  private flushPairs() {
    let game = this.state.game, privateState = this.state.private;
    for (const [version, pair] of [...this.pairs].sort(([a], [b]) => a - b)) {
      if (version < (game?.stateVersion ?? -1)) { this.pairs.delete(version); continue; }
      if (pair.game && pair.private && pair.game.roomId === this.state.identity?.roomId && pair.private.playerId === this.state.identity?.playerId) {
        game = pair.game; privateState = pair.private; this.pairs.delete(version);
      }
    }
    for (const version of this.pairs.keys()) if (version <= (game?.stateVersion ?? -1)) this.pairs.delete(version);
    this.update({ game, private: privateState, syncing: this.pairs.size > 0 });
  }
  private accept(value: BootstrapResponse | null | undefined, generation: number, attemptId?: string) {
    const op = this.operation;
    if (!op || op.generation !== generation || !this.socket.connected) return;
    if (!validBootstrap(value) || (attemptId && value.attemptId !== attemptId)) {
      this.fail("invalid_ack", "The server did not return a valid bootstrap", op.kind, true); return;
    }
    const identity: Identity = { version: 1, roomId: value.roomId, roomCode: value.roomCode,
      playerId: value.playerId, playerSessionId: value.playerSessionId };
    if (op.kind === "restore" && identity.playerSessionId !== this.state.identity?.playerSessionId) {
      this.fail("invalid_ack", "Bootstrap belongs to a different session", op.kind); return;
    }
    this.storage.write(IDENTITY_KEY, identity);
    if (op.kind === "join") { this.pending = null; this.storage.remove(PENDING_KEY); }
    this.cancel();
    this.update({ identity, room: value.room, game: value.game, private: value.private,
      session: "ready", syncing: false, pendingAdmission: !!this.pending, error: null, outcome: "known" });
    if (this.queuedRoom) this.applyRoom(this.queuedRoom);
    this.queuedRoom = null;
    this.flushPairs();
    if (value.requiresTakeover) this.replaced("Identity recovered; choose Continue in this tab to take over");
  }
  private receiveError(error: ErrorEvent) {
    const op = this.operation;
    if (error.requestId && op?.id === error.requestId) {
      if (error.code === "session_in_use") { this.replaced(error.message); return; }
      if (error.code === "invalid_session") {
        if (this.state.identity) this.storage.clearIdentity(this.state.identity.playerSessionId);
        this.cancel(); this.pairs.clear();
        this.update({ identity: null, room: null, game: null, private: null, session: "invalid", error, syncing: false }); return;
      }
      this.fail(error.code, error.message, op.kind); return;
    }
    if (!error.requestId || this.actionIds.has(error.requestId)) this.update({ error });
  }
  private replaced(message: string) {
    this.cancel(); this.pairs.clear();
    this.socket.io.reconnection(false);
    this.update({ session: "replaced", private: null, game: null, room: null, syncing: true,
      error: { code: "session_in_use", message }, outcome: "known" });
    this.socket.disconnect();
  }
  retryRestore = () => {
    if (this.state.session === "replaced") return;
    if (this.socket.connected) this.restore(false);
    else { this.socket.io.reconnection(true); this.socket.connect(); }
  };
  takeOver = () => {
    if (!this.state.identity || this.operation) return;
    // A duplicated tab may have copied the old instance ID. Rotate on explicit takeover
    // so the old tab cannot reclaim ownership after going offline and coming back.
    this.instance = crypto.randomUUID();
    this.storage.write(INSTANCE_KEY, this.instance);
    this.socket.io.reconnection(true);
    if (this.socket.connected) this.restore(true);
    else { this.takeoverOnConnect = true; this.socket.connect(); }
  };
  private restore(takeover: boolean) {
    if (!this.state.identity || !this.socket.connected || this.operation) return;
    const attemptId = crypto.randomUUID();
    const generation = this.begin(attemptId, "restore");
    this.socket.emit("player:reconnect", { playerSessionId: this.state.identity.playerSessionId,
      clientInstanceId: this.instance, takeover, attemptId }, value => this.accept(value, generation, attemptId));
  }
  createRoom = (nickname: string) => this.admission("room:create", nickname);
  joinRoom = (roomCode: string, nickname: string) => this.admission("room:join", nickname, roomCode);
  private admission(event: PendingAdmission["event"], nickname: string, roomCode?: string) {
    if (this.pending || this.operation || this.state.identity) return;
    if (!this.socket.connected || !this.hello) { this.fail("not_connected", "Wait for the connection", "join"); return; }
    const now = Date.now();
    const serverNow = this.hello.serverTime + now - this.helloReceivedAt;
    this.pending = { event, createdAt: now, expiresAt: now + this.hello.idempotencyTtlMs,
      payload: { nickname, clientInstanceId: this.instance,
        requestId: `${this.hello.serverEpoch}:${serverNow}:${crypto.randomUUID()}`,
        ...(event === "room:join" ? { roomCode: roomCode!.trim().toUpperCase() } : {}) } };
    this.storage.write(PENDING_KEY, this.pending);
    this.update({ pendingAdmission: true });
    this.retryAdmission();
  }
  retryAdmission = () => {
    if (!this.pending || this.operation) return;
    if (!this.socket.connected) { this.fail("not_connected", "Reconnect before retrying admission", "join", true); return; }
    if (Date.now() >= this.pending.expiresAt) { this.fail("request_expired", "Request expired. Explicitly discard it before starting a new admission", "join"); return; }
    const generation = this.begin(this.pending.payload.requestId, "join");
    const ack = (value?: BootstrapResponse | null) => this.accept(value, generation);
    if (this.pending.event === "room:join" && "roomCode" in this.pending.payload) this.socket.emit("room:join", this.pending.payload, ack);
    else this.socket.emit("room:create", this.pending.payload, ack);
  };
  /** Explicit user recovery: an unknown admission may have left a seat on the server. */
  discardAdmission = () => {
    if (this.operation || this.state.identity) return;
    this.pending = null; this.storage.remove(PENDING_KEY);
    // Release any binding from an admission whose ack was lost.
    this.socket.disconnect(); this.socket.connect();
    this.update({ session: "none", pendingAdmission: false, outcome: null, error: null });
  };
  private canAct() {
    if (this.socket.connected && this.state.session === "ready" && !this.state.syncing &&
        (this.state.room?.status === "waiting" || this.state.game && this.state.private)) return true;
    this.update({ error: { code: "not_ready", message: "Wait until your session is synchronized" } }); return false;
  }
  private requestId() {
    const id = crypto.randomUUID(); this.actionIds.add(id);
    if (this.actionIds.size > 100) this.actionIds.delete(this.actionIds.values().next().value!);
    return id;
  }
  ready = (isReady: boolean) => { if (this.canAct()) this.socket.emit("room:ready", { isReady }); };
  startGame = () => { if (this.canAct()) this.socket.emit("game:start", { requestId: this.requestId() }); };
  drawCard = () => { if (this.canAct()) this.socket.emit("turn:draw-card", { requestId: this.requestId() }); };
  playCard = (cardId: string, targetPlayerId?: string) => {
    if (this.canAct()) this.socket.emit("turn:play-card", { cardId, requestId: this.requestId(), ...(targetPlayerId ? { targetPlayerId } : {}) });
  };
}

export function createSocket() {
  return io(process.env.NEXT_PUBLIC_SOCKET_URL || "http://localhost:8000", {
    path: process.env.NEXT_PUBLIC_SOCKET_PATH || "/socket.io", autoConnect: false,
    reconnection: true, retries: 0,
  }) as GameSocket;
}

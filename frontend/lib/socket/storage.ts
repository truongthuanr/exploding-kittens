import type { RoomCreateResponse, RoomCreateRequest, RoomJoinRequest } from "../../../shared/contracts";

export const IDENTITY_KEY = "boardgame.identity.v1";
export const INSTANCE_KEY = "boardgame.instance.v1";
export const PENDING_KEY = "boardgame.pending.v1";
export type Identity = RoomCreateResponse & { version: 1 };
export type PendingAdmission = {
  event: "room:create" | "room:join";
  payload: RoomCreateRequest | RoomJoinRequest;
  createdAt: number;
  expiresAt: number;
};
export type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object";
const nonempty = (v: unknown): v is string => typeof v === "string" && v.length > 0;
export function isIdentity(v: unknown): v is Identity {
  return record(v) && v.version === 1 && [v.roomId, v.roomCode, v.playerId, v.playerSessionId].every(nonempty);
}
export function isPending(v: unknown): v is PendingAdmission {
  if (!record(v) || !record(v.payload)) return false;
  return (v.event === "room:create" || v.event === "room:join") &&
    [v.payload.requestId, v.payload.clientInstanceId, v.payload.nickname].every(nonempty) &&
    (v.event !== "room:join" || nonempty(v.payload.roomCode)) &&
    typeof v.createdAt === "number" && Number.isFinite(v.createdAt) &&
    typeof v.expiresAt === "number" && Number.isFinite(v.expiresAt) && v.expiresAt > v.createdAt;
}

/** Never persists snapshots or hands. Storage failures fall back to this tab's memory. */
export class SessionStorage {
  degraded = false;
  private memory = new Map<string, unknown>();
  private unavailable = new Set<string>();
  constructor(private local?: StorageLike, private tab?: StorageLike) {
    if (!local || !tab) this.degraded = true;
  }
  private storage(key: string) { return key === IDENTITY_KEY ? this.local : this.tab; }
  read<T>(key: string, validate: (value: unknown) => value is T): T | null {
    let value: unknown = this.memory.get(key);
    try {
      const target = this.storage(key);
      if (target && !this.unavailable.has(key)) {
        const raw = target.getItem(key);
        if (raw === null) value = null;
        else {
          try { value = JSON.parse(raw); }
          catch { this.remove(key); return null; }
        }
      }
    } catch { this.degraded = true; this.unavailable.add(key); }
    if (value != null && !validate(value)) { this.remove(key); return null; }
    return validate(value) ? value : null;
  }
  write(key: string, value: unknown) {
    this.memory.set(key, value);
    try { this.storage(key)?.setItem(key, JSON.stringify(value)); }
    catch { this.degraded = true; this.unavailable.add(key); }
  }
  remove(key: string) {
    this.memory.delete(key);
    try { this.storage(key)?.removeItem(key); }
    catch { this.degraded = true; this.unavailable.add(key); }
  }
  identity() { return this.read(IDENTITY_KEY, isIdentity); }
  pending() { return this.read(PENDING_KEY, isPending); }
  instance(): string {
    const id = this.read(INSTANCE_KEY, nonempty) ?? crypto.randomUUID();
    this.write(INSTANCE_KEY, id);
    return id;
  }
  clearIdentity(sessionId: string) {
    if (this.identity()?.playerSessionId === sessionId) this.remove(IDENTITY_KEY);
  }
}

export function browserStorage(): SessionStorage {
  let local: Storage | undefined, tab: Storage | undefined;
  try { local = window.localStorage; } catch { /* private mode */ }
  try { tab = window.sessionStorage; } catch { /* private mode */ }
  return new SessionStorage(local, tab);
}

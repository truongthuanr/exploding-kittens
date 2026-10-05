"use client";
import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { createSocket, EMPTY_STATE, RealtimeClient } from "./client";
import { browserStorage } from "./storage";

let shared: RealtimeClient | undefined;
let consumers = 0;
let releaseTimer: ReturnType<typeof setTimeout> | undefined;
const Context = createContext<RealtimeClient | null>(null);

export function SocketProvider({ children }: { children: ReactNode }) {
  const [client, setClient] = useState<RealtimeClient | null>(null);
  useEffect(() => {
    if (releaseTimer) clearTimeout(releaseTimer);
    consumers++;
    const configured = Number(process.env.NEXT_PUBLIC_SOCKET_TIMEOUT_MS || 10000);
    shared ??= new RealtimeClient(createSocket(), browserStorage(), Number.isFinite(configured) && configured > 0 ? configured : 10000);
    shared.start(); setClient(shared);
    return () => {
      consumers--;
      // React Strict Mode immediately remounts effects. Keep one socket through that cycle.
      releaseTimer = setTimeout(() => {
        if (consumers === 0) { shared?.stop(); shared = undefined; }
      }, 0);
    };
  }, []);
  return <Context.Provider value={client}>{children}</Context.Provider>;
}
const noopSubscribe = () => () => {};
const serverSnapshot = () => EMPTY_STATE;
export function useRealtime() {
  const client = useContext(Context);
  const state = useSyncExternalStore(client?.subscribe ?? noopSubscribe, client?.getSnapshot ?? serverSnapshot, serverSnapshot);
  return { state, client };
}

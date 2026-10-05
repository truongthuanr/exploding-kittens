"use client";
import { useState } from "react";
import { useRealtime } from "../lib/socket/provider";
export default function Page() {
  const { state, client } = useRealtime();
  const [nickname, setNickname] = useState("");
  const [roomCode, setRoomCode] = useState("");
  const [cardId, setCardId] = useState("");
  const [target, setTarget] = useState("");
  const connected = state.connection === "connected";
  const ready = connected && state.session === "ready" && !state.syncing;
  const admission = connected && !state.identity && !state.pendingAdmission;
  return <main>
    <p className="eyebrow">EXPLODING KITTENS LITE / DEVELOPMENT</p>
    <h1>Realtime check</h1>
    <p>Trang kiểm tra kết nối và phục hồi phiên. Mở browser context riêng để thử với người chơi khác.</p>
    <section aria-label="Connection status" className="status">
      <span>Connection: <strong data-testid="connection">{state.connection}</strong></span>
      <span>Session: <strong data-testid="session">{state.session}</strong></span>
      <span>Room: <strong data-testid="room-code">{state.identity?.roomCode ?? "—"}</strong></span>
      <span>Player: <strong data-testid="player-id">{state.identity?.playerId ?? "—"}</strong></span>
    </section>
    {state.connectionError && <p role="alert">Connection: {state.connectionError}</p>}
    {state.error && <p role="alert">{state.error.code}: {state.error.message}{state.outcome === "unknown" && " — Kết quả chưa xác định."}</p>}
    {state.storageDegraded && <p role="alert">Không lưu được đầy đủ phiên trên trình duyệt; reload có thể mất thông tin phục hồi.</p>}
    <section>
      <h2>Create / join</h2>
      <label>Nickname<input aria-label="Nickname" value={nickname} onChange={e => setNickname(e.target.value)} /></label>
      <label>Room code<input aria-label="Room code" value={roomCode} onChange={e => setRoomCode(e.target.value)} /></label>
      <div className="actions">
        <button disabled={!admission || !nickname.trim()} onClick={() => client?.createRoom(nickname.trim())}>Create room</button>
        <button disabled={!admission || !nickname.trim() || !roomCode.trim()} onClick={() => client?.joinRoom(roomCode, nickname.trim())}>Join room</button>
        {state.pendingAdmission && <>
          <button disabled={!connected || state.session === "joining"} onClick={() => client?.retryAdmission()}>Retry admission</button>
          <button disabled={state.session === "joining"} onClick={() => client?.discardAdmission()}>Discard pending request</button>
          <p>Bỏ request không hoàn tác room/player mà server có thể đã tạo.</p>
        </>}
      </div>
    </section>
    <section>
      <h2>Session / actions</h2>
      <div className="actions">
        <button disabled={!state.identity || state.session === "replaced" || state.session === "restoring"} onClick={() => client?.retryRestore()}>Retry restore</button>
        <button disabled={state.session !== "replaced"} onClick={() => client?.takeOver()}>Tiếp tục ở tab này</button>
        <button disabled={!ready} onClick={() => client?.ready(true)}>Ready</button>
        <button disabled={!ready} onClick={() => client?.ready(false)}>Unready</button>
        <button disabled={!ready} onClick={() => client?.startGame()}>Start game</button>
        <button disabled={!ready || !state.game} onClick={() => client?.drawCard()}>Draw card</button>
      </div>
      <label>Card ID<input value={cardId} onChange={e => setCardId(e.target.value)} /></label>
      <label>Target player (optional)<input value={target} onChange={e => setTarget(e.target.value)} /></label>
      <button disabled={!ready || !cardId} onClick={() => client?.playCard(cardId, target || undefined)}>Play card</button>
    </section>
    <section><h2>Snapshots</h2>
      <p>Last event: {state.lastEvent ?? "—"} · Synchronizing: {String(state.syncing)}</p>
      <div className="snapshots">
        <article><h3>Room</h3><pre data-testid="room-state">{JSON.stringify(state.room, null, 2)}</pre></article>
        <article><h3>Public game</h3><pre data-testid="game-state">{JSON.stringify(state.game, null, 2)}</pre></article>
        <article><h3>Your private state</h3><pre data-testid="private-state">{JSON.stringify(state.private, null, 2)}</pre></article>
      </div>
    </section>
  </main>;
}

"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRealtime } from "../lib/socket/provider";
import type { RealtimeClient, RealtimeState } from "../lib/socket/client";
import { selectLobbyActions, selectRoomView, type LobbyBlocker, type RoomView } from "../lib/socket/selectors";
import { describeRealtimeError } from "../lib/socket/error-messages";

const reasons: Record<LobbyBlocker, string> = {
  connection_unavailable: "Chưa kết nối với máy chủ.",
  session_unavailable: "Phiên người chơi chưa sẵn sàng.",
  admission_conflict: "Cần xử lý yêu cầu vào phòng đang chờ.",
  synchronizing: "Đang đồng bộ trạng thái phòng.",
  room_unavailable: "Chưa có thông tin phòng hợp lệ.",
  room_not_waiting: "Phòng không còn ở trạng thái chờ.",
  player_missing: "Không tìm thấy người chơi của bạn trong phòng.",
  ready_pending: "Đang chờ cập nhật Ready.",
  start_pending: "Đang chờ máy chủ bắt đầu trận.",
  not_host: "Chỉ chủ phòng có thể bắt đầu trận.",
  player_count: "Cần từ 3 đến 5 người chơi.",
  players_not_ready: "Tất cả người chơi cần Ready.",
  players_disconnected: "Tất cả người chơi cần kết nối.",
};

function StatusMessages({ state, client }: { state: RealtimeState; client: RealtimeClient | null }) {
  const error = state.error && describeRealtimeError(state.error, state.session);
  return <>
    {state.connectionError && <p role="alert">Kết nối: {state.connectionError}</p>}
    {error && <div className="notice" role="alert">
      <p>{error.message}</p>
      {error.action === "retry_restore" && state.session === "ready" &&
        <button type="button" disabled={!client} onClick={() => client?.retryRestore()}>Thử khôi phục phiên</button>}
    </div>}
    {state.storageDegraded && <p role="status">Không lưu được phiên đầy đủ; tải lại trang có thể mất khả năng khôi phục.</p>}
  </>;
}

type AdmissionMode = "create" | "join";

function Home({ state, client }: { state: RealtimeState; client: RealtimeClient | null }) {
  const [mode, setMode] = useState<AdmissionMode>("create");
  const [nickname, setNickname] = useState("");
  const [roomCode, setRoomCode] = useState("");
  const [errors, setErrors] = useState<{ nickname?: string; roomCode?: string }>({});
  const nicknameRef = useRef<HTMLInputElement>(null);
  const roomCodeRef = useRef<HTMLInputElement>(null);
  const errorAction = state.error && describeRealtimeError(state.error, state.session).action;
  const canRetryAdmission = !state.error || errorAction === "retry_admission";
  const canSubmit = state.connection === "connected" && !state.pendingAdmission &&
    state.session !== "joining" && !!client;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    const name = nickname.trim();
    const code = roomCode.trim();
    const nextErrors = {
      nickname: name ? undefined : "Nhập tên người chơi.",
      roomCode: mode === "join" && !code ? "Nhập mã phòng." : undefined,
    };
    setErrors(nextErrors);
    if (nextErrors.nickname) { nicknameRef.current?.focus(); return; }
    if (nextErrors.roomCode) { roomCodeRef.current?.focus(); return; }
    if (mode === "create") client?.createRoom(name);
    else client?.joinRoom(code, name);
  };

  return <section className="panel">
    <h1 tabIndex={-1}>Chơi cùng bạn bè</h1>
    <p>Tạo phòng mới hoặc nhập mã phòng để tham gia.</p>
    {state.session === "invalid" && <p role="status">Phiên trước không còn hợp lệ. Bạn có thể tạo hoặc vào phòng mới.</p>}
    <form noValidate onSubmit={submit}>
      <fieldset className="mode-options" disabled={state.pendingAdmission || state.session === "joining"}>
        <legend>Chọn cách tham gia</legend>
        <label><input type="radio" name="admission-mode" value="create" checked={mode === "create"}
          onChange={() => { setMode("create"); setErrors({}); }} /> Tạo phòng</label>
        <label><input type="radio" name="admission-mode" value="join" checked={mode === "join"}
          onChange={() => { setMode("join"); setErrors({}); }} /> Vào phòng</label>
      </fieldset>
      <label htmlFor="nickname">Nickname</label>
      <input ref={nicknameRef} id="nickname" name="nickname" autoComplete="nickname"
        value={nickname} aria-invalid={!!errors.nickname}
        aria-describedby={errors.nickname ? "nickname-error" : undefined}
        onChange={event => { setNickname(event.target.value); setErrors(previous => ({ ...previous, nickname: undefined })); }} />
      {errors.nickname && <p id="nickname-error" className="field-error" role="alert">{errors.nickname}</p>}
      {mode === "join" && <>
        <label htmlFor="room-code-input">Room code</label>
        <input ref={roomCodeRef} id="room-code-input" name="roomCode" autoCapitalize="characters"
          value={roomCode} aria-invalid={!!errors.roomCode}
          aria-describedby={errors.roomCode ? "room-code-error" : undefined}
          onChange={event => { setRoomCode(event.target.value); setErrors(previous => ({ ...previous, roomCode: undefined })); }} />
        {errors.roomCode && <p id="room-code-error" className="field-error" role="alert">{errors.roomCode}</p>}
      </>}
      <button disabled={!canSubmit} type="submit">{mode === "create" ? "Create room" : "Join room"}</button>
    </form>
    {state.pendingAdmission && <div className="notice">
      <p>Yêu cầu tạo hoặc vào phòng đang chờ. Máy chủ có thể đã xử lý dù chưa nhận được phản hồi.</p>
      <div className="button-row">
        <button type="button" disabled={!client || state.connection !== "connected" || state.session === "joining" || !canRetryAdmission}
          onClick={() => client?.retryAdmission()}>Retry admission</button>
        <button type="button" className="secondary" disabled={!client || state.session === "joining"}
          onClick={() => client?.discardAdmission()}>Bỏ yêu cầu đang chờ</button>
      </div>
      <p className="helper">Bỏ yêu cầu không xóa phòng hoặc người chơi mà máy chủ có thể đã tạo.</p>
    </div>}
  </section>;
}

function Recovery({ view, state, client }: { view: RoomView; state: RealtimeState; client: RealtimeClient | null }) {
  const copy: Record<string, [string, string]> = {
    admission_conflict: ["Xung đột phiên", "Có phiên đã lưu và một yêu cầu vào phòng đang chờ. Yêu cầu đó có thể đã thành công dù mất phản hồi."],
    restoring: ["Đang khôi phục phiên", "Vui lòng chờ máy chủ xác nhận người chơi và phòng."],
    restore_failed: ["Không khôi phục được phiên", "Kiểm tra kết nối rồi thử lại."],
    replaced: ["Phiên đang hoạt động ở tab khác", "Tiếp tục tại tab này sẽ thay thế tab đang dùng phiên."],
    safe_recovery: ["Đang đồng bộ", "Chưa có dữ liệu phòng hợp lệ để hiển thị. Vui lòng thử khôi phục phiên."],
  };
  const [title, message] = copy[view] ?? copy.safe_recovery;
  return <section className="panel">
    <h1 tabIndex={-1}>{title}</h1><p role="status">{message}</p>
    {view === "admission_conflict" && <>
      <p className="helper">Tiếp tục phiên đã lưu sẽ bỏ yêu cầu đang chờ. Nếu máy chủ đã xử lý yêu cầu đó, một người chơi có thể vẫn còn trong phòng nhưng bị ngắt kết nối.</p>
      <button disabled={!client} onClick={() => client?.continueSavedSession()}>Tiếp tục phiên đã lưu</button>
    </>}
    {(view === "restore_failed" || view === "safe_recovery") &&
      <button disabled={!client} onClick={() => client?.retryRestore()}>Thử khôi phục lại</button>}
    {view === "replaced" &&
      <button disabled={!client} onClick={() => client?.takeOver()}>Tiếp tục ở tab này</button>}
  </section>;
}

function Lobby({ state, client, readOnly }: { state: RealtimeState; client: RealtimeClient | null; readOnly: boolean }) {
  const room = state.room!;
  const current = room.players.find(player => player.playerId === state.identity?.playerId);
  const [pendingReady, setPendingReady] = useState<{ version: number; error: RealtimeState["error"] } | null>(null);
  const [pendingStart, setPendingStart] = useState<{ version: number; error: RealtimeState["error"] } | null>(null);

  useEffect(() => {
    if (pendingReady && (room.stateVersion > pendingReady.version || (state.error && state.error !== pendingReady.error))) {
      setPendingReady(null);
    }
    if (pendingStart && (room.status !== "waiting" || (state.error && state.error !== pendingStart.error))) {
      setPendingStart(null);
    }
  }, [room.stateVersion, room.status, state.error, pendingReady, pendingStart]);

  const actions = selectLobbyActions(state, { ready: !!pendingReady, start: !!pendingStart });
  const ready = () => {
    if (!actions.canToggleReady || !client || !current) return;
    setPendingReady({ version: room.stateVersion, error: state.error });
    client.ready(!current.isReady);
  };
  const start = () => {
    if (!actions.canStart || !client) return;
    setPendingStart({ version: room.stateVersion, error: state.error });
    client.startGame();
  };

  return <section className="panel">
    <div className="room-heading">
      <div><p className="eyebrow">Phòng chờ</p><h1 tabIndex={-1}>Room <span data-testid="room-code">{room.roomCode}</span></h1></div>
      <p>{room.players.length} / 5 người chơi</p>
    </div>
    {readOnly && <div className="notice" role="status">
      <p>Mất kết nối. Bạn đang xem trạng thái phòng đã lưu; các thao tác tạm khóa.</p>
      <button type="button" onClick={() => client?.retryRestore()}>Thử kết nối lại</button>
    </div>}
    {state.syncing && !readOnly && <p role="status">Đang đồng bộ phòng; các thao tác tạm khóa.</p>}
    <ul className="players">
      {room.players.map(player => <li key={player.playerId} className="player">
        <span className="player-name">{player.nickname} {player.playerId === state.identity?.playerId && <span className="badge">Bạn</span>} {player.isHost && <span className="badge">Chủ phòng</span>}</span>
        <span className="badge">{player.isReady ? "Ready" : "Chưa Ready"}</span>
        <span className="badge">{player.status === "connected" ? "Đang kết nối" : player.status === "disconnected" ? "Mất kết nối" : "Đã bị loại"}</span>
      </li>)}
    </ul>
    <div className="button-row">
      <button type="button" disabled={!actions.canToggleReady || readOnly} onClick={ready}>
        {current?.isReady ? "Unready" : "Ready"}
      </button>
      {current?.isHost && <button type="button" disabled={!actions.canStart || readOnly} onClick={start}>Start game</button>}
    </div>
    {actions.readyBlocker && !readOnly && <p className="helper">{reasons[actions.readyBlocker]}</p>}
    {current?.isHost ? actions.startBlockers.length > 0 && <ul className="requirements">
      {actions.startBlockers.map(reason => <li key={reason}>{reasons[reason]}</li>)}
    </ul> : actions.startBlockers.length === 1 && actions.startBlockers[0] === "not_host" &&
      <p className="helper">Đã đủ điều kiện. Đang chờ chủ phòng bắt đầu trận.</p>}
  </section>;
}

export default function Page() {
  const { state, client } = useRealtime();
  const view = selectRoomView(state);
  const previousView = useRef(view);
  useEffect(() => {
    if (previousView.current !== view) {
      document.querySelector<HTMLElement>(".panel h1")?.focus();
      previousView.current = view;
    }
  }, [view]);
  return <main className="page">
    <header className="site-header">
      <span className="brand">Exploding Kittens Lite</span>
      <span className="connection" role="status">Kết nối: <strong data-testid="connection">{state.connection}</strong></span>
    </header>
    <span className="sr-only" data-testid="session">{state.session}</span>
    {view === "home" || view === "admission_home" ? <Home state={state} client={client} /> :
      view === "lobby" || view === "read_only_lobby" ? <Lobby state={state} client={client} readOnly={view === "read_only_lobby"} /> :
      view === "game_loading" ? <section className="panel"><h1 tabIndex={-1}>Đang tải trận đấu</h1><p role="status">Đang đồng bộ trạng thái trận đấu.</p></section> :
      view === "game" ? <section className="panel"><h1 tabIndex={-1}>Trận đấu đã bắt đầu</h1><p>Giao diện bàn chơi sẽ được bổ sung ở bước tiếp theo.</p></section> :
      view === "finished" ? <section className="panel"><h1 tabIndex={-1}>Trận đấu đã kết thúc</h1><p>Giao diện kết quả sẽ được bổ sung ở bước tiếp theo.</p></section> :
      <Recovery view={view} state={state} client={client} />}
    <StatusMessages state={state} client={client} />
  </main>;
}

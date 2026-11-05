"use client";

import { useEffect, useState } from "react";
import type { PlayerStatus } from "../../shared/contracts";
import type { RealtimeClient, RealtimeState } from "../lib/socket/client";
import { selectFinishedResult } from "../lib/socket/selectors";
import { PublicActionLog } from "./public-action-log";

const statusNames: Record<PlayerStatus, string> = {
  connected: "Còn kết nối",
  disconnected: "Mất kết nối",
  eliminated: "Đã bị loại",
};

export function FinishedResultView({ state, client }: { state: RealtimeState; client?: RealtimeClient | null }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const result = selectFinishedResult(state);
  if (!result) {
    return <section className="panel"><h1 tabIndex={-1}>Đang tải kết quả</h1>
      <p role="status">Đang đồng bộ trạng thái cuối của trận đấu.</p></section>;
  }

  const controlsLocked = !client || state.connection !== "connected" || state.session !== "ready" ||
    state.syncing || state.game!.stateVersion < state.room!.stateVersion ||
    !!state.pendingAction || !!state.pendingPostGame;
  const resultMessage = result.outcome === "win" ? "Bạn đã thắng!" :
    result.outcome === "loss" ? "Bạn đã thua." : "Trận đấu kết thúc không có người thắng.";

  return <section className="panel finished-result">
    <div>
      <p className="eyebrow">Phòng {state.room!.roomCode}</p>
      <h1 tabIndex={-1}>Trận đấu đã kết thúc</h1>
      <p className="result-message" role="status">{resultMessage}</p>
      <p className="winner-name">Người thắng: <strong>{result.winner?.nickname ?? "Không có"}</strong></p>
    </div>

    <section aria-labelledby="final-players-heading">
      <h2 id="final-players-heading">Kết quả người chơi</h2>
      <ul className="final-players">
        {result.players.map(player => <li key={player.playerId} className="final-player">
          <div className="final-player-name"><strong>{player.nickname}</strong>
            {player.playerId === result.localPlayer.playerId && <span className="badge">Bạn</span>}
          </div>
          <span className="final-player-status">
            <span className="badge">{result.winner
              ? result.winner.playerId === player.playerId ? "Thắng" : "Thua"
              : "Không có người thắng"}</span>
            <span className="badge">{statusNames[player.status]}</span>
          </span>
        </li>)}
      </ul>
    </section>

    <section aria-labelledby="rematch-heading">
      <h2 id="rematch-heading">Chơi lại cùng phòng</h2>
      <p role="status" aria-live="polite">{state.room!.players.filter(player => player.rematchReady).length} / {state.room!.players.length} người chơi đã đồng ý.</p>
      <ul className="rematch-players">
        {state.room!.players.map(player => {
          const deadline = player.rematchGraceDeadlineMs;
          const seconds = deadline === null || now === null ? null :
            Math.max(0, Math.ceil((deadline - now - state.serverTimeOffsetMs) / 1000));
          return <li key={player.playerId} className="player">
            <span className="player-name">{player.nickname} {player.playerId === state.identity?.playerId && <span className="badge">Bạn</span>}</span>
            <span>{player.rematchReady ? "Đã đồng ý" : "Chưa đồng ý"}</span>
            {player.status === "disconnected" && <span>
              Mất kết nối{deadline !== null ? ` · Còn ${seconds === null ? "đang tính" : `${seconds} giây`} để quay lại` : ""}
            </span>}
          </li>;
        })}
      </ul>
      <p className="helper">Trận mới bắt đầu sau khi mọi người đồng ý, trở về phòng chờ và Ready lại.</p>
      <div className="button-row">
        {state.room!.players.find(player => player.playerId === state.identity?.playerId)?.rematchReady
          ? <button type="button" className="secondary" disabled={controlsLocked}
              onClick={() => client?.rematchWithdraw()}>Rút phiếu Play Again</button>
          : <button type="button" disabled={controlsLocked}
              onClick={() => client?.rematchReady()}>Play Again</button>}
        <button type="button" className="secondary" disabled={controlsLocked}
          onClick={() => client?.leaveRoom()}>Leave Room</button>
      </div>
      {state.pendingPostGame && <div className="notice" role="status" aria-live="polite">
        <p>{state.pendingPostGame.status === "pending"
          ? "Đang chờ máy chủ xác nhận yêu cầu sau trận."
          : "Chưa xác định được yêu cầu trước đã thành công hay chưa."}</p>
        {state.pendingPostGame.status === "unknown" && <div className="button-row">
          <button type="button" disabled={!client || state.connection !== "connected" || state.session === "restoring"}
            onClick={() => client?.retryRestore()}>Khôi phục phiên</button>
          {state.pendingPostGame.restored && <button type="button" className="secondary" disabled={!client || state.connection !== "connected" || state.session !== "ready"}
            onClick={() => client?.retryPostGame()}>Thử lại yêu cầu</button>}
        </div>}
      </div>}
    </section>

    <PublicActionLog game={state.game!} />
  </section>;
}

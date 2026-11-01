import type { PlayerStatus } from "../../shared/contracts";
import type { RealtimeState } from "../lib/socket/client";
import { selectFinishedResult } from "../lib/socket/selectors";
import { PublicActionLog } from "./public-action-log";

const statusNames: Record<PlayerStatus, string> = {
  connected: "Còn kết nối",
  disconnected: "Mất kết nối",
  eliminated: "Đã bị loại",
};

export function FinishedResultView({ state }: { state: RealtimeState }) {
  const result = selectFinishedResult(state);
  if (!result) {
    return <section className="panel"><h1 tabIndex={-1}>Đang tải kết quả</h1>
      <p role="status">Đang đồng bộ trạng thái cuối của trận đấu.</p></section>;
  }

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

    <PublicActionLog game={state.game!} />
  </section>;
}

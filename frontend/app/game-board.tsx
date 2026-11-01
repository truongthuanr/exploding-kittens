import type { CardType, GamePhase, PlayerStatus } from "../../shared/contracts";
import type { RealtimeState } from "../lib/socket/client";
import {
  GAME_ACTION_BLOCKER_TEXT, hasCurrentGamePair, selectCurrentPlayer, selectGameActions,
  selectIsEliminated, selectIsOwnTurn,
} from "../lib/socket/selectors";

const cardNames: Record<CardType, string> = {
  exploding_kitten: "Mèo nổ",
  defuse: "Gỡ bom",
  skip: "Bỏ lượt",
  attack: "Tấn công",
  shuffle: "Xáo bài",
  see_the_future: "Nhìn trước tương lai",
  favor: "Xin bài",
};

const phaseNames: Record<GamePhase, string> = {
  lobby: "Phòng chờ",
  setup: "Chuẩn bị",
  turn_action: "Chọn hành động",
  turn_draw: "Rút bài",
  resolving_explosion: "Đang xử lý Mèo nổ",
  finished: "Đã kết thúc",
};

const playerStatuses: Record<PlayerStatus, string> = {
  connected: "Đang kết nối",
  disconnected: "Mất kết nối",
  eliminated: "Đã bị loại",
};

export function GameBoard({ state }: { state: RealtimeState }) {
  if (state.connection !== "connected" || state.session !== "ready" ||
      state.pendingAdmission || state.syncing || !hasCurrentGamePair(state)) {
    return <section className="panel"><h1 tabIndex={-1}>Đang tải trận đấu</h1>
      <p role="status">Đang đồng bộ trạng thái trận đấu.</p></section>;
  }

  const game = state.game!;
  const privateState = state.private!;
  const currentPlayer = selectCurrentPlayer(state);
  const ownTurn = selectIsOwnTurn(state);
  const eliminated = selectIsEliminated(state);
  const actions = selectGameActions(state);
  const turnMessage = eliminated ? "Bạn đã bị loại và có thể theo dõi trận đấu." :
    ownTurn ? "Đến lượt bạn." : currentPlayer ? `Đang đến lượt ${currentPlayer.nickname}.` :
    "Đang chờ xác định người chơi hiện tại.";

  return <section className="panel game-board">
    <div className="room-heading">
      <div><p className="eyebrow">Phòng {state.room!.roomCode}</p>
        <h1 tabIndex={-1}>Trận đấu đã bắt đầu</h1></div>
      <span className="badge">Lượt {game.turnNumber}</span>
    </div>
    <p className="turn-message" role="status">{turnMessage}</p>
    <dl className="game-summary">
      <div><dt>Người đang chơi</dt><dd>{currentPlayer?.nickname ?? "Không xác định"}</dd></div>
      <div><dt>Lượt cần rút</dt><dd>{game.pendingDraws}</dd></div>
      <div><dt>Giai đoạn</dt><dd>{phaseNames[game.phase]}</dd></div>
      <div><dt>Chồng bài bỏ</dt><dd>{game.discardCount} lá · {game.discardTopCardType
        ? `Trên cùng: ${cardNames[game.discardTopCardType]}` : "Chưa có lá nào"}</dd></div>
    </dl>

    <section aria-labelledby="game-players-heading">
      <h2 id="game-players-heading">Người chơi</h2>
      <ul className="game-players">
        {game.players.map(player => <li key={player.playerId} className="game-player">
          <div className="game-player-name"><strong>{player.nickname}</strong>
            {player.playerId === state.identity!.playerId && <span className="badge">Bạn</span>}
            {player.playerId === game.currentPlayerId && <span className="badge">Đang chơi</span>}
          </div>
          <span>{player.handCount} lá trên tay</span>
          <span className="badge">{playerStatuses[player.status]}</span>
        </li>)}
      </ul>
    </section>

    <section aria-labelledby="my-hand-heading">
      <h2 id="my-hand-heading">Bài trên tay bạn</h2>
      {actions.cards.length === 0 ? <p className="helper">Bạn chưa có lá bài nào.</p> :
        <ul className="hand-cards">
          {actions.cards.map(card => <li key={card.cardId} className="hand-card">
            <strong>{cardNames[card.cardType]}</strong>
            <span className="helper">{card.blocker
              ? GAME_ACTION_BLOCKER_TEXT[card.blocker] : "Có thể đánh trong lượt này."}</span>
          </li>)}
        </ul>}
      {actions.drawBlocker && <p className="helper" role="status">
        Rút bài: {GAME_ACTION_BLOCKER_TEXT[actions.drawBlocker]}
      </p>}
    </section>

    {privateState.visibleFutureCards !== null && <section aria-labelledby="future-cards-heading">
      <h2 id="future-cards-heading">Các lá bài sắp tới</h2>
      {privateState.visibleFutureCards.length === 0
        ? <p className="helper">Không có lá bài nào để xem trước.</p>
        : <ol className="future-cards">{privateState.visibleFutureCards.map((cardType, index) =>
          <li key={index}>{cardNames[cardType]}</li>)}</ol>}
    </section>}
  </section>;
}

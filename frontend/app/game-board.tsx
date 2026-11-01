"use client";

import { useEffect, useState } from "react";
import type { CardType, GamePhase, PlayerStatus } from "../../shared/contracts";
import type { RealtimeClient, RealtimeState } from "../lib/socket/client";
import { describeRealtimeError } from "../lib/socket/error-messages";
import { PublicActionLog } from "./public-action-log";
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

export function GameBoard({ state, client }: { state: RealtimeState; client: RealtimeClient | null }) {
  const [favorCardId, setFavorCardId] = useState<string | null>(null);
  const [targetPlayerId, setTargetPlayerId] = useState<string | null>(null);
  const [lastRequestId, setLastRequestId] = useState<string | null>(null);

  useEffect(() => {
    setFavorCardId(null);
    setTargetPlayerId(null);
  }, [state.game?.stateVersion, state.connection, state.session, state.syncing]);
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
  const selectedFavor = actions.cards.find(card => card.cardId === favorCardId &&
    card.cardType === "favor" && card.canPlay);
  const actionError = !state.pendingAction && lastRequestId && state.error?.requestId === lastRequestId
    ? describeRealtimeError(state.error, state.session) : null;
  const submitPlay = (cardId: string, target?: string) => {
    const requestId = client?.playCard(cardId, target);
    if (requestId) setLastRequestId(requestId);
    return requestId;
  };
  const submitDraw = () => {
    const requestId = client?.drawCard();
    if (requestId) setLastRequestId(requestId);
  };
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
      {favorCardId && <p id="favor-planning-note" className="helper" role="status">
        Hoàn tất hoặc hủy chọn mục tiêu Xin bài trước khi dùng hành động khác.
      </p>}
      {actions.cards.length === 0 ? <p className="helper">Bạn chưa có lá bài nào.</p> :
        <ul className="hand-cards">
          {actions.cards.map((card, index) => <li key={card.cardId} className="hand-card">
            <strong>{cardNames[card.cardType]}</strong>
            <span className="helper" id={`card-reason-${index}`}>{card.blocker
              ? GAME_ACTION_BLOCKER_TEXT[card.blocker] : "Có thể đánh trong lượt này."}</span>
            {card.blocker !== "card_not_playable" &&
              <button type="button" disabled={!card.canPlay || !client || !!favorCardId}
                aria-describedby={favorCardId ? `card-reason-${index} favor-planning-note` : `card-reason-${index}`}
                onClick={() => {
                  if (card.cardType === "favor") {
                    setFavorCardId(card.cardId);
                    setTargetPlayerId(null);
                  } else submitPlay(card.cardId);
                }}>
                Đánh {cardNames[card.cardType]}
              </button>}
          </li>)}
        </ul>}
    </section>

    <section aria-labelledby="game-actions-heading" className="game-actions">
      <h2 id="game-actions-heading">Hành động</h2>
      <h3>Rút bài</h3>
      <p className="helper">{ownTurn && !eliminated
        ? `Bạn còn ${game.pendingDraws} lượt rút cần hoàn thành.`
        : "Chỉ người đang chơi mới có thể rút bài."}</p>
      <button type="button" disabled={!actions.canDraw || !client || !!favorCardId}
        aria-describedby={favorCardId ? "favor-planning-note" : actions.drawBlocker ? "draw-blocker" : undefined}
        onClick={submitDraw}>Rút bài</button>
      {actions.drawBlocker && <p id="draw-blocker" className="helper">
        {GAME_ACTION_BLOCKER_TEXT[actions.drawBlocker]}
      </p>}
      {favorCardId && selectedFavor && <fieldset className="favor-picker">
        <legend>Chọn người nhận yêu cầu Xin bài</legend>
        <p className="helper">Chọn một đối thủ còn bài, rồi xác nhận hoặc hủy.</p>
        {actions.favorTargets.map(player => <label key={player.playerId}>
          <input type="radio" name="favor-target" value={player.playerId}
            checked={targetPlayerId === player.playerId}
            onChange={() => setTargetPlayerId(player.playerId)} />
          {player.nickname} ({player.handCount} lá)
        </label>)}
        <div className="button-row">
          <button type="button" disabled={!targetPlayerId || !client}
            onClick={() => {
              if (!targetPlayerId || !actions.favorTargets.some(player => player.playerId === targetPlayerId)) return;
              if (submitPlay(favorCardId, targetPlayerId)) {
                setFavorCardId(null);
                setTargetPlayerId(null);
              }
            }}>Xác nhận Xin bài</button>
          <button type="button" className="secondary"
            onClick={() => { setFavorCardId(null); setTargetPlayerId(null); }}>Hủy</button>
        </div>
      </fieldset>}
      {state.pendingAction && <p className="helper" role="status">{state.pendingAction.status === "unknown"
        ? "Chưa rõ máy chủ đã xử lý thao tác hay chưa. Hãy khôi phục phiên trước khi tiếp tục."
        : "Đang chờ máy chủ xác nhận và đồng bộ trạng thái mới."}</p>}
      {state.pendingAction?.status === "unknown" && <button type="button" className="secondary"
        disabled={!client} onClick={() => client?.retryRestore()}>Khôi phục phiên</button>}
      {actionError && <div className="notice" role="alert">
        <p>{actionError.message}</p>
        {actionError.action === "retry_restore" && <button type="button" className="secondary"
          onClick={() => client?.retryRestore()}>Khôi phục phiên</button>}
      </div>}
    </section>

    {privateState.visibleFutureCards !== null && <section aria-labelledby="future-cards-heading">
      <h2 id="future-cards-heading">Các lá bài sắp tới</h2>
      {privateState.visibleFutureCards.length === 0
        ? <p className="helper">Không có lá bài nào để xem trước.</p>
        : <ol className="future-cards">{privateState.visibleFutureCards.map((cardType, index) =>
          <li key={index}>{cardNames[cardType]}</li>)}</ol>}
    </section>}
    <PublicActionLog game={game} />
  </section>;
}

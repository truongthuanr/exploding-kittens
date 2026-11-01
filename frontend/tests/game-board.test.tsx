import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GameBoard } from "../app/game-board";
import { EMPTY_STATE, type RealtimeState } from "../lib/socket/client";

const state: RealtimeState = {
  ...EMPTY_STATE,
  connection: "connected",
  session: "ready",
  identity: { version: 1, roomId: "room", roomCode: "ROOM01", playerId: "self", playerSessionId: "session" },
  room: {
    roomId: "room", roomCode: "ROOM01", status: "in_game", stateVersion: 4,
    players: [
      { playerId: "self", nickname: "Alice", isHost: true, isReady: true, status: "connected" },
      { playerId: "other", nickname: "Bob", isHost: false, isReady: true, status: "connected" },
    ],
  },
  game: {
    roomId: "room", stateVersion: 4, phase: "turn_action", currentPlayerId: "self",
    pendingDraws: 2, turnNumber: 3,
    players: [
      { playerId: "self", nickname: "Alice", handCount: 2, status: "connected" },
      { playerId: "other", nickname: "Bob", handCount: 4, status: "connected" },
    ],
    discardTopCardType: "attack", discardCount: 5, winnerPlayerId: null,
    recentAction: null, actionHistory: [],
  },
  private: {
    playerId: "self", stateVersion: 4,
    hand: [
      { cardId: "private-skip", cardType: "skip" },
      { cardId: "private-defuse", cardType: "defuse" },
    ],
    visibleFutureCards: ["shuffle", "favor"],
  },
};

describe("GameBoard", () => {
  it("shows the public board and only the local private hand and future cards", () => {
    const html = renderToStaticMarkup(<GameBoard state={state} />);
    expect(html).toContain("Trận đấu đã bắt đầu");
    expect(html).toContain("Lượt 3");
    expect(html).toContain("Lượt cần rút");
    expect(html).toContain(">2</dd>");
    expect(html).toContain("Trên cùng: Tấn công");
    expect(html).toContain("Bob");
    expect(html).toContain("4 lá trên tay");
    expect(html).toContain("Bỏ lượt");
    expect(html).toContain("Gỡ bom");
    expect(html).toContain("Lá bài này không thể đánh trực tiếp.");
    expect(html).toContain("Các lá bài sắp tới");
    expect(html).toContain("Xáo bài");
    expect(html).not.toContain("private-skip");
    expect(html).not.toContain("private-defuse");
  });

  it("clears future cards with the next private snapshot and keeps eliminated players read only", () => {
    const next: RealtimeState = {
      ...state,
      room: { ...state.room!, stateVersion: 5 },
      game: {
        ...state.game!, stateVersion: 5, currentPlayerId: "other",
        players: state.game!.players.map(player => player.playerId === "self"
          ? { ...player, status: "eliminated" as const } : player),
      },
      private: { ...state.private!, stateVersion: 5, visibleFutureCards: null },
    };
    const html = renderToStaticMarkup(<GameBoard state={next} />);
    expect(html).toContain("Bạn đã bị loại");
    expect(html).toContain("Đã bị loại");
    expect(html).not.toContain("Các lá bài sắp tới");
    expect(html).not.toContain("Có thể đánh trong lượt này.");
  });

  it("hides the board and private hand while restoring", () => {
    const html = renderToStaticMarkup(<GameBoard state={{ ...state, connection: "disconnected" }} />);
    expect(html).toContain("Đang tải trận đấu");
    expect(html).not.toContain("Bài trên tay bạn");
    expect(html).not.toContain("Bob");
  });
});

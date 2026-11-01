import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GameBoard } from "../app/game-board";
import { EMPTY_STATE, type RealtimeClient, type RealtimeState } from "../lib/socket/client";

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
      { playerId: "self", nickname: "Alice", handCount: 7, status: "connected" },
      { playerId: "other", nickname: "Bob", handCount: 4, status: "connected" },
    ],
    discardTopCardType: "attack", discardCount: 5, winnerPlayerId: null,
    recentAction: null, actionHistory: [],
  },
  private: {
    playerId: "self", stateVersion: 4,
    hand: [
      { cardId: "private-skip", cardType: "skip" },
      { cardId: "private-attack", cardType: "attack" },
      { cardId: "private-shuffle", cardType: "shuffle" },
      { cardId: "private-future", cardType: "see_the_future" },
      { cardId: "private-favor", cardType: "favor" },
      { cardId: "private-defuse", cardType: "defuse" },
      { cardId: "private-bomb", cardType: "exploding_kitten" },
    ],
    visibleFutureCards: ["shuffle", "favor"],
  },
};

describe("GameBoard", () => {
  it("shows the public board and only the local private hand and future cards", () => {
    const html = renderToStaticMarkup(<GameBoard state={state} client={null} />);
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
    const html = renderToStaticMarkup(<GameBoard state={next} client={null} />);
    expect(html).toContain("Bạn đã bị loại");
    expect(html).toContain("Đã bị loại");
    expect(html).not.toContain("Các lá bài sắp tới");
    expect(html).not.toContain("Có thể đánh trong lượt này.");
  });

  it("hides the board and private hand while restoring", () => {
    const html = renderToStaticMarkup(<GameBoard state={{ ...state, connection: "disconnected" }} client={null} />);
    expect(html).toContain("Đang tải trận đấu");
    expect(html).not.toContain("Bài trên tay bạn");
    expect(html).not.toContain("Bob");
  });
});

const connectedClient = {} as RealtimeClient;

describe("GameBoard action controls", () => {
  it("offers normal playable cards and draw without a direct Defuse control", () => {
    const html = renderToStaticMarkup(<GameBoard state={state} client={connectedClient} />);
    for (const name of ["Bỏ lượt", "Tấn công", "Xáo bài", "Nhìn trước tương lai", "Xin bài"]) {
      expect(html).toContain(`Đánh ${name}</button>`);
    }
    expect(html).toMatch(/<button[^>]*>Rút bài<\/button>/);
    expect(html).not.toContain("Đánh Gỡ bom");
    expect(html).not.toContain("Đánh Mèo nổ");
  });

  it("explains and disables controls outside the local player's turn", () => {
    const otherTurn: RealtimeState = {
      ...state, game: { ...state.game!, currentPlayerId: "other" },
    };
    const html = renderToStaticMarkup(<GameBoard state={otherTurn} client={connectedClient} />);
    expect(html).toContain("Chưa đến lượt của bạn.");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Đánh Bỏ lượt<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Rút bài<\/button>/);
  });

  it("locks controls while an action is pending or its outcome is unknown", () => {
    const pending: RealtimeState = { ...state, pendingAction: {
      requestId: "req", kind: "draw-card", status: "pending", confirmedStateVersion: 5,
    } };
    const pendingHtml = renderToStaticMarkup(<GameBoard state={pending} client={connectedClient} />);
    expect(pendingHtml).toContain("Đang chờ máy chủ xác nhận");
    expect(pendingHtml).toMatch(/<button[^>]*disabled=""[^>]*>Rút bài<\/button>/);
    const unknownHtml = renderToStaticMarkup(<GameBoard state={{ ...pending,
      pendingAction: { ...pending.pendingAction!, status: "unknown" },
    }} client={connectedClient} />);
    expect(unknownHtml).toContain("Chưa rõ máy chủ đã xử lý");
    expect(unknownHtml).toContain("Khôi phục phiên");
  });
});

describe("Favor availability", () => {
  it("disables Favor when no living opponent has a card", () => {
    const noTarget: RealtimeState = {
      ...state,
      game: { ...state.game!, players: state.game!.players.map(player => player.playerId === "other"
        ? { ...player, handCount: 0 } : player) },
    };
    const html = renderToStaticMarkup(<GameBoard state={noTarget} client={connectedClient} />);
    expect(html).toContain("Không có đối thủ hợp lệ để dùng Favor.");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Đánh Xin bài<\/button>/);
  });
});

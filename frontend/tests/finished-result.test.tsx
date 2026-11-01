import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { EMPTY_STATE, type RealtimeState } from "../lib/socket/client";
import { selectFinishedResult, selectRoomView } from "../lib/socket/selectors";
import { FinishedResultView } from "../app/finished-result";

const finished: RealtimeState = {
  ...EMPTY_STATE,
  connection: "connected", session: "ready",
  identity: { version: 1, roomId: "room", roomCode: "ROOM01", playerId: "alice", playerSessionId: "session" },
  room: {
    roomId: "room", roomCode: "ROOM01", status: "finished", stateVersion: 8,
    players: [
      { playerId: "alice", nickname: "Alice", isReady: true, isHost: true, status: "eliminated" },
      { playerId: "bob", nickname: "Bob", isReady: true, isHost: false, status: "connected" },
      { playerId: "cat", nickname: "Cat", isReady: true, isHost: false, status: "eliminated" },
    ],
  },
  game: {
    roomId: "room", stateVersion: 8, phase: "finished", currentPlayerId: "bob",
    pendingDraws: 0, turnNumber: 5,
    players: [
      { playerId: "alice", nickname: "Alice", handCount: 0, status: "eliminated" },
      { playerId: "bob", nickname: "Bob", handCount: 2, status: "connected" },
      { playerId: "cat", nickname: "Cat", handCount: 0, status: "eliminated" },
    ],
    discardTopCardType: "exploding_kitten", discardCount: 14, winnerPlayerId: "bob",
    recentAction: null,
    actionHistory: [
      { stateVersion: 8, actorPlayerId: "alice", actionType: "eliminate",
        summary: "Alice was eliminated" },
    ],
  },
  private: { playerId: "alice", stateVersion: 8, hand: [], visibleFutureCards: null },
};

describe("FinishedResultView", () => {
  it("shows the winner, local loss, every final status, and public history", () => {
    const html = renderToStaticMarkup(<FinishedResultView state={finished} />);
    expect(html).toContain("Trận đấu đã kết thúc");
    expect(html).toContain("Bạn đã thua.");
    expect(html).toContain("Người thắng: <strong>Bob</strong>");
    expect(html).toContain("Alice");
    expect(html).toContain("Cat");
    expect(html).toContain("Đã bị loại");
    expect(html).toContain("Còn kết nối");
    expect(html).toContain("50 hành động gần nhất");
    expect(html).toContain("Alice đã bị loại sau khi rút Mèo nổ.");
    expect(html).not.toContain("Bài trên tay bạn");
  });

  it("shows local victory from the finished game snapshot", () => {
    const winner: RealtimeState = {
      ...finished,
      game: {
        ...finished.game!, winnerPlayerId: "alice",
        players: finished.game!.players.map(player => player.playerId === "alice"
          ? { ...player, status: "connected" as const } : player),
      },
    };
    expect(selectFinishedResult(winner)?.outcome).toBe("win");
    const html = renderToStaticMarkup(<FinishedResultView state={winner} />);
    expect(html).toContain("Bạn đã thắng!");
    expect(html).toContain("Người thắng: <strong>Alice</strong>");
  });

  it("handles a finished server state with no surviving winner", () => {
    const noWinner: RealtimeState = {
      ...finished, game: { ...finished.game!, winnerPlayerId: null },
    };
    expect(selectFinishedResult(noWinner)?.outcome).toBe("no_winner");
    const html = renderToStaticMarkup(<FinishedResultView state={noWinner} />);
    expect(html).toContain("Trận đấu kết thúc không có người thắng.");
    expect(html).toContain("Người thắng: <strong>Không có</strong>");
  });

  it("waits for a synchronized finished pair regardless of room/game arrival order", () => {
    const staleRoomFirst: RealtimeState = {
      ...finished,
      game: { ...finished.game!, stateVersion: 7, phase: "turn_action" },
      private: { ...finished.private!, stateVersion: 7 },
    };
    expect(selectRoomView(staleRoomFirst)).toBe("game_loading");
    expect(selectFinishedResult(staleRoomFirst)).toBeNull();

    const gameFirst: RealtimeState = {
      ...finished, room: { ...finished.room!, status: "in_game" },
    };
    expect(selectRoomView(gameFirst)).toBe("finished");
    expect(selectFinishedResult(gameFirst)?.winner?.nickname).toBe("Bob");

    const notificationOnly: RealtimeState = {
      ...staleRoomFirst, lastEvent: "game:ended",
    };
    expect(selectFinishedResult(notificationOnly)).toBeNull();
    expect(selectRoomView({ ...finished, session: "restoring" })).toBe("restoring");
    expect(selectRoomView(finished)).toBe("finished");
  });
});

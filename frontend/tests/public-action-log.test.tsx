import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ActionHistoryEntry, PublicGameStateEvent } from "../../shared/contracts";
import { PublicActionLog } from "../app/public-action-log";

const game: PublicGameStateEvent = {
  roomId: "room", stateVersion: 10, phase: "turn_action", currentPlayerId: "alice",
  pendingDraws: 1, turnNumber: 2, discardTopCardType: null, discardCount: 0,
  winnerPlayerId: null, recentAction: null, actionHistory: [],
  players: [
    { playerId: "alice", nickname: "Alice", handCount: 3, status: "connected" },
    { playerId: "bob", nickname: "Bob", handCount: 2, status: "connected" },
  ],
};

function entry(stateVersion: number, actionType: ActionHistoryEntry["actionType"],
               actorPlayerId = "alice", targetPlayerId?: string): ActionHistoryEntry {
  return { stateVersion, actionType, actorPlayerId, targetPlayerId,
    summary: "PRIVATE_SECRET_CARD_TYPE and hidden deck order" };
}

describe("PublicActionLog", () => {
  it("shows a clear empty state", () => {
    const html = renderToStaticMarkup(<PublicActionLog game={game} />);
    expect(html).toContain("50 hành động gần nhất");
    expect(html).toContain("Chưa có hành động nào được ghi nhận.");
    expect(html).not.toContain("<li");
  });

  it("renders names and resolved outcomes in server sequence without private summary text", () => {
    const snapshot = { ...game, actionHistory: [
      entry(8, "eliminate", "bob"),
      entry(3, "start_game"),
      entry(5, "play_favor", "alice", "bob"),
      entry(7, "defuse", "alice"),
      entry(6, "draw_card", "bob"),
    ] };
    const html = renderToStaticMarkup(<PublicActionLog game={snapshot} />);
    expect(html.indexOf('data-state-version="3"')).toBeLessThan(html.indexOf('data-state-version="5"'));
    expect(html.indexOf('data-state-version="7"')).toBeLessThan(html.indexOf('data-state-version="8"'));
    expect(html).toContain("Alice đã dùng Xin bài với Bob.");
    expect(html).toContain("Bob đã rút một lá bài.");
    expect(html).toContain("Alice đã dùng Gỡ bom sau khi rút Mèo nổ.");
    expect(html).toContain("Bob đã bị loại sau khi rút Mèo nổ.");
    expect(html).not.toContain("PRIVATE_SECRET_CARD_TYPE");
    expect(html).not.toContain("hidden deck order");
  });

  it("keeps only the latest 50 entries from a restored public snapshot", () => {
    const actionHistory = Array.from({ length: 52 }, (_, index) => entry(index + 1, "draw_card")).reverse();
    const html = renderToStaticMarkup(<PublicActionLog game={{ ...game, actionHistory }} />);
    expect((html.match(/data-state-version=/g) ?? [])).toHaveLength(50);
    expect(html).not.toContain('data-state-version="1"');
    expect(html).not.toContain('data-state-version="2"');
    expect(html.indexOf('data-state-version="3"')).toBeLessThan(html.indexOf('data-state-version="52"'));
  });
});

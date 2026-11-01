import type { ActionHistoryEntry, PublicGameStateEvent } from "../../shared/contracts";

function describeAction(entry: ActionHistoryEntry, names: Map<string, string>): string {
  const actor = names.get(entry.actorPlayerId) ?? "Người chơi";
  const target = entry.targetPlayerId ? names.get(entry.targetPlayerId) ?? "một người chơi" : "một người chơi";
  switch (entry.actionType) {
    case "start_game": return `${actor} đã bắt đầu trận đấu.`;
    case "play_skip": return `${actor} đã dùng Bỏ lượt.`;
    case "play_attack": return `${actor} đã dùng Tấn công.`;
    case "play_shuffle": return `${actor} đã xáo chồng bài rút.`;
    case "play_see_the_future": return `${actor} đã xem trước các lá bài sắp tới.`;
    case "play_favor": return `${actor} đã dùng Xin bài với ${target}.`;
    case "draw_card": return `${actor} đã rút một lá bài.`;
    case "defuse": return `${actor} đã dùng Gỡ bom sau khi rút Mèo nổ.`;
    case "explode": return `${actor} đã rút Mèo nổ.`;
    case "eliminate": return `${actor} đã bị loại sau khi rút Mèo nổ.`;
    case "turn_advanced": return `${actor} đã kết thúc lượt.`;
    default: return `${actor} đã thực hiện một hành động.`;
  }
}

export function PublicActionLog({ game }: { game: PublicGameStateEvent }) {
  const names = new Map(game.players.map(player => [player.playerId, player.nickname]));
  const entries = [...game.actionHistory]
    .sort((left, right) => left.stateVersion - right.stateVersion)
    .slice(-50);

  return <section className="public-action-log" aria-labelledby="action-log-heading">
    <h2 id="action-log-heading">50 hành động gần nhất</h2>
    <p className="helper">Nhật ký công khai, theo thứ tự diễn ra.</p>
    {entries.length === 0
      ? <p className="helper">Chưa có hành động nào được ghi nhận.</p>
      : <ol className="public-action-log-list">
        {entries.map(entry => <li key={entry.stateVersion} data-state-version={entry.stateVersion}>
          {describeAction(entry, names)}
        </li>)}
      </ol>}
  </section>;
}

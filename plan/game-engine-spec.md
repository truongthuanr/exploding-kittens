# Game Engine Specification: Exploding Kittens Lite

## 1. Mục tiêu

Tài liệu này định nghĩa luật game theo cách máy có thể thực thi. Đây là nguồn chân lý cho backend game engine.

## 2. Nguyên tắc cốt lõi

- Server là nguồn chân lý duy nhất của game state.
- Client không được quyền quyết định luật, thứ tự deck hay kết quả action.
- Mọi state transition phải đi qua một action validator và resolver tuần tự.
- Hidden information phải được lọc trước khi gửi ra ngoài server.

## 3. Core enums / types

## `RoomStatus`

- `waiting`
- `starting`
- `in_game`
- `finished`

## `GamePhase`

- `lobby`
- `setup`
- `turn_action`
- `turn_draw`
- `resolving_explosion`
- `finished`

## `CardType`

- `exploding_kitten`
- `defuse`
- `skip`
- `attack`
- `shuffle`
- `see_the_future`
- `favor`

## `PlayerStatus`

- `connected`
- `disconnected`
- `eliminated`

## `ServerGameState`

```ts
type ServerGameState = {
  roomId: string;
  roomStatus: RoomStatus;
  phase: GamePhase;
  turnNumber: number;
  currentPlayerId: string;
  pendingDraws: number;
  players: PlayerState[];
  drawPile: CardInstance[];
  discardPile: CardInstance[];
  eliminatedPlayerIds: string[];
  winnerPlayerId: string | null;
  actionLock: boolean;
  createdAt: string;
  updatedAt: string;
};
```

## `PlayerPrivateState`

```ts
type PlayerPrivateState = {
  playerId: string;
  hand: CardInstance[];
  visibleFutureCards: CardType[] | null;
};
```

## `PlayerState`

```ts
type PlayerState = {
  playerId: string;
  nickname: string;
  status: PlayerStatus;
  handCount: number;
  seatIndex: number;
  isHost: boolean;
  isReady: boolean;
};
```

## 4. Cấu trúc deck và setup

### Quy tắc setup

- Game hỗ trợ 3-5 người.
- Mỗi người chơi bắt đầu với 1 `Defuse`.
- Sau đó mỗi người nhận thêm số lá khởi đầu cố định do implementation chọn; mặc định là 4 lá, tổng khởi đầu là 5 lá.
- Số lượng `Exploding Kitten` trong deck bằng `playerCount - 1`.
- Các `Exploding Kitten` không được chia vào tay khởi đầu.
- Sau khi chia bài xong mới trộn `Exploding Kitten` vào draw pile.

### Deck composition mặc định

MVP không cần bám chính xác bản commercial. Dùng cấu hình hợp lý sau:

- `Exploding Kitten`: `playerCount - 1`
- `Defuse`: `playerCount` lá khởi đầu đã phát, cộng thêm `2` lá trong deck
- `Skip`: `4`
- `Attack`: `4`
- `Shuffle`: `4`
- `See the Future`: `5`
- `Favor`: `4`

Implementer có thể điều chỉnh con số này nếu playtest thấy nhịp độ chưa ổn, nhưng nếu chưa có dữ liệu thì dùng cấu hình trên làm mặc định.

## 5. State ownership

### State server giữ toàn cục

- Toàn bộ `drawPile`
- Toàn bộ `discardPile`
- Tay bài đầy đủ của tất cả người chơi
- `currentPlayerId`
- `pendingDraws`
- `phase`
- `actionLock`
- Danh sách người bị loại
- Winner

### State public broadcast

- Danh sách người chơi
- `currentPlayerId`
- `pendingDraws`
- `discardPile` hoặc top discard summary
- `turnNumber`
- Trạng thái room/game
- Ai bị loại
- Kết quả action vừa resolve

### State riêng từng player

- Hand của chính họ
- Kết quả `See the Future` do chính họ tạo ra
- Session metadata phục vụ reconnect

## 6. Turn lifecycle

### 6.1 Start game

- Room chuyển `waiting` -> `starting`
- Tạo thứ tự ghế ngồi
- Tạo deck action cards
- Phát `1 Defuse + 4 cards` cho từng player
- Trộn `Exploding Kitten` vào draw pile
- Chọn `currentPlayerId` theo seat đầu tiên
- Set `pendingDraws = 1`
- Set `phase = turn_action`
- Room chuyển sang `in_game`

### 6.2 Player action window

- Chỉ `currentPlayerId` với trạng thái chưa bị loại mới được hành động.
- Trong `phase = turn_action`, player có thể:
  - chơi `skip`
  - chơi `attack`
  - chơi `shuffle`
  - chơi `see_the_future`
  - chơi `favor`
  - chuyển sang draw step bằng `turn:draw-card`
- Sau mỗi action hợp lệ, server resolve xong rồi mới nhận action tiếp.

### 6.3 Draw step

- Khi player gửi `turn:draw-card`, set `phase = turn_draw`.
- Rút lá trên cùng của `drawPile`.
- Nếu lá vừa rút không phải `exploding_kitten`:
  - thêm vào hand người chơi
  - `pendingDraws -= 1`
  - nếu `pendingDraws > 0`, set lại `phase = turn_action` để người chơi tiếp tục cùng lượt
  - nếu `pendingDraws == 0`, kết thúc lượt và chuyển sang người kế tiếp với `pendingDraws = 1`
- Nếu lá vừa rút là `exploding_kitten`, chuyển sang explosion flow.

## 7. Resolve rules cho từng loại bài

## `Skip`

- Điều kiện: đúng lượt, player có lá `skip`.
- Effect:
  - chuyển lá `skip` từ hand sang discard.
  - `pendingDraws -= 1`
  - nếu `pendingDraws == 0`, kết thúc lượt và chuyển turn.
  - nếu `pendingDraws > 0`, player vẫn giữ lượt hiện tại trong `phase = turn_action`.

## `Attack`

- Điều kiện: đúng lượt, player có lá `attack`.
- Effect:
  - chuyển lá `attack` sang discard.
  - kết thúc lượt hiện tại mà không cần rút.
  - chuyển turn sang người kế tiếp còn sống.
  - người kế tiếp nhận `pendingDraws = pendingDraws + 1`.

### Attack stacking policy đã chốt

- `pendingDraws` của lượt hiện tại mặc định là 1.
- Nếu player hiện tại chơi `Attack` khi `pendingDraws = 1`, người kế tiếp nhận `2`.
- Nếu vì lý do nào đó người chơi hiện tại đang có `pendingDraws > 1` và dùng `Attack`, người kế tiếp nhận `pendingDraws + 1`.
- Player mới vẫn có thể chơi tiếp `Attack` trong lượt của họ để chuyển gánh nặng tiếp.

## `Shuffle`

- Điều kiện: đúng lượt, player có lá `shuffle`.
- Effect:
  - lá bài được discard.
  - server random lại thứ tự `drawPile`.
  - không đổi `pendingDraws`.
  - phase quay lại `turn_action`.

## `See the Future`

- Điều kiện: đúng lượt, player có lá `see_the_future`.
- Effect:
  - lá bài được discard.
  - server đọc 3 lá đầu `drawPile` hoặc ít hơn nếu deck không đủ 3 lá.
  - chỉ gửi kết quả này cho player hiện tại qua private payload.
  - không đổi `drawPile`.
  - phase quay lại `turn_action`.

## `Favor`

- Điều kiện: đúng lượt, player có lá `favor`, target hợp lệ.
- Effect:
  - lá `favor` được discard.
  - server chọn ngẫu nhiên 1 lá từ hand của target.
  - lá đó được chuyển sang hand của người chơi hiện tại.
  - cả phòng chỉ biết rằng đã có trao đổi bài, không biết loại bài nhận được.
  - phase quay lại `turn_action`.

## 8. Exploding flow

### 8.1 Kích hoạt

- Xảy ra khi player rút lá `exploding_kitten` từ draw pile.
- `phase = resolving_explosion`
- `actionLock = true`

### 8.2 Nếu player có `Defuse`

- Tự động remove 1 `defuse` khỏi hand player.
- `defuse` vào discard pile.
- `exploding_kitten` được đặt lại vào draw pile theo một vị trí ngẫu nhiên do server chọn.
- `pendingDraws -= 1`
- Nếu `pendingDraws == 0`, kết thúc lượt và chuyển turn.
- Nếu `pendingDraws > 0`, phase trở lại `turn_action` cho cùng player.
- `actionLock = false`

### 8.3 Nếu player không có `Defuse`

- Player chuyển sang `eliminated`.
- `exploding_kitten` vào discard pile.
- Toàn bộ hand còn lại của player vào discard pile.
- `pendingDraws` của player không còn ý nghĩa sau khi bị loại.
- Nếu số player còn sống là 1, game kết thúc.
- Nếu còn nhiều hơn 1, lượt chuyển sang người kế tiếp còn sống với `pendingDraws = 1`.
- `actionLock = false`

## 9. Chuyển lượt

### Quy tắc chọn người kế tiếp

- Đi theo `seatIndex` tăng dần dạng vòng tròn.
- Bỏ qua mọi player `eliminated`.
- Nếu không tìm được player còn sống khác, game phải kết thúc ngay trước bước này.

### Khi kết thúc lượt bình thường

- `turnNumber += 1`
- `currentPlayerId = nextAlivePlayerId`
- `pendingDraws = 1`
- `phase = turn_action`

### Khi chuyển lượt do `Attack`

- `turnNumber += 1`
- `currentPlayerId = nextAlivePlayerId`
- `pendingDraws = inheritedPendingDraws`
- `phase = turn_action`

## 10. Validation rules

Mọi action từ client phải pass toàn bộ điều kiện sau:

- Room status là `in_game`
- Game phase cho phép action tương ứng
- Player là `currentPlayerId`
- Player không ở trạng thái `eliminated`
- `actionLock = false`
- Request idempotency key chưa được xử lý trước đó, nếu hệ thống có hỗ trợ
- Card tồn tại trong hand player

Validation thêm theo action:

- `skip`: `pendingDraws >= 1`
- `attack`: không cần target
- `shuffle`: draw pile phải có ít nhất 2 lá để shuffle có ý nghĩa, nhưng vẫn cho phép nếu ít hơn để giữ luật đơn giản
- `see_the_future`: luôn hợp lệ nếu có bài
- `favor`: target phải tồn tại, active, khác người chơi hiện tại và có ít nhất 1 lá trên tay
- `draw-card`: chỉ hợp lệ khi không còn pending resolution khác

## 11. Hidden information rules

- Không broadcast chi tiết hand của bất kỳ player nào.
- Không broadcast kết quả `See the Future`.
- Không broadcast card cụ thể được lấy bởi `Favor`.
- Chỉ broadcast hand count sau mọi biến động hand.
- Khi reconnect, chỉ gửi full hand cho đúng player sở hữu session.

## 12. End game

Game kết thúc khi:

- Chỉ còn 1 player có trạng thái chưa `eliminated`.

Khi kết thúc:

- `roomStatus = finished`
- `phase = finished`
- `winnerPlayerId` được set
- Không chấp nhận thêm `turn:play-card` hoặc `turn:draw-card`
- Cho phép flow rematch

## 13. Các mặc định đã chốt

- Người chơi có thể chơi nhiều action cards trong một lượt trước khi rút.
- `Defuse` là automatic resolution, không cần client xác nhận.
- `Exploding Kitten` sau khi defuse được đặt lại ngẫu nhiên vào draw pile.
- `Favor` lấy ngẫu nhiên 1 lá, không cho target tự chọn ở MVP.
- Không hỗ trợ self-target cho `Favor`.
- Không hỗ trợ `Nope` ở MVP.
- Không reshuffle discard vào deck khi deck cạn. Nếu deck cạn thật, coi là trạng thái không hỗ trợ và trả lỗi hệ thống để implementer bổ sung sau nếu cần.

## 14. Engine test scenarios

- Start game với 3, 4, 5 người cho đúng số `Exploding Kitten`.
- `Skip` giảm `pendingDraws` đúng khi đang chịu ảnh hưởng `Attack`.
- `Attack` chuyển gánh lượt rút đúng sang người kế tiếp.
- `Shuffle` không làm lộ draw order.
- `See the Future` chỉ gửi private payload cho đúng player.
- `Favor` không làm lộ loại bài bị lấy.
- Draw thường làm kết thúc hoặc tiếp tục lượt đúng theo `pendingDraws`.
- Draw `Exploding Kitten` với `Defuse` sống sót và bomb quay lại deck.
- Draw `Exploding Kitten` không có `Defuse` bị loại và bỏ toàn bộ hand.
- Game kết thúc ngay khi chỉ còn 1 người active.
- Double-submit cùng action không làm state chuyển hai lần.

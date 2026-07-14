# Functional Specification: Exploding Kittens Lite

## 1. Mục đích

Tài liệu này mô tả các tính năng và hành vi hệ thống ở mức functional. Đây là cầu nối giữa luật game, UI flow và backend behavior.

## 2. Trạng thái phòng

`waiting`
- Phòng đã được tạo, chưa bắt đầu trận.
- Người chơi có thể tham gia, rời phòng, chuyển trạng thái `ready`.

`starting`
- Server đang khóa room membership, khởi tạo deck và chia bài.
- Không nhận người chơi mới và không cho phép đổi `ready`.

`in_game`
- Trận đang diễn ra.
- Chỉ nhận game actions hợp lệ theo lượt.

`finished`
- Trận đã kết thúc.
- Cho phép rematch hoặc rời phòng.

## 3. Feature: Tạo phòng

### Mục tiêu

Cho phép một người chơi tạo room mới để mời người khác vào chơi.

### Preconditions

- Người dùng đang ở trang chủ hoặc trang tạo phòng.
- Chưa ở trong một room khác đang active.

### Luồng chính

- Client gửi yêu cầu tạo phòng.
- Server sinh `roomId`, `roomCode`, tạo player đầu tiên làm host.
- Room được tạo ở trạng thái `waiting`.
- Server trả về thông tin room và player session.

### Business rules

- Một room chỉ có 1 host.
- Room mới tạo chưa có game state trận đấu.
- Host mặc định là `not_ready` cho tới khi tự nhấn ready.

### Edge cases

- Người chơi gửi nhiều yêu cầu tạo phòng liên tiếp.
- Kết nối mất ngay sau khi room tạo xong.

### Lỗi trả về

- `ALREADY_IN_ACTIVE_ROOM`
- `RATE_LIMITED`
- `INTERNAL_ERROR`

## 4. Feature: Tham gia phòng

### Mục tiêu

Cho phép người chơi tham gia vào room bằng mã.

### Preconditions

- Room tồn tại.
- Room đang ở trạng thái `waiting`.
- Room chưa đủ số lượng tối đa 5 người.

### Luồng chính

- Client nhập `roomCode` và nickname.
- Server kiểm tra room.
- Server thêm player mới vào room với trạng thái `not_ready`.
- Server broadcast danh sách người chơi mới cho cả phòng.

### Business rules

- Nickname phải duy nhất trong room.
- Room chỉ nhận người chơi mới khi ở `waiting`.
- Số người tối thiểu để bắt đầu là 3.

### Edge cases

- Room code sai.
- Room vừa chuyển sang `starting` khi người chơi bấm join.
- Người chơi reconnect bằng session cũ thay vì join mới.

### Lỗi trả về

- `ROOM_NOT_FOUND`
- `ROOM_FULL`
- `ROOM_NOT_JOINABLE`
- `DUPLICATE_NICKNAME`
- `SESSION_CONFLICT`

## 5. Feature: Ready / Unready

### Mục tiêu

Cho phép người chơi xác nhận đã sẵn sàng trước khi bắt đầu.

### Preconditions

- Player đang trong room trạng thái `waiting`.

### Luồng chính

- Client gửi thay đổi `ready` hoặc `unready`.
- Server cập nhật trạng thái player.
- Server broadcast room state mới.

### Business rules

- Tất cả người chơi trong room phải `ready` mới được start.
- Host cũng phải `ready`.
- Không thể đổi `ready` sau khi room đã sang `starting`.

### Edge cases

- Hai thao tác toggle liên tiếp từ cùng một client.
- Host mất kết nối khi tất cả vừa `ready`.

### Lỗi trả về

- `ROOM_NOT_WAITING`
- `PLAYER_NOT_IN_ROOM`
- `INVALID_STATE_TRANSITION`

## 6. Feature: Start game

### Mục tiêu

Khởi tạo ván mới từ lobby.

### Preconditions

- Room ở trạng thái `waiting`.
- Có từ 3 đến 5 người chơi.
- Tất cả người chơi đều `ready`.

### Luồng chính

- Host gửi `game:start` hoặc server tự động start khi đủ điều kiện, tùy implementation đã chọn.
- Server chuyển room sang `starting`.
- Server sinh deck, chia bài, trộn `Exploding Kitten` vào draw pile.
- Server tạo game state authoritative.
- Server gửi private state cho từng người chơi và public state cho cả phòng.
- Room chuyển sang `in_game`.

### Business rules

- Không có người chơi mới được join sau khi bắt đầu.
- Mọi action lobby bị khóa trong `starting`.
- Deck setup phải quyết định hoàn toàn trên server.

### Edge cases

- Host gửi `start` nhiều lần.
- Một người mất kết nối đúng lúc game khởi tạo.

### Lỗi trả về

- `NOT_HOST`
- `NOT_ENOUGH_PLAYERS`
- `PLAYERS_NOT_READY`
- `ROOM_NOT_WAITING`
- `GAME_ALREADY_STARTED`

## 7. Feature: Chơi lá bài

### Mục tiêu

Cho phép người chơi hiện tại dùng action cards hợp lệ trong lượt của mình.

### Preconditions

- Room ở trạng thái `in_game`.
- Player đang ở trạng thái `active`.
- Đúng lượt của player.
- Lá bài tồn tại trong tay.

### Luồng chính

- Client gửi `turn:play-card` với `cardId` và payload phụ nếu cần.
- Server validate quyền hành động.
- Server resolve hiệu ứng theo luật engine.
- Server cập nhật discard pile, hand counts, pending effects và turn state.
- Server broadcast public result; gửi private payload nếu action tạo hidden info.

### Business rules

- Người chơi có thể chơi nhiều action cards trước bước rút.
- `Exploding Kitten` và `Defuse` không được tự chơi từ tay trong flow bình thường.
- `Favor` yêu cầu target còn sống và không phải chính mình.
- Sau khi chơi `Attack`, lượt hiện tại kết thúc ngay.

### Edge cases

- Client gửi play card khi không phải lượt.
- Client gửi `Favor` vào target đã bị loại.
- Double-submit cùng `cardId`.

### Lỗi trả về

- `NOT_YOUR_TURN`
- `CARD_NOT_IN_HAND`
- `CARD_NOT_PLAYABLE`
- `INVALID_TARGET`
- `ACTION_LOCKED`

## 8. Feature: Rút bài

### Mục tiêu

Cho phép người chơi kết thúc lượt bằng bước rút bài, hoặc thực hiện lượt rút bắt buộc khi bị `Attack`.

### Preconditions

- Room ở trạng thái `in_game`.
- Đúng lượt player.
- Không có pending resolution khác đang khóa action.

### Luồng chính

- Client gửi `turn:draw-card`.
- Server lấy lá trên cùng từ draw pile.
- Nếu không phải `Exploding Kitten`, thêm lá vào tay, giảm `pendingDraws`, xử lý kết thúc hoặc tiếp tục lượt theo luật.
- Nếu là `Exploding Kitten`, chuyển sang flow xử lý nổ.

### Business rules

- Mặc định mỗi lượt có 1 lượt rút bắt buộc.
- `Attack` tăng số lượt rút bắt buộc của người kế tiếp.
- Lượt chỉ kết thúc khi `pendingDraws` về 0 hoặc khi player bị loại.

### Edge cases

- Player gửi draw nhiều lần liên tiếp.
- Draw pile ít lá.

### Lỗi trả về

- `NOT_YOUR_TURN`
- `DRAW_NOT_ALLOWED`
- `ACTION_LOCKED`
- `DECK_EMPTY_UNSUPPORTED`

## 9. Feature: Dùng Defuse

### Mục tiêu

Xử lý trường hợp player rút `Exploding Kitten` và còn `Defuse`.

### Preconditions

- Player vừa rút `Exploding Kitten`.
- Player có ít nhất 1 `Defuse`.

### Luồng chính

- Server tự động kiểm tra `Defuse`.
- Server loại 1 `Defuse` khỏi tay player và đưa vào discard.
- Server đặt lại `Exploding Kitten` vào draw pile theo logic server-defined.
- Server gửi state update cho cả phòng.

### Business rules

- MVP không yêu cầu người chơi tự chọn vị trí đặt lại bom.
- Không có window để từ chối dùng `Defuse`.
- Nếu không có `Defuse`, player bị loại ngay.

### Edge cases

- Player disconnect đúng lúc vừa nổ.
- Client cũ vẫn gửi action khác trong lúc server đang resolve defuse.

### Lỗi trả về

- Không có lỗi client-facing riêng, vì flow này do server tự động xử lý.

## 10. Feature: Loại người chơi

### Mục tiêu

Loại player khỏi trận khi không sống sót sau `Exploding Kitten`.

### Preconditions

- Player vừa rút `Exploding Kitten`.
- Player không có `Defuse`.

### Luồng chính

- Server chuyển player sang `eliminated`.
- Toàn bộ hand của player bị loại khỏi game và chuyển vào discard hoặc graveyard logic đã chốt.
- Server broadcast `player:eliminated`.
- Nếu còn hơn 1 người sống, turn chuyển tiếp theo luật.
- Nếu còn 1 người sống, game kết thúc.

### Business rules

- Người bị loại không được gửi thêm game action.
- Người bị loại vẫn nhận public updates và màn kết quả.
- Nếu player bị loại đang là người current turn, lượt chuyển ngay.

### Edge cases

- Hai người còn lại, một người nổ và game kết thúc ngay.
- Player bị loại disconnect trước khi nhận event.

### Lỗi trả về

- Không có lỗi client-facing riêng cho chính flow loại người chơi.

## 11. Feature: Reconnect

### Mục tiêu

Cho phép người chơi mất kết nối quay lại phòng/trận đang chạy với đúng session.

### Preconditions

- Người chơi có `playerSessionId` hợp lệ.
- Room vẫn tồn tại.

### Luồng chính

- Client gửi `player:reconnect` với session token.
- Server xác thực session.
- Server gắn socket mới vào player cũ.
- Server gửi lại private state của player và public room/game state hiện tại.

### Business rules

- Reconnect không tạo người chơi mới.
- Nếu player đã bị loại, reconnect vẫn thành công nhưng chỉ ở trạng thái spectator-like trong cùng trận.
- Session cũ bị vô hiệu hóa khi socket mới được gắn.

### Edge cases

- Hai client cùng reconnect bằng cùng một session.
- Room đã `finished` nhưng chưa giải tán.

### Lỗi trả về

- `SESSION_NOT_FOUND`
- `SESSION_EXPIRED`
- `ROOM_CLOSED`
- `SESSION_TAKEN_OVER`

## 12. Feature: Rematch

### Mục tiêu

Cho phép cùng nhóm người chơi bắt đầu ván mới sau khi ván cũ kết thúc.

### Preconditions

- Room ở trạng thái `finished`.
- Người chơi cũ vẫn còn trong room.

### Luồng chính

- Người chơi gửi tín hiệu rematch ready.
- Khi tất cả người chơi còn trong room đồng ý, room reset về `waiting` hoặc trực tiếp `starting` tùy implementation.
- Server xóa game state cũ, giữ membership room, reset readiness.

### Business rules

- Nickname và session được giữ nguyên.
- Player mới không được join vào giữa `finished` nếu room đang chờ rematch kín.
- Không carry state trận cũ sang trận mới, trừ player roster.

### Edge cases

- Một người rời room sau khi game kết thúc.
- Host không còn online lúc rematch được yêu cầu.

### Lỗi trả về

- `ROOM_NOT_FINISHED`
- `REMATCH_NOT_READY`
- `PLAYER_NOT_IN_ROOM`

## 13. Danh sách lỗi chuẩn

Các event lỗi nên trả về object thống nhất:

```json
{
  "code": "NOT_YOUR_TURN",
  "message": "It is not your turn.",
  "requestId": "optional-client-request-id"
}
```

Danh sách lỗi tối thiểu:

- `ALREADY_IN_ACTIVE_ROOM`
- `RATE_LIMITED`
- `ROOM_NOT_FOUND`
- `ROOM_FULL`
- `ROOM_NOT_JOINABLE`
- `DUPLICATE_NICKNAME`
- `SESSION_CONFLICT`
- `ROOM_NOT_WAITING`
- `PLAYER_NOT_IN_ROOM`
- `INVALID_STATE_TRANSITION`
- `NOT_HOST`
- `NOT_ENOUGH_PLAYERS`
- `PLAYERS_NOT_READY`
- `GAME_ALREADY_STARTED`
- `NOT_YOUR_TURN`
- `CARD_NOT_IN_HAND`
- `CARD_NOT_PLAYABLE`
- `INVALID_TARGET`
- `ACTION_LOCKED`
- `DRAW_NOT_ALLOWED`
- `DECK_EMPTY_UNSUPPORTED`
- `SESSION_NOT_FOUND`
- `SESSION_EXPIRED`
- `ROOM_CLOSED`
- `SESSION_TAKEN_OVER`
- `INTERNAL_ERROR`

## 14. Functional test scenarios

- Tạo room và join đủ 3 người thành công.
- Người chơi không thể join room đã bắt đầu.
- Tất cả ready và bắt đầu trận thành công.
- Người chơi hiện tại chơi `Skip`, `Attack`, `Shuffle`, `See the Future`, `Favor` đúng flow.
- `Favor` chỉ target vào người còn sống.
- Rút `Exploding Kitten` với `Defuse` sống sót.
- Rút `Exploding Kitten` không có `Defuse` bị loại.
- Người bị loại không được gửi thêm `turn:play-card` hoặc `turn:draw-card`.
- Reconnect giữa trận nhận lại đúng hand và đúng public state.
- Rematch reset đúng room và không giữ game state cũ.

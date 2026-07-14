# Game Design: Exploding Kittens Lite

## 1. Mục tiêu sản phẩm

Xây dựng một game bài multiplayer trên web, chơi online theo phòng riêng, có nhịp độ nhanh, dễ hiểu trong 2-3 phút và hoàn thành trong 10-15 phút mỗi ván. Trải nghiệm cần đủ vui để chơi với nhóm bạn, nhưng phạm vi MVP phải đủ gọn để hoàn thành nhanh và triển khai ổn định.

## 2. Vision

Game là một bản `Exploding Kittens inspired` rút gọn:

- 3-5 người chơi trong cùng một phòng.
- Mỗi lượt người chơi có thể chơi nhiều lá hành động trước khi kết thúc bằng việc rút bài.
- Người rút trúng `Exploding Kitten` mà không có `Defuse` sẽ bị loại.
- Người sống cuối cùng là người chiến thắng.

## 3. Trải nghiệm cốt lõi

Người chơi cần cảm nhận được ba thứ:

- Căng thẳng mỗi khi phải rút bài.
- Niềm vui phá nhau bằng các lá hành động đơn giản.
- Sự rõ ràng trong thông tin công khai, để dù có yếu tố bất ngờ thì người chơi vẫn hiểu chuyện gì vừa xảy ra.

Game không hướng tới chiều sâu chiến thuật nặng. Trọng tâm là party game online có tính tương tác, dễ xem, dễ thử lại nhiều ván.

## 4. Đối tượng người chơi

- Nhóm bạn muốn chơi online nhanh trong 10-15 phút.
- Người dùng quen các game bài phổ thông, không cần học luật dài.
- Người chơi mobile/web casual, không muốn điều khiển phức tạp.

## 5. Phạm vi MVP

### Bao gồm

- Tạo phòng và tham gia phòng bằng mã.
- 3-5 người chơi.
- Lobby với trạng thái `ready`.
- Một ván đầy đủ từ chia bài đến kết thúc.
- Realtime đồng bộ lượt chơi, log hành động, loại người chơi, kết quả.
- Reconnect ở mức khôi phục lại trạng thái phiên đang diễn ra.

### Không bao gồm

- Matchmaking công khai.
- Xếp hạng, MMR, leaderboard.
- Bot.
- Chat voice/text nâng cao.
- Spectator mode.
- Lá `Nope`.
- Rule tùy biến theo phòng.

## 6. Bộ bài MVP

Các loại bài được hỗ trợ:

- `Exploding Kitten`
- `Defuse`
- `Skip`
- `Attack`
- `Shuffle`
- `See the Future`
- `Favor`

### Vai trò từng loại bài

`Exploding Kitten`
- Không thể tự chơi từ tay.
- Chỉ kích hoạt khi bị rút từ deck.
- Nếu không có `Defuse`, người chơi bị loại ngay.

`Defuse`
- Được dùng tự động khi người chơi rút trúng `Exploding Kitten` và có ít nhất 1 lá `Defuse`.
- Sau khi dùng, người chơi không bị loại và lá `Exploding Kitten` được đặt lại vào deck theo vị trí do server xử lý.

`Skip`
- Bỏ qua một lượt rút bắt buộc.
- Nếu người chơi đang nợ nhiều lượt rút do `Attack`, mỗi `Skip` giảm 1 lượt rút còn nợ.

`Attack`
- Kết thúc lượt hiện tại ngay lập tức, không cần rút bài.
- Chuyển áp lực sang người kế tiếp bằng cách cộng thêm lượt rút bắt buộc.

`Shuffle`
- Xáo lại toàn bộ draw pile.

`See the Future`
- Chỉ người chơi hiện tại được nhìn 3 lá đầu draw pile.
- Không thay đổi thứ tự deck.

`Favor`
- Chọn 1 người chơi còn sống khác.
- Người bị chọn phải đưa ngẫu nhiên 1 lá bài từ tay cho người chơi hiện tại.

## 7. Gameplay loop

### 7.1 Trước trận

- Người tạo phòng tạo room code.
- Người chơi khác tham gia bằng room code.
- Tất cả vào lobby và nhấn `ready`.
- Khi đủ điều kiện, host hoặc server khởi động ván.

### 7.2 Bắt đầu trận

- Server tạo deck theo cấu hình game.
- Chia bài khởi đầu cho từng người chơi.
- Mỗi người phải có ít nhất 1 `Defuse` khởi đầu.
- `Exploding Kitten` chỉ được trộn vào deck sau khi chia bài xong.

### 7.3 Một lượt chơi

- Người chơi hiện tại có thể chơi 0 hoặc nhiều action cards hợp lệ.
- Khi kết thúc chuỗi action, người chơi thực hiện bước rút bài, trừ khi một action vừa chơi đã kết thúc lượt khác đi.
- Nếu rút bình thường, lượt kết thúc và chuyển sang người tiếp theo.
- Nếu rút `Exploding Kitten`, game chuyển sang flow xử lý nổ.

### 7.4 Khi có nổ

- Nếu người chơi có `Defuse`, server tiêu thụ 1 lá `Defuse`.
- `Exploding Kitten` được đưa lại vào draw pile ở vị trí do server chọn.
- Nếu không có `Defuse`, người chơi bị loại và tay bài của họ bị bỏ.

### 7.5 Kết thúc ván

- Khi chỉ còn 1 người chơi còn sống, ván kết thúc.
- Hiển thị người thắng, trạng thái các người chơi còn lại và cho phép rematch.

## 8. Điều kiện thắng và thua

### Thắng

- Là người chơi cuối cùng còn trạng thái `active`.

### Thua

- Rút `Exploding Kitten` khi không còn `Defuse`.
- Người chơi bị loại không thể hành động thêm trong ván đó.

## 9. Thông tin ẩn và thông tin công khai

### Công khai với cả phòng

- Danh sách người chơi trong phòng.
- Trạng thái `ready`.
- Người đang tới lượt.
- Số lá trên tay của mỗi người chơi.
- Kết quả của các action công khai như `Skip`, `Attack`, `Shuffle`, `Favor`.
- Người chơi nào bị loại.
- Discard pile.

### Chỉ riêng từng người chơi được thấy

- Bài trên tay của mình.
- Kết quả `See the Future` do mình kích hoạt.
- Trạng thái reconnect private payload của mình.

### Không ai được thấy

- Thứ tự cụ thể của draw pile, trừ trường hợp `See the Future`.
- Tay bài chi tiết của người chơi khác.

## 10. UX goals

- Người mới có thể vào phòng và bắt đầu chơi mà không cần đọc tài liệu dài.
- Mỗi action đều để lại log ngắn, rõ lý do và kết quả.
- Giao diện phải luôn trả lời được ba câu hỏi:
  - Ai đang tới lượt?
  - Tôi có thể làm gì lúc này?
  - Chuyện gì vừa xảy ra?

## 11. Scope sau MVP

### Phase 2 hợp lý

- Thêm `Nope`.
- Rule tùy chỉnh theo phòng.
- Match history.
- Spectator mode.
- Public matchmaking.
- Cosmetic, emote, animation phong phú hơn.

### Điều chưa làm ở MVP để giảm rủi ro

- Combo hoặc stack effect phức tạp ngoài `Attack`.
- Card targeting nhiều nhánh.
- Deck manipulation do người chơi tự chọn vị trí khi `Defuse`.
- Hệ thống kinh tế, progression, inventory.

## 12. Success criteria cho MVP

- 3-5 người có thể tạo phòng, vào trận và chơi xong một ván đầy đủ.
- State không desync giữa người chơi.
- Người chơi bị loại, reconnect và end game đều xử lý nhất quán.
- Người thử game lần đầu có thể hiểu luật cơ bản sau một ván.

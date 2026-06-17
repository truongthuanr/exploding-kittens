# Exploding Kittens Lite Docs Index

Thư mục `plan/` chứa bộ tài liệu sản phẩm và kỹ thuật cho dự án game web multiplayer lấy cảm hứng từ Exploding Kittens. Bộ tài liệu này được viết ở mức đủ chi tiết để một kỹ sư khác có thể bắt đầu implement mà không phải tự quyết định lại luật game, feature flow hay kiến trúc nền tảng.

## Danh sách tài liệu

- [game-design.md](/plan/game-design.md): vision sản phẩm, trải nghiệm người chơi, phạm vi MVP, luật ở mức gameplay.
- [functional-spec.md](/plan/functional-spec.md): đặc tả tính năng theo hành vi người dùng và luồng hệ thống.
- [game-engine-spec.md](/plan/game-engine-spec.md): đặc tả state server-authoritative, luật resolve, validation và hidden information.
- [technical-design.md](/plan/technical-design.md): kiến trúc hệ thống, socket contract, reconnect strategy và định hướng scale.

## Nguyên tắc sử dụng

- `game-design.md` là nguồn chân lý cho trải nghiệm và phạm vi sản phẩm.
- `game-engine-spec.md` là nguồn chân lý cho luật game và state transition.
- `functional-spec.md` nối luật game với hành vi UI và room lifecycle.
- `technical-design.md` chốt contract kỹ thuật giữa frontend và backend.

Khi có thay đổi luật hoặc interface, cập nhật `game-engine-spec.md` trước, sau đó đồng bộ sang các tài liệu còn lại để tránh drift.

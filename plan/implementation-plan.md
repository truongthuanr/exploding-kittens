# Implementation Plan: Exploding Kittens Lite

## 1. Mục tiêu của tài liệu

Tài liệu này chuyển bộ docs hiện có thành một roadmap triển khai thực tế từ repo trống đến một bản MVP có thể chơi được. Mục tiêu không phải viết lại luật game hay technical design, mà là chốt thứ tự làm việc, các phụ thuộc giữa phase, deliverables bắt buộc và điều kiện tối thiểu để chuyển sang giai đoạn tiếp theo.

Người đọc chính là chính bạn, nên format ưu tiên:

- checklist thực thi
- phase rõ ràng
- dependency rõ ràng
- definition of done cụ thể

## 2. Source of truth

Implementation plan này không tự định nghĩa luật hay kiến trúc mới. Khi có mâu thuẫn, ưu tiên theo thứ tự sau:

1. [game-engine-spec.md](/plan/game-engine-spec.md) cho luật game, state transition, validation và hidden information.
2. [functional-spec.md](/plan/functional-spec.md) cho feature behavior, room lifecycle và user-facing flows.
3. [technical-design.md](/plan/technical-design.md) cho system architecture, infra, socket contract, reconnect và scale strategy.
4. [game-design.md](/plan/game-design.md) cho trải nghiệm sản phẩm, phạm vi MVP và định hướng mở rộng.

## 3. Nguyên tắc triển khai

- Triển khai theo thứ tự `backend-first`.
- Ưu tiên đạt `vertical slice playable` sớm, sau đó mới hardening.
- Backend luôn là nguồn chân lý duy nhất cho game state.
- Không để client tự resolve rule hoặc đoán hidden information.
- Live game state chỉ giữ trong memory ở MVP.
- Không thêm `Nope`, auth thật, ranking, bot, spectator hoặc `Redis` vào bản đầu.
- Mọi phase phải có output kiểm được, không kết thúc ở mức “gần xong”.

## 4. Thứ tự triển khai tổng thể

1. Foundation và shared contracts
2. Backend core: models, room/session services, game engine
3. Realtime gateway và playable backend
4. Frontend lobby/game board/result flow
5. Reconnect, rematch, persistence tối thiểu, deploy/hardening

Thứ tự này được chọn vì mọi phần phía trước là dependency thực của phần phía sau. Nếu làm ngược, nguy cơ sửa lại nhiều ở contract, state model và UI flow là rất cao.

## 5. Phase plan

### Phase 1: Foundation và shared contracts

**Mục tiêu**

Dựng bộ khung project và chốt contract dùng chung để backend và frontend có thể phát triển mà không drift từ đầu.

**Tasks chính**

- Tạo skeleton project:
  - `backend/` cho `FastAPI + python-socketio`
  - `frontend/` cho `Next.js + TypeScript`
- Thiết lập config tối thiểu:
  - backend port
  - frontend port
  - `DATABASE_URL`
  - `SESSION_SECRET`
  - `NEXT_PUBLIC_SOCKET_URL`
- Tạo shared enums/types từ docs:
  - `RoomStatus`
  - `GamePhase`
  - `CardType`
  - `PlayerStatus`
- Tạo request/response schemas cho các socket events chính.
- Chốt folder structure mức tối thiểu cho backend và frontend.

**Deliverables**

- Repo có thể cài dependencies và chạy riêng frontend/backend.
- Có schema models cho socket payloads.
- Có README hoặc note ngắn mô tả cách chạy local.

**Dependencies**

- Chỉ phụ thuộc vào bộ docs hiện có.

**Definition of done**

- Có thể start backend server và frontend dev server độc lập.
- Shared contract đã được tạo và không mâu thuẫn với `technical-design.md`.

### Phase 2: Backend core

**Mục tiêu**

Xây dựng phần domain logic cốt lõi trước khi đụng tới UI thật, để luật game được kiểm chứng ở mức service và unit test.

**Tasks chính**

- Implement models và registries cho:
  - room state
  - player session state
  - server game state
- Implement `room service`:
  - create room
  - join room
  - ready/unready
  - start game preconditions
- Implement `session service`:
  - tạo `playerSessionId`
  - bind/unbind socket
  - track disconnect
  - takeover logic
- Implement `game engine`:
  - deck builder
  - start game setup
  - turn lifecycle
  - `skip`, `attack`, `shuffle`, `see_the_future`, `favor`
  - draw flow
  - explosion flow
  - defuse flow
  - elimination
  - end game
- Tách rõ public state và private player state.
- Viết engine unit tests và service-level tests.

**Deliverables**

- Backend có thể start game và resolve actions bằng code, chưa cần UI.
- Test backend xác nhận engine hoạt động đúng với luật đã chốt.

**Dependencies**

- Hoàn thành Phase 1.

**Definition of done**

- Unit tests cho engine pass.
- Service tests cho room/session/game flow cơ bản pass.
- Không còn logic luật nằm ở TODO mơ hồ.

### Phase 3: Realtime playable backend

**Mục tiêu**

Nối backend core với realtime layer để có thể chơi full match qua socket events, kể cả khi chưa có frontend hoàn chỉnh.

**Tasks chính**

- Tạo `python-socketio` gateway và event handlers cho:
  - `room:create`
  - `room:join`
  - `room:ready`
  - `game:start`
  - `turn:play-card`
  - `turn:draw-card`
  - `player:reconnect`
- Chuẩn hóa `error` event:
  - `code`
  - `message`
  - `requestId`
- Implement broadcaster cho:
  - `room:updated`
  - `game:started`
  - `turn:started`
  - `game:state`
  - `player:private-state`
  - `player:eliminated`
  - `game:ended`
- Dùng `asyncio.Lock` theo `roomId` để serialize action resolution.
- Thêm duplicate guard nhẹ bằng `requestId` hoặc action lock.
- Viết socket integration tests.

**Deliverables**

- Có thể dùng socket client thô hoặc script test để tạo room, join room, start game và chơi hết ván.
- Không leak hidden information qua broadcast.

**Dependencies**

- Hoàn thành Phase 2.

**Definition of done**

- Socket integration tests cho action flow pass.
- Chơi full match được mà không cần frontend đẹp.
- Public/private payload split đã hoạt động đúng.

### Phase 4: Frontend MVP flow

**Mục tiêu**

Dựng UI đủ để nhiều người chơi ván hoàn chỉnh trên web, không cần polish sâu.

**Tasks chính**

- Tạo socket client layer:
  - connect
  - reconnect
  - subscribe event
  - persist `playerSessionId`
- Dựng 4 màn chính:
  - home/create-join room
  - lobby
  - game board
  - result/rematch
- Lobby support:
  - create room
  - join room
  - ready/unready
  - start game
- Game board support:
  - current turn
  - pending draws
  - discard summary
  - hand riêng của player
  - action buttons cho card playable
  - draw button
  - game log
  - eliminated state
- Result flow support:
  - winner display
  - rematch button/state

**Deliverables**

- Có thể dùng UI để tạo room, vào lobby, bắt đầu ván và chơi full match.

**Dependencies**

- Hoàn thành Phase 3.

**Definition of done**

- 3-5 người có thể join room qua UI và chơi xong một ván.
- UI chỉ render từ server state, không tự giải luật.

### Phase 5: Reconnect, rematch, persistence tối thiểu, deploy/hardening

**Mục tiêu**

Biến vertical slice thành MVP ổn định hơn, dùng được trong staging/demo thật.

**Tasks chính**

- Hoàn thiện reconnect flow:
  - frontend lưu `playerSessionId`
  - reload tab -> reconnect đúng session
  - backend restore đúng room/game/private state
- Implement rematch flow sau `game:ended`.
- Persist tối thiểu:
  - match result
  - room metadata nếu cần audit
- Thêm health endpoint và startup config.
- Bổ sung env docs và deploy notes:
  - frontend trên `Vercel`
  - backend một instance Python
  - `PostgreSQL` managed
- Chạy manual multi-client scenarios.
- Fix race conditions và polish game log nếu cần.

**Deliverables**

- MVP có thể demo/staging:
  - reconnect được
  - rematch được
  - có match result tối thiểu
  - deploy được

**Dependencies**

- Hoàn thành Phase 4.

**Definition of done**

- Reload tab giữa trận không mất ghế.
- Rematch hoạt động sau trận kết thúc.
- Có thể deploy một bản staging chạy được end-to-end.

## 6. Workstream breakdown

### Backend foundation

**Module cần tạo**

- config/env loader
- app bootstrap
- schema models
- basic error model

**Outputs tối thiểu**

- backend server chạy được
- typed payload validation

**Rủi ro chính**

- drift giữa docs và transport models

**Ưu tiên**

1. config
2. schemas
3. bootstrap

### Game engine

**Module cần tạo**

- card/deck logic
- turn resolver
- action validators
- state serializers

**Outputs tối thiểu**

- có thể resolve full match bằng service calls

**Rủi ro chính**

- sai logic `attack` / `skip`
- leak hidden information

**Ưu tiên**

1. start game setup
2. draw flow
3. action cards
4. elimination/end game

### Room / session management

**Module cần tạo**

- room registry
- player session registry
- room lifecycle service
- reconnect binding logic

**Outputs tối thiểu**

- create/join/ready/start flow
- reconnect lookup đúng session

**Rủi ro chính**

- session takeover sai
- room state transition không chặt

**Ưu tiên**

1. room lifecycle
2. session creation
3. disconnect/reconnect

### Realtime / socket events

**Module cần tạo**

- socket gateway
- event handlers
- broadcaster
- duplicate guard

**Outputs tối thiểu**

- chơi full match qua events

**Rủi ro chính**

- race conditions
- inconsistent public/private payload

**Ưu tiên**

1. room events
2. game events
3. reconnect event
4. error event standardization

### Frontend screens and state

**Module cần tạo**

- socket client layer
- room/lobby state
- game board state
- result/rematch state

**Outputs tối thiểu**

- UI cho full match

**Rủi ro chính**

- render stale state
- UI enable sai action

**Ưu tiên**

1. home + join room
2. lobby
3. game board
4. result/rematch

### Persistence / reconnect

**Module cần tạo**

- match result persistence
- session restore flow
- health endpoint

**Outputs tối thiểu**

- reload tab không mất phiên
- có record kết quả trận

**Rủi ro chính**

- restore sai hand/private state

**Ưu tiên**

1. reconnect restore
2. match result
3. deploy config

### Testing

**Module cần tạo**

- engine unit tests
- service tests
- socket integration tests
- manual scenario checklist

**Outputs tối thiểu**

- có gates trước khi qua phase

**Rủi ro chính**

- chỉ test happy path

**Ưu tiên**

1. engine tests
2. room/session tests
3. socket tests
4. manual multi-client tests

### Deploy / config

**Module cần tạo**

- env docs
- health endpoint
- deployment notes

**Outputs tối thiểu**

- staging deploy được

**Rủi ro chính**

- config thiếu biến môi trường

**Ưu tiên**

1. env docs
2. health checks
3. staging notes

## 7. Deliverables và acceptance criteria

### Milestone A: Backend core ổn định

**Cần đạt**

- start game được
- resolve rules được qua tests
- room/session flow cơ bản hoạt động

**Acceptance criteria**

- backend tests pass cho game engine và room lifecycle

### Milestone B: Realtime backend playable

**Cần đạt**

- có thể chơi full match qua socket events
- hidden information không bị leak

**Acceptance criteria**

- socket integration tests pass
- có thể dùng client thô để chơi hết ván

### Milestone C: Frontend MVP playable

**Cần đạt**

- 3-5 người join room qua UI
- chơi full match qua browser

**Acceptance criteria**

- manual run nhiều client thành công

### Milestone D: MVP hardening

**Cần đạt**

- reconnect được
- rematch được
- `game:ended` ổn định
- deploy staging được

**Acceptance criteria**

- manual scenarios chính pass
- staging có thể demo end-to-end

## 8. Test gates

- Engine unit tests phải pass trước khi nối socket layer.
- Service tests cho room/session phải pass trước khi làm playable backend.
- Socket integration tests phải pass trước khi làm UI polish.
- Manual multi-client scenarios phải pass trước khi coi là MVP hoàn chỉnh.

## 9. Rủi ro chính và cách giảm rủi ro

### State desync

**Mitigation**

- backend authoritative
- UI chỉ render từ server state

### Race conditions do duplicate actions

**Mitigation**

- `asyncio.Lock` theo room
- `requestId` và duplicate guard

### Reconnect sai session

**Mitigation**

- `playerSessionId` riêng
- session takeover rõ ràng
- restore public và private state tách biệt

### Hidden information leak

**Mitigation**

- split `publicGameState` và `player:private-state`
- test riêng cho `See the Future` và `Favor`

### Logic `attack` / `skip` sai

**Mitigation**

- unit tests cho `pendingDraws`
- validate theo đúng `game-engine-spec.md`

## 10. Mốc hoàn thành tối thiểu để bắt đầu code thật

Có thể bắt đầu code ngay khi:

- folder structure được tạo
- enums và payload schemas được chốt
- engine state model được map sang code

Điều đó có nghĩa là Phase 1 nên được hoàn thành trọn vẹn trước khi tách nhánh sang backend core hoặc frontend UI.

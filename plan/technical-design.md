# Technical Design: Exploding Kittens Lite

## 1. Mục tiêu kỹ thuật

Thiết kế một hệ thống đủ đơn giản để hoàn thành MVP nhanh, nhưng vẫn có đường nâng cấp rõ ràng khi số lượng room, người chơi đồng thời hoặc số instance backend tăng lên.

Tài liệu này đóng vai trò `system design doc` cho dự án. Bên trong đó, phần `System Architecture` mô tả cấu trúc high-level; các phần còn lại mô tả realtime flow, state ownership, reconnect, persistence và scale strategy.

## 2. Stack mục tiêu

### Frontend

- `Next.js`
- `React`
- `TypeScript`
- `Tailwind CSS`

### Backend

- `Python 3.12+`
- `FastAPI`
- `python-socketio`
- `asyncio`
- `Pydantic`
- `SQLAlchemy`

### Data

- `PostgreSQL` cho dữ liệu bền vững
- In-memory state trên backend cho MVP

### Phase sau

- `Redis` cho pub/sub, session coordination và room state distribution khi scale multi-instance

## 3. System Architecture

### Architecture overview

Hệ thống được chia thành 4 khối chính:

- `Web Client`: UI game, lobby, room join, action panel, reconnect logic.
- `Realtime Backend`: xử lý room lifecycle, game engine, validation, broadcast state.
- `Persistent Storage`: lưu user metadata, room history, match history.
- `Future Cache Layer`: Redis cho session registry, room registry và cross-instance messaging khi scale.

### High-level flow

1. Người chơi mở web client và tạo/join room.
2. Frontend kết nối tới backend qua `Socket.IO`.
3. Backend tạo hoặc restore session, đưa player vào room.
4. Khi game bắt đầu, backend giữ toàn bộ game state authoritative.
5. Client chỉ gửi user intent như `play_card`, `draw_card`, `ready`.
6. Backend validate, resolve luật game, rồi broadcast state đã lọc cho từng người chơi.

### Trách nhiệm từng lớp

`Frontend`
- Render room, lobby, game board, result screen.
- Quản lý local UI state và socket lifecycle.
- Hiển thị public state và private hand của chính người chơi.
- Không tự resolve luật game.

`Backend`
- Quản lý room lifecycle.
- Quản lý player sessions và reconnect.
- Giữ game state authoritative.
- Validate actions, resolve rules, emit public/private payload.

`Database`
- Lưu dữ liệu bền vững cần giữ sau khi process restart.
- Không phải nguồn chân lý cho live game state của MVP.

## 4. Infrastructure / Deployment

### MVP deployment

- `Frontend`: deploy trên `Vercel`.
- `Backend`: 1 service Python duy nhất chạy `FastAPI + python-socketio`.
- `Database`: `PostgreSQL` managed service.
- `TLS / reverse proxy`: để platform hosting quản lý.

### MVP infra principles

- Ưu tiên một backend instance để tránh phức tạp với room ownership và sticky sessions.
- Live game state giữ trong RAM của backend.
- PostgreSQL chỉ lưu metadata và match results, không lưu mọi state transition trong trận.

### Khi nào cần nâng cấp infra

Thêm lớp scale khi bắt đầu có một trong các dấu hiệu sau:

- nhiều room chạy đồng thời
- backend cần nhiều replicas
- cần survive process restart tốt hơn
- cần cross-instance broadcasting

### Production-lite sau MVP

- Frontend vẫn giữ trên `Vercel`
- Backend tăng lên nhiều replicas
- Thêm `Redis`
- PostgreSQL tiếp tục giữ persistence

## 5. System Components

### Web client

- Join room bằng `roomCode`
- Lưu `playerSessionId` ở browser storage
- Tự reconnect socket khi mất kết nối
- Render private hand và public table state

### Realtime gateway

- Nhận và phát sự kiện qua `python-socketio`
- Ánh xạ socket vào `playerSessionId`
- Route event tới `room service` và `game engine`

### Room service

- Tạo room
- Join/leave room
- Ready/unready
- Room status transitions
- Host ownership

### Game engine service

- Setup deck
- Chia bài
- Resolve turn actions
- Resolve explosion/defuse
- End game

### Session service

- Sinh `playerSessionId`
- Xác minh reconnect
- Gắn socket mới vào player cũ
- Thu hồi session cũ khi takeover

### Persistence layer

- Ghi room metadata
- Ghi match result
- Hỗ trợ future analytics nếu cần

## 6. Authoritative State Model

Backend lưu ba lớp state chính:

### Room state

```python
class RoomState(TypedDict):
    room_id: str
    room_code: str
    status: Literal["waiting", "starting", "in_game", "finished"]
    host_player_id: str
    player_ids: list[str]
    created_at: str
```

### Game state

Dùng `ServerGameState` như đã chốt trong [game-engine-spec.md](/home/thuantruong/03_Boardgame/plan/game-engine-spec.md).

### Player session state

```python
class PlayerSession(TypedDict):
    player_session_id: str
    player_id: str
    room_id: str
    socket_id: str | None
    connected: bool
    last_seen_at: str
```

### Ownership rule

- Server giữ toàn bộ `drawPile`, `discardPile`, hand của tất cả người chơi và turn state.
- Client chỉ giữ UI state và hand của chính mình.
- Database không phải source of truth cho live state ở MVP.

## 7. Realtime Communication Design

### Broadcast strategy

Server không broadcast cùng một payload cho mọi người chơi trong các case có hidden information.

`Public payload`
- player list
- player statuses
- hand counts
- current turn
- pending draws
- discard summary
- log events
- winner

`Private payload`
- own hand
- `See the Future` result
- reconnect bootstrap payload

### Recommended emit pattern

- Sau mỗi action, backend build:
  - `publicGameState`
  - `privateStateByPlayerId`
- Broadcast `publicGameState` cho room
- Emit riêng `privateState` cho từng player khi cần

### Socket event contract

Mặc dù backend dùng Python, event names và payload contract vẫn giữ ổn định cho frontend TypeScript. Backend nên map payload vào `Pydantic models` để validate trước khi đi vào game engine.

## Client -> server events

### `room:create`

```ts
type RoomCreateRequest = {
  nickname: string;
};
```

### `room:join`

```ts
type RoomJoinRequest = {
  roomCode: string;
  nickname: string;
};
```

### `room:ready`

```ts
type RoomReadyRequest = {
  isReady: boolean;
};
```

### `game:start`

```ts
type GameStartRequest = {
  requestId?: string;
};
```

### `turn:play-card`

```ts
type PlayCardRequest = {
  requestId?: string;
  cardId: string;
  targetPlayerId?: string;
};
```

### `turn:draw-card`

```ts
type DrawCardRequest = {
  requestId?: string;
};
```

### `turn:defuse`

Event này tồn tại trong contract để rõ nghĩa, nhưng ở MVP server không yêu cầu client chủ động gửi. Nếu client có gửi thì server nên từ chối hoặc bỏ qua.

```ts
type DefuseRequest = {
  requestId?: string;
};
```

### `player:reconnect`

```ts
type ReconnectRequest = {
  playerSessionId: string;
};
```

## Server -> client events

### `room:updated`

```ts
type RoomUpdatedEvent = {
  roomId: string;
  roomCode: string;
  status: RoomStatus;
  players: Array<{
    playerId: string;
    nickname: string;
    isReady: boolean;
    isHost: boolean;
    status: PlayerStatus;
  }>;
};
```

### `game:started`

```ts
type GameStartedEvent = {
  roomId: string;
  currentPlayerId: string;
  turnNumber: number;
};
```

### `turn:started`

```ts
type TurnStartedEvent = {
  currentPlayerId: string;
  pendingDraws: number;
  turnNumber: number;
};
```

### `game:state`

```ts
type PublicGameStateEvent = {
  roomId: string;
  phase: GamePhase;
  currentPlayerId: string;
  pendingDraws: number;
  turnNumber: number;
  players: Array<{
    playerId: string;
    nickname: string;
    handCount: number;
    status: PlayerStatus;
  }>;
  discardTopCardType: CardType | null;
  discardCount: number;
  winnerPlayerId: string | null;
  recentAction: {
    actorPlayerId: string;
    actionType: string;
    targetPlayerId?: string;
    summary: string;
  } | null;
};
```

### `player:private-state`

```ts
type PlayerPrivateStateEvent = {
  playerId: string;
  hand: Array<{
    cardId: string;
    cardType: CardType;
  }>;
  visibleFutureCards: CardType[] | null;
};
```

### `player:eliminated`

```ts
type PlayerEliminatedEvent = {
  playerId: string;
  eliminatedBy: "exploding_kitten";
};
```

### `game:ended`

```ts
type GameEndedEvent = {
  winnerPlayerId: string;
};
```

### `error`

```ts
type ErrorEvent = {
  code: string;
  message: string;
  requestId?: string;
};
```

## 8. Reconnect Strategy

### Mục tiêu

- Player reload tab hoặc mất socket tạm thời không bị mất ghế.
- Reconnect phải khôi phục đúng tay bài riêng của người đó.

### Flow

- Khi tạo/join room, server cấp `playerSessionId`.
- Client lưu `playerSessionId` trong browser storage.
- Khi socket reconnect hoặc app reload, client gửi `player:reconnect`.
- Server verify token và cập nhật `socketId`.
- Server gửi:
  - `room:updated`
  - `game:state`
  - `player:private-state`

### Session takeover

- Chỉ một socket active cho một `playerSessionId`.
- Nếu socket mới reconnect với cùng session, socket cũ bị vô hiệu hóa.

## 9. Concurrency, Validation, and Anti-Cheat

### Action lock

- Trong khi resolve một action, set `actionLock = true`.
- Reject mọi action khác cho tới khi resolution hoàn tất.
- MVP chọn `reject`, không queue action.

### Idempotency

- Client được khuyến nghị gửi `requestId`.
- Backend có thể lưu recent request ids ngắn hạn theo player để tránh double-submit.

### Disconnect giữa action

- Nếu disconnect xảy ra sau khi action đã tới server, server vẫn resolve xong rồi mới đánh dấu player disconnected.

### Anti-cheat guards

- Không tin payload client về card type hay deck order.
- Chỉ nhận `cardId`; mọi thuộc tính lá bài phải lookup từ server state.
- Validate turn ownership cho mọi action.
- Không gửi hidden data cho sai player.

### Python-specific synchronization

- Chạy game loop theo `asyncio`; mọi socket handler phải là `async def`.
- Không dùng global mutable state không có guard.
- Dùng `asyncio.Lock` theo `roomId` để serialize action resolution trong từng phòng.

## 10. Persistence Strategy

### MVP

- Room state, game state, session state giữ trong memory process.
- Match result cuối ván có thể ghi vào database sau khi `game:ended`.

### Hạn chế chấp nhận ở MVP

- Nếu backend process restart, mọi trận đang chạy bị mất.
- Đây là trade-off chấp nhận được để giữ hệ thống đơn giản ở bản đầu.

## 11. Scaling Strategy

Khi có nhiều room hoặc cần nhiều backend instances:

- Chuyển room registry và session registry sang `Redis`.
- Dùng `python-socketio` với Redis manager để broadcast xuyên instance.
- Nếu cần survive process restart tốt hơn, serialize `ServerGameState` vào Redis theo `roomId`.
- Tách ghi match history thành async background job.

Không cần broker riêng ở MVP. `Redis` là bước scale đầu tiên hợp lý hơn `RabbitMQ` hoặc `Kafka` cho hệ thống này.

## 12. Folder Responsibility

### Frontend

- `app/` hoặc `pages/`: route cho home, room, game
- `components/`: lobby, player list, hand cards, action panel, game log
- `lib/socket/`: socket client, reconnect logic
- `state/`: UI state và event handlers

### Backend

- `app/api/`: FastAPI app bootstrap, health endpoints, dependency wiring
- `app/socket/`: `python-socketio` server, event handlers, room broadcast helpers
- `app/rooms/`: room service và room models
- `app/game/`: game engine, card effects, validators
- `app/sessions/`: reconnect/session management
- `app/schemas/`: Pydantic request/response models
- `app/db/`: SQLAlchemy models, session factory, repositories

## 13. Technical Test Plan

- Tạo/join room và broadcast lobby state đúng.
- Chỉ host được `game:start`.
- Chỉ current player được `turn:play-card` và `turn:draw-card`.
- `game:state` không làm lộ hand của player khác.
- `player:private-state` chỉ về đúng socket/session.
- Reconnect khôi phục đúng state sau reload.
- Hai client dùng cùng session chỉ còn một socket active.
- Spam action liên tiếp không làm state race hoặc double-resolve.
- Kết thúc game phát `game:ended` nhất quán cho cả phòng.

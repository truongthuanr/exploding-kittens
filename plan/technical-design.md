# Technical Design: Exploding Kittens Lite

## 1. Mục tiêu kỹ thuật

Thiết kế một kiến trúc đủ đơn giản để hoàn thành MVP nhanh, nhưng không khóa đường scale nếu game có nhiều room hoặc nhiều instance backend về sau.

## 2. Stack mục tiêu

### Frontend

- `Next.js`
- `React`
- `TypeScript`
- `Tailwind CSS`

### Backend

- `Node.js`
- `Socket.IO`
- `TypeScript`

### Data

- `PostgreSQL` cho dữ liệu bền vững
- In-memory state trên backend cho MVP

### Phase sau

- `Redis` cho pub/sub, session coordination và room state distribution nếu scale multi-instance

## 3. Kiến trúc tổng thể

### Frontend responsibility

- Trang home, create/join room, lobby, game board, result screen
- Quản lý local UI state và socket lifecycle
- Render public state và private hand của current player
- Gửi user intents lên server, không tự resolve luật

### Backend responsibility

- Room lifecycle
- Session management
- Game state authoritative
- Action validation
- Rule resolution
- Broadcasting filtered state
- Reconnect handling

### Database responsibility

`PostgreSQL` dùng cho:

- User profile tối thiểu nếu sau này có auth
- Room history / match history
- Analytics hoặc audit records nếu cần

MVP không bắt buộc persist toàn bộ live game state vào database.

## 4. System components

### Web client

- Join room bằng `roomCode`
- Lưu session token tạm thời ở browser storage
- Reconnect socket nếu mất kết nối

### Realtime gateway

- Nhận và phát sự kiện `Socket.IO`
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

## 5. Authoritative state model

Backend lưu hai lớp state:

### Room state

```ts
type RoomState = {
  roomId: string;
  roomCode: string;
  status: "waiting" | "starting" | "in_game" | "finished";
  hostPlayerId: string;
  playerIds: string[];
  createdAt: string;
};
```

### Game state

Dùng `ServerGameState` như đã chốt trong [game-engine-spec.md](/home/thuantruong/03_Boardgame/plan/game-engine-spec.md).

### Player session state

```ts
type PlayerSession = {
  playerSessionId: string;
  playerId: string;
  roomId: string;
  socketId: string | null;
  connected: boolean;
  lastSeenAt: string;
};
```

## 6. Broadcast strategy

Server không broadcast cùng một payload cho mọi người chơi trong các case có hidden information.

### Public room/game payload

Gửi cho cả phòng:

- player list
- player statuses
- hand counts
- current turn
- pending draws
- discard summary
- log events
- winner

### Private payload

Gửi riêng cho từng player:

- own hand
- `See the Future` result
- reconnect bootstrap payload

### Recommended pattern

- Sau mỗi action, backend build:
  - `publicGameState`
  - `privateStateByPlayerId`
- Broadcast `publicGameState` cho room
- Emit riêng `privateState` cho từng player khi cần

## 7. Socket event contract

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

## 8. Reconnect strategy

### Mục tiêu

- Player reload tab hoặc mất socket tạm thời không bị mất ghế.
- Reconnect phải khôi phục đúng tay bài riêng của người đó.

### Cách làm

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

## 9. Anti-cheat basic

MVP không cần anti-cheat nặng, nhưng phải có các guard bắt buộc:

- Không tin payload client về card type hay deck order.
- Chỉ nhận `cardId`, mọi thuộc tính lá bài được lookup từ server state.
- Validate turn ownership cho mọi action.
- Reject duplicate action bằng `requestId` hoặc action lock.
- Không gửi hidden data cho sai player.

## 10. Error handling và concurrency

### Action lock

- Trong khi resolve một action, set `actionLock = true`.
- Reject hoặc queue mọi action khác cho tới khi resolution hoàn tất.
- MVP nên chọn reject thay vì queue để đơn giản hóa hệ thống.

### Idempotency

- Client được khuyến nghị gửi `requestId`.
- Backend có thể lưu recent request ids ngắn hạn theo player để tránh double-submit.

### Disconnect giữa action

- Nếu disconnect xảy ra sau khi action đã tới server, server vẫn resolve xong rồi mới đánh dấu player disconnected.

## 11. Persistence strategy

### MVP

- Room state, game state, session state giữ trong memory process.
- Match result cuối ván có thể ghi vào database sau khi `game:ended`.

### Hạn chế chấp nhận ở MVP

- Nếu backend process restart, mọi trận đang chạy bị mất.
- Chấp nhận vì mục tiêu là build MVP nhanh.

## 12. Hướng scale lên Redis / multi-instance

Khi có nhiều room hoặc cần nhiều backend instances:

- Chuyển room registry và session registry sang `Redis`.
- Dùng `Socket.IO Redis adapter` để broadcast xuyên instance.
- Tách persistence match history thành async job.
- Nếu live game state cần survive process crash, serialize `ServerGameState` vào Redis theo room key.

Không cần broker riêng ở MVP. `Redis` là bước scale đầu tiên hợp lý hơn `RabbitMQ` hoặc `Kafka` cho hệ thống này.

## 13. Folder responsibility ở mức cao

### Frontend

- `app/` hoặc `pages/`: route cho home, room, game
- `components/`: lobby, player list, hand cards, action panel, game log
- `lib/socket/`: socket client, reconnect logic
- `state/`: UI state và event handlers

### Backend

- `src/rooms/`: room service và room models
- `src/game/`: game engine, card effects, validators
- `src/socket/`: event gateway
- `src/sessions/`: reconnect/session management
- `src/types/`: shared transport và state types

## 14. Technical test plan

- Tạo/join room và broadcast lobby state đúng.
- Chỉ host được `game:start`.
- Chỉ current player được `turn:play-card` và `turn:draw-card`.
- `game:state` không làm lộ hand của player khác.
- `player:private-state` chỉ về đúng socket/session.
- Reconnect khôi phục đúng state sau reload.
- Hai client dùng cùng session chỉ còn một socket active.
- Spam action liên tiếp không làm state race hoặc double-resolve.
- Kết thúc game phát `game:ended` nhất quán cho cả phòng.

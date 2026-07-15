## Goal
Expose the room flow over realtime events so clients can create, join, ready, and start matches.

## Scope
- Add handlers for `room:create`, `room:join`, `room:ready`, `game:start`
- Emit `room:updated` and `game:started`
- Map service errors to the standard `error` event
- `game:start` initializes and stores the initial runtime state so later gameplay
  socket issues can operate on an existing match.

## Implementation decisions
- `room:create` and `room:join` return ack payloads.
- `room:ready` returns no ack payload; clients observe success through
  `room:updated`.
- `game:start` returns no ack payload; clients observe success through
  `room:updated` and `game:started`.
- Error events include `requestId: null` when the request schema does not
  provide a request id.
- Duplicate `game:start` is guarded by checking `GameRegistry` and emits
  `game_already_started`.
- Unknown service/setup `ValueError` maps to `invalid_operation`.
- Room status changes from `STARTING` to `IN_GAME` only after game setup and
  runtime storage succeed.

## Implementation checklist

### Socket handler foundation
- [ ] Add shared socket error helper that emits the documented `error` shape:
  - `code`
  - `message`
  - `requestId`
- [ ] Add helper to resolve the bound player session from `sid`.
- [ ] Return `session_not_bound` error when a socket has no bound session.
- [ ] Keep request validation at the socket boundary before calling services.

### `room:create`
- [ ] Validate `RoomCreateRequest`.
- [ ] Call `RoomService.create_room(...)`.
- [ ] Create a player session for the host.
- [ ] Bind the session to the current socket id.
- [ ] Add the socket to the Socket.IO room matching `roomId`.
- [ ] Emit `room:updated` to the room.
- [ ] Return `RoomCreateResponse` as the event ack.
- [ ] Map room/session service errors to `error`.

### `room:join`
- [ ] Validate `RoomJoinRequest`.
- [ ] Call `RoomService.join_room(...)`.
- [ ] Create a player session for the joining player.
- [ ] Bind the session to the current socket id.
- [ ] Add the socket to the Socket.IO room matching `roomId`.
- [ ] Emit `room:updated` to the room.
- [ ] Return `RoomJoinResponse` as the event ack.
- [ ] Map room/session service errors to `error`.

### `room:ready`
- [ ] Validate `RoomReadyRequest`.
- [ ] Resolve the bound session from `sid`.
- [ ] Call `RoomService.set_ready(session.room_id, session.player_id, payload.isReady)`.
- [ ] Emit `room:updated` to the room.
- [ ] Map room/session service errors to `error`.

### `game:start`
- [ ] Validate `GameStartRequest`.
- [ ] Resolve the bound session from `sid`.
- [ ] Call `RoomService.transition_to_starting(session.room_id, session.player_id)`.
- [ ] Create initial game state with `GameSetupService.create_initial_game_state(room)`.
- [ ] Store `GameRuntimeState.from_setup_result(...)` in `GameRegistry`.
- [ ] Set room status to `IN_GAME` after setup succeeds.
- [ ] Emit `room:updated` to the room.
- [ ] Emit `game:started` with:
  - `roomId`
  - `currentPlayerId`
  - `turnNumber`
- [ ] If setup fails after room status becomes `STARTING`, roll room status back to `WAITING`.
- [ ] Map room/session/setup service errors to `error`.

### Error mapping
- [ ] Map `RoomNotFoundError` to `room_not_found`.
- [ ] Map `DuplicateNicknameError` to `duplicate_nickname`.
- [ ] Map `RoomNotJoinableError` to `room_not_joinable`.
- [ ] Map `RoomFullError` to `room_full`.
- [ ] Map `NotHostError` to `not_host`.
- [ ] Map `RoomNotWaitingError` to `room_not_waiting`.
- [ ] Map `PlayerNotInRoomError` to `player_not_in_room`.
- [ ] Map `NotEnoughPlayersError` to `not_enough_players`.
- [ ] Map `PlayersNotReadyError` to `players_not_ready`.
- [ ] Map `PlayersDisconnectedError` to `players_disconnected`.
- [ ] Map missing socket session to `session_not_bound`.
- [ ] Map duplicate `game:start` to `game_already_started`.
- [ ] Map setup `ValueError` to `invalid_operation`.

### Tests
- [ ] `room:create` returns `playerSessionId`, enters socket room, and emits `room:updated`.
- [ ] `room:join` returns `playerSessionId`, enters socket room, and emits `room:updated`.
- [ ] `room:join` duplicate nickname emits `error`.
- [ ] `room:ready` updates player readiness and emits `room:updated`.
- [ ] `room:ready` without a bound socket session emits `session_not_bound`.
- [ ] `game:start` by host with enough ready connected players stores runtime state.
- [ ] `game:start` emits `room:updated` and `game:started`.
- [ ] `game:start` by non-host emits `not_host`.
- [ ] `game:start` with unready players emits `players_not_ready`.
- [ ] Duplicate `game:start` emits `game_already_started`.
- [ ] `game:start` setup failure rolls room status back to `WAITING`.

## Out of scope
- `turn:play-card`
- `turn:draw-card`
- `game:state`
- `player:private-state`
- `turn:started`
- Private hand delivery
- Reconnect into an in-progress game
- Request idempotency / duplicate guard
- Per-room `asyncio.Lock`
- Redis or multi-instance Socket.IO scaling

## Done when
- Room lifecycle works through socket events
- Clients receive room updates through realtime events
- Errors use the documented event shape
- `game:start` creates and stores initial runtime state, then emits `game:started`
- Public/private game state and turn events remain deferred to later issues

## Source docs
- `plan/implementation-plan.md`
- `plan/functional-spec.md`
- `plan/technical-design.md`

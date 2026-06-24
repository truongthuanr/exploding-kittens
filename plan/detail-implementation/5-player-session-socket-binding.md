## Goal
Add session tracking so reconnect and socket ownership can be implemented cleanly.

## Scope
- Define player session state
- Generate `playerSessionId`
- Track socket binding/unbinding
- Support session takeover and disconnect metadata

## Done when
- Sessions can be created and looked up reliably
- Socket binding can be reassigned to a reconnecting client
- Session state is ready for reconnect flow and room service use

## Source docs
- `plan/implementation-plan.md`
- `plan/technical-design.md`

## Session boundary
- `session` module owns player session identity and socket binding state.
- A session represents which client currently owns a player connection for reconnect purposes.
- Session state answers:
  - which `playerSessionId` belongs to which `playerId`
  - which `roomId` that session belongs to
  - which `socketId` is currently bound
  - whether the session is currently connected
- Session state does not own room lifecycle or room membership rules.
- A session is not a Socket.IO room.
- Socket.IO rooms may be used later for broadcast, but session state remains the source of truth for reconnect and socket ownership.

## Implementation checklist
### 1. Backend model
- `backend/app/modules/session/models.py`
- `PlayerSession`: `player_session_id`, `player_id`, `room_id`, `socket_id`, `connected`, `last_seen_at`

### 2. Domain methods
- `bind_socket(socket_id)`
- `unbind_socket()`
- `mark_connected()`
- `mark_disconnected()`
- `touch_last_seen()`

### 3. Backend service
- `backend/app/modules/session/service.py`
- Use cases
  - `create_session(player_id, room_id)` returns `PlayerSession`
  - `bind_socket(player_session_id, socket_id)` is used when the session does not have an active socket binding
  - `unbind_socket(socket_id)` returns `PlayerSession | None`
  - `rebind_socket(player_session_id, socket_id)` is used for reconnect or takeover and may replace an old socket binding
  - `get_session(player_session_id)` returns `PlayerSession` or raises `SessionNotFoundError`
  - `get_session_by_socket(socket_id)` returns `PlayerSession | None`
- Depends on `models.py`, `registry.py`, and `errors.py`
- Session service only owns session state and socket ownership
- Session service does not update `RoomState` or `RoomPlayerState.status`
- If a socket is not bound to any session, `unbind_socket(...)` is a no-op and returns `None`
- `bind_socket(...)` should fail if the session already has an active socket binding
- `rebind_socket(...)` is the only service API that may replace an existing socket binding

### 4. Backend registry
- `backend/app/modules/session/registry.py`
- `sessions_by_id: dict[str, PlayerSession]`
- `session_id_by_socket: dict[str, str]`
- API
  - `add(session)`
  - `get_by_id(player_session_id)` returns `PlayerSession` or raises `SessionNotFoundError`
  - `get_by_socket(socket_id)` returns `PlayerSession | None`
  - `remove(player_session_id)`
  - `bind_socket(player_session_id, socket_id)`
  - `unbind_socket(socket_id)`
- Session lookup is required by `playerSessionId` and `socketId`
- Session lookup by `playerId` is not required in this issue

### 5. Realtime orchestration
- `backend/app/realtime/server.py`
- `room:create` and `room:join` create a session and return `playerSessionId`
- `disconnect` looks up session by `sid` and unbinds socket
- `player:reconnect` validates `playerSessionId` and rebinds socket to the same session
- Room-visible presence changes are handled by realtime/application orchestration after session update
- No direct room mutation from inside session module
- No event bus required in this issue

### 6. Backend errors
- `backend/app/modules/session/errors.py`
- `SessionNotFoundError`
- Keep the error surface minimal in this issue

### 7. Session rule
- `playerSessionId` is unique
- 1 active socket for each `playerSessionId`
- `last_seen_at` is initialized when the session is created
- disconnect unbinds socket but does not delete session
- reconnect reuses the same session
- binding a new socket to the same session invalidates the old socket binding
- takeover in this issue only updates session binding state and clears the old socket lookup
- the server does not need to actively disconnect the old socket connection yet
- `last_seen_at` is updated on bind, unbind, and rebind operations
- session state is transport/session ownership only, not room presence state

### 8. Tests
- session registry/service tests
- create session and store in registry
- lookup session by `playerSessionId`
- lookup session by `socketId`
- bind socket to session
- unbind socket without deleting session
- rebind same session to new socket
- clear old socket lookup after takeover
- realtime wiring tests
- `room:create` returns `playerSessionId`
- `room:join` returns `playerSessionId`

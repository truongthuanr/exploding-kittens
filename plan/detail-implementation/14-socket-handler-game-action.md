## Goal
Make the backend playable through realtime game events while preserving hidden information.

## Scope
- Add handlers for `turn:play-card`, `turn:draw-card`, `player:reconnect`
- Emit `turn:started`, `game:state`, `player:private-state`, `player:eliminated`, `game:ended`
- Split public and private payload generation
- Add action lock and light duplicate guard

## Done when
- A full match can be played through socket events
- Hidden information is not broadcast to the room
- Concurrent or duplicate actions do not corrupt state

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`
- `plan/technical-design.md`

## Implementation decision

- This issue wires the realtime socket layer to the game engine behavior that already exists:
  - draw card
  - play `skip`
  - play `attack`
  - automatic defuse / elimination / end game after drawing an exploding kitten
- `shuffle`, `see_the_future`, and `favor` are out of scope for this issue.
- Unsupported action cards are detected only after the server has confirmed that
  the requested `cardId` exists in the current player's private hand.
- If a player attempts to play one of the unsupported action cards through `turn:play-card`, emit:
  - `code = unsupported_card_action`
  - include the original `requestId`
  - do not mutate game state
  - do not mark the request as processed by the duplicate guard
- Do not expose intermediate `resolving_explosion` state to clients when automatic resolution can complete in the same socket action.
- `turn:play-card` and `turn:draw-card` do not return ack payloads; successful actions are reported through emitted events, and failures are reported through `error`.
- Per-room action locks stay in memory for the lifetime of the process; no lock cleanup is required in this issue.
- Duplicate request replay emits the current snapshot only to the requester, not to the whole room.
- If `player:reconnect` receives an unknown `playerSessionId`, emit `invalid_session` and do not bind the socket.
- The old socket for a replaced session is not force-disconnected in this issue.

## Implementation checklist

### 1. Wire turn service into realtime server

- [ ] Instantiate `TurnLifecycleService(registry=game_registry)` in `backend/app/realtime/server.py`.
- [ ] Import game engine errors from `app.modules.game.errors`.
- [ ] Add `GAME_ERROR_CODES` for known turn/game validation failures.
- [ ] Use this exact game error mapping:
  - [ ] `GameNotFoundError -> game_not_found`
  - [ ] `GameNotInProgressError -> game_not_in_progress`
  - [ ] `PlayerNotFoundError -> player_not_found`
  - [ ] `NotCurrentPlayerError -> not_current_player`
  - [ ] `PlayerEliminatedError -> player_eliminated`
  - [ ] `PlayerDisconnectedError -> player_disconnected`
  - [ ] `CardNotInHandError -> card_not_in_hand`
  - [ ] `InvalidCardTypeError -> invalid_card_type`
  - [ ] `InvalidTurnPhaseError -> invalid_turn_phase`
  - [ ] `TurnActionLockedError -> turn_action_locked`
  - [ ] `PendingResolutionError -> pending_resolution`
  - [ ] `NoPendingExplosionError -> no_pending_explosion`
  - [ ] `InvalidExplosionStateError -> invalid_explosion_state`
  - [ ] `InvalidPendingDrawsError -> invalid_pending_draws`
  - [ ] `EmptyDrawPileError -> empty_draw_pile`
- [ ] Extend service error handling so game errors become documented `error` events instead of bubbling out of handlers.
- [ ] Preserve `requestId` in emitted errors when the request model supports it.
- [ ] Add `invalid_session` handling for unknown `playerSessionId` during reconnect.
- [ ] Add `unsupported_card_action` handling for unsupported cards that exist in the player's hand.

### 2. Add public/private payload mappers

- [ ] Create `backend/app/realtime/game_events.py` for game payload mappers and broadcaster helpers.
- [ ] Keep socket handler orchestration in `backend/app/realtime/server.py`; do not put all mapper/broadcast logic in the handlers.
- [ ] Add a mapper from `GameRuntimeState` to `PublicGameStateEvent`.
- [ ] Public game state must include only:
  - [ ] `roomId`
  - [ ] `phase`
  - [ ] `currentPlayerId`
  - [ ] `pendingDraws`
  - [ ] `turnNumber`
  - [ ] `players[].playerId`
  - [ ] `players[].nickname`
  - [ ] `players[].handCount`
  - [ ] `players[].status`
  - [ ] `discardTopCardType`
  - [ ] `discardCount`
  - [ ] `winnerPlayerId`
  - [ ] `recentAction`
- [ ] Public game state must not include:
  - [ ] `draw_pile`
  - [ ] full `discard_pile`
  - [ ] any player's full hand
  - [ ] `player_private_states`
  - [ ] `pending_explosion_card`
- [ ] Add a mapper from `PlayerPrivateState` to `PlayerPrivateStateEvent`.
- [ ] Private state should include only the target player's:
  - [ ] `playerId`
  - [ ] `hand`
  - [ ] `visibleFutureCards`

### 3. Add broadcaster helpers

- [ ] Add `SessionRegistry.get_by_player(room_id, player_id)`.
- [ ] Add `SessionService.get_session_by_player(room_id, player_id)`.
- [ ] Implement `get_by_player(...)` with a simple scan of in-memory sessions for this MVP; do not add a second index in this issue.
- [ ] Use `SessionService.get_session_by_player(...)` from broadcaster helpers instead of reading registry internals directly.
- [ ] Add helper to broadcast `game:state` to the room.
- [ ] Add helper to emit `player:private-state` to one socket by `playerId`.
- [ ] Add helper to emit `player:private-state` for all connected players in a runtime.
- [ ] Skip private-state emits for players without an active `socket_id`.
- [ ] Add helper to emit `turn:started`.
- [ ] Add helper to emit `player:eliminated`.
- [ ] Add helper to emit `game:ended`.
- [ ] Add helper to sync room status to `finished` and emit `room:updated` when a game ends.
- [ ] Game-end sync must set `room_service.registry.get_by_id(room_id).status = RoomStatus.FINISHED`, not only `runtime.game_state.room_status`.
- [ ] Add helper to emit snapshot state to one requester:
  - [ ] `game:state` to the requester's `sid`
  - [ ] `player:private-state` to the requester's `sid`

### 4. Emit initial game state after `game:start`

- [ ] Keep existing `room:updated` emit.
- [ ] Keep existing `game:started` emit.
- [ ] Emit `game:state` after runtime state is stored.
- [ ] Emit `player:private-state` separately to each connected player.
- [ ] Emit `turn:started` for the first turn.
- [ ] Use `recentAction.actionType = start_game` for the first `game:state` snapshot.

### 5. Add per-room socket action lock

- [ ] Add an in-memory `asyncio.Lock` map keyed by `roomId`.
- [ ] Add `get_room_lock(room_id)` helper.
- [ ] Wrap `turn:play-card` resolution in the room lock.
- [ ] Wrap `turn:draw-card` resolution in the room lock.
- [ ] Do not use a single global lock across all rooms.
- [ ] Do not add lock cleanup in this issue.

### 6. Add light duplicate guard

- [ ] Add an in-memory processed request cache keyed by `(room_id, player_id, request_id)`.
- [ ] Use an `OrderedDict` or equivalent insertion-ordered structure for the processed request cache.
- [ ] Keep at most 500 processed request keys globally.
- [ ] When the cache exceeds 500 keys, remove the oldest key.
- [ ] Ignore duplicate handling when `requestId` is `None`.
- [ ] Mark a request as processed only after successful state resolution and after the main action events have been emitted.
- [ ] Do not mark a request as processed after:
  - [ ] payload validation failure
  - [ ] missing or invalid session
  - [ ] unsupported action card
  - [ ] engine validation error
  - [ ] any other error emit
- [ ] If a duplicate request arrives:
  - [ ] do not mutate game state
  - [ ] re-emit current `game:state` only to the requester's `sid`
  - [ ] re-emit the requester's `player:private-state` only to the requester's `sid`
  - [ ] do not broadcast anything to the room
  - [ ] do not emit an error

### 7. Implement `turn:draw-card`

- [ ] Validate payload with `DrawCardRequest`.
- [ ] Resolve the bound player session.
- [ ] Use the bound session's `room_id` and `player_id`; do not trust client identity.
- [ ] Run inside the per-room action lock.
- [ ] Call `turn_service.draw_card(...)`.
- [ ] If the result is `EXPLOSION_PENDING`, immediately call `turn_service.resolve_pending_explosion(...)` in the same lock.
- [ ] Emit only the final resolved state for automatic explosion handling; do not emit a public intermediate `resolving_explosion` snapshot.
- [ ] Emit `game:state` with a generated `recentAction`.
- [ ] Use these draw action mappings:
  - [ ] normal draw -> `recentAction.actionType = draw_card`
  - [ ] exploding kitten with defuse -> `recentAction.actionType = defuse`
  - [ ] exploding kitten with elimination -> `recentAction.actionType = eliminate`
- [ ] Emit private state updates to connected players.
- [ ] Emit `player:eliminated` if automatic explosion resolution eliminated the player.
- [ ] Emit `game:ended` and `room:updated` if the game finished.
- [ ] Emit `turn:started` when the current player or turn number changes.
- [ ] Mark a non-duplicate `requestId` as processed only after successful resolution and event emission.

### 8. Implement `turn:play-card`

- [ ] Validate payload with `PlayCardRequest`.
- [ ] Resolve the bound player session.
- [ ] Use the bound session's `room_id` and `player_id`; do not trust client identity.
- [ ] Run inside the per-room action lock.
- [ ] Lookup `cardId` in the current player's private hand on the server.
- [ ] If `cardId` is not in the player's hand, emit the mapped engine error (`card_not_in_hand`); do not emit `unsupported_card_action`.
- [ ] Dispatch by server-owned card type:
  - [ ] `skip` calls `turn_service.play_skip(...)`
  - [ ] `attack` calls `turn_service.play_attack(...)`
- [ ] For `shuffle`, `see_the_future`, and `favor`, emit `unsupported_card_action`.
- [ ] Do not mutate state for unsupported action cards.
- [ ] Do not mark unsupported action card requests as processed by the duplicate guard.
- [ ] Emit `game:state` with a generated `recentAction`.
- [ ] Use these play action mappings:
  - [ ] `skip` -> `recentAction.actionType = play_skip`
  - [ ] `attack` -> `recentAction.actionType = play_attack`
- [ ] Emit private state updates to connected players.
- [ ] Emit `game:ended` and `room:updated` if the game finished.
- [ ] Emit `turn:started` when the current player or turn number changes.
- [ ] Mark a non-duplicate `requestId` as processed only after successful resolution and event emission.

### 9. Generate recent action payloads

- [ ] Generate `RecentAction` in the socket/application layer, not in the domain engine.
- [ ] Use stable `ActionType` values:
  - [ ] `start_game`
  - [ ] `draw_card`
  - [ ] `play_skip`
  - [ ] `play_attack`
  - [ ] `defuse`
  - [ ] `eliminate`
  - [ ] `turn_advanced`
- [ ] Generate short backend summaries:
  - [ ] `<nickname> started the game`
  - [ ] `<nickname> drew a card`
  - [ ] `<nickname> played Skip`
  - [ ] `<nickname> played Attack`
  - [ ] `<nickname> defused an Exploding Kitten`
  - [ ] `<nickname> was eliminated`
- [ ] Do not include hidden card identity in public summaries.
- [ ] If elimination ends the game, keep `recentAction.actionType = eliminate` and also emit `game:ended`.
- [ ] Do not use `turn_advanced` as the primary recent action when an action-specific event already explains the transition.

### 10. Complete `player:reconnect`

- [ ] Keep existing session rebind behavior.
- [ ] If `playerSessionId` is unknown, emit `invalid_session` to the reconnecting socket and stop.
- [ ] Keep existing `room:updated` emit.
- [ ] If the room has a runtime state:
  - [ ] emit `game:state` to the reconnecting socket
  - [ ] emit `player:private-state` to the reconnecting socket
  - [ ] emit `turn:started` snapshot to the reconnecting socket only when `phase != finished`
- [ ] If the runtime is already finished, rely on `game:state.winnerPlayerId` and do not emit `turn:started`.
- [ ] Do not force-disconnect the old socket in this issue.

### 11. Add socket integration tests

- [ ] `game:start` emits initial `game:state`, per-player private state, and `turn:started`.
- [ ] Current player can draw through `turn:draw-card`.
- [ ] Current player can play `skip` through `turn:play-card`.
- [ ] Current player can play `attack` through `turn:play-card`.
- [ ] Non-current player draw/play emits an error and does not mutate state.
- [ ] Missing `cardId` emits `card_not_in_hand`, not `unsupported_card_action`.
- [ ] Unsupported action card emits `unsupported_card_action` and does not mutate state.
- [ ] Unsupported action card does not mark the `requestId` as processed.
- [ ] Public `game:state` does not include hidden hand or draw pile data.
- [ ] `player:private-state` is emitted only to the owning player's socket.
- [ ] Duplicate `requestId` does not resolve the same action twice.
- [ ] Duplicate `requestId` re-emits snapshot only to the requester and does not broadcast to the room.
- [ ] Drawing an exploding kitten with defuse auto-resolves and emits updated private/public state.
- [ ] Drawing an exploding kitten with defuse does not emit an intermediate public `resolving_explosion` snapshot.
- [ ] Drawing an exploding kitten without defuse emits `player:eliminated`.
- [ ] Ending the game emits `game:ended`, updates room status to `finished`, and emits `room:updated`.
- [ ] Reconnect during an active game restores `game:state` and the reconnecting player's private state.
- [ ] Reconnect with an unknown session emits `invalid_session`.
- [ ] Reconnect into a finished game does not emit `turn:started`.

### 12. Verification

- [ ] Ensure backend env file exists:

```bash
cp backend/.env.example backend/.env
```

- [ ] Run turn service tests:

```bash
docker compose run --rm backend pytest tests/test_turn_service.py
```

- [ ] Run socket flow tests:

```bash
docker compose run --rm backend pytest tests/test_socket_room_session_flow.py
```

- [ ] Run full backend tests:

```bash
docker compose run --rm backend pytest
```

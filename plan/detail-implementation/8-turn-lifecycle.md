## Goal
Add the base turn loop before action-card-specific logic is layered on top.

## Scope
- Current player tracking
- `pendingDraws` handling
- Normal draw-card flow
- Transition between action phase and draw phase
- Move to next alive player after a completed turn

## Done when
- A turn can progress from action window to draw to next player
- Normal non-exploding draws work correctly
- Turn state transitions are testable without sockets

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`

## Module design

```text
socket/application orchestration
    -> turn lifecycle service
        -> authoritative game aggregate / registry
        -> private player hands
        -> turn-state helpers
    -> public and private event mapping
```

The turn lifecycle service is domain logic only: it mutates authoritative
game state and returns an outcome for the application layer to broadcast. It
does not read sockets or emit Socket.IO events directly.

## Key decisions

- This issue establishes the base loop: `turn_action -> turn_draw -> turn_action`
  or `turn_action -> turn_draw -> next player's turn_action`.
- `pending_draws` is the number of draws the current player still owes before
  their turn ends. A normal new turn begins with `pending_draws = 1`.
- The draw pile uses index `0` as its top. Drawing removes the top card with
  `pop(0)`; this matches the setup service's deterministic dealing convention.
- A normal draw removes one card from `draw_pile`, adds it to the current
  player's private hand, increments that player's public `hand_count`, and
  decrements `pending_draws`.
- The draw pile must not be empty while a match remains `in_game`: there are
  `player_count - 1` bombs, a defused bomb is returned to the deck, and each
  non-defused bomb eliminates one player. Once the final required elimination
  occurs, only one player remains and the game ends before another draw.
  An empty draw pile during an active game is therefore an invariant violation,
  not a gameplay branch.
- When a normal draw leaves `pending_draws > 0`, the same player remains
  current and the phase returns to `turn_action`.
- When it leaves `pending_draws == 0`, the service advances to the next
  non-eliminated player by ascending `seat_index` circularly, increments
  `turn_number`, resets `pending_draws = 1`, and sets `phase = turn_action`.
- `turn_draw` is an internal transition while a validated draw resolves. A
  client can initiate `turn:draw-card` only from `turn_action`, preventing a
  duplicate draw request from drawing twice.
- Encountering `exploding_kitten` is not a normal draw. This issue removes it
  from the draw pile, retains it in authoritative `pending_explosion_card`
  state, sets `phase = resolving_explosion` and `action_lock = true`, and
  returns a distinct outcome. Defuse, elimination, and reinsertion rules
  belong to the explosion-flow issue.
- Action-card effects are out of scope, but the lifecycle exposes reusable
  helpers for later `Skip`, `Attack`, and explosion flows. Those effects will
  resolve from `turn_action` and either retain the current turn or use the
  same next-alive-player helper.
- Authoritative runtime state must retain both `ServerGameState` and
  `PlayerPrivateState` values. Storing only `ServerGameState` in `GameRegistry`
  would make it impossible to add a drawn card to its owner's hand.
- `GameRuntimeState` is the canonical aggregate stored in `GameRegistry`.
  Game-start orchestration constructs it from issue 7's `GameSetupResult`,
  retaining its `game_state` and `player_private_states` fields.
- The turn lifecycle service is constructed with `GameRegistry` and exposes
  `draw_card(room_id, player_id, request_id=None)` as its main use case. It
  loads the runtime aggregate internally so missing games can raise a named
  domain error.
- A disconnected current player pauses the game until reconnect in MVP. They
  remain in the turn order and are not auto-skipped; only `eliminated` players
  are skipped for turn selection.
- Normal draw resolution is atomic. The application layer broadcasts only the
  final state, not transient `turn_draw`; `resolving_explosion` may be
  broadcast because it represents a pending resolution visible to the room.
- Idempotency storage is deferred to realtime/application orchestration, but
  lifecycle use cases accept an optional `request_id` now so later work can
  replay a completed command instead of drawing twice.
- This issue does not wire `turn:draw-card` to Socket.IO. That integration is
  enabled only with idempotency handling in the realtime/application issue.
- `pending_explosion_card` belongs only to the runtime aggregate. It is never
  a `ServerGameState` field or a public/private socket payload field.
- A player whose status is not `connected` cannot draw or play an action.
  If turn progression selects a disconnected non-eliminated player, the service
  still advances `current_player_id`, increments `turn_number`, sets
  `pending_draws` according to the turn transition, and sets
  `phase = turn_action`. The match is considered paused by validation: that
  player cannot draw or play until their status is synchronized back to
  `connected`.
- Realtime/session orchestration keeps connectivity synchronized in both
  `RoomPlayerState.status` and the matching `GamePlayerSummary.status` in the
  runtime aggregate. Turn lifecycle validation uses the aggregate's status.
- `next_alive_player(...)` returns `None` when no other alive player exists.
  Its caller must finish the game rather than select the current player again.

## Implementation checklist

### 1. Authoritative game state access

- Add `GameRuntimeState` in `backend/app/modules/game/models.py`. It contains:
  - `game_state: ServerGameState`
  - `player_private_states: dict[str, PlayerPrivateState]`
  - `pending_explosion_card: CardInstance | None`
- Game-start orchestration constructs this aggregate from the existing
  `GameSetupResult` after setup succeeds, with `pending_explosion_card = None`.
- Update the game registry storage and API from `ServerGameState` to
  `GameRuntimeState`, so turn logic can retrieve this aggregate by `room_id`.
- Keep `pending_explosion_card` in the aggregate only. The later explosion
  service consumes it and clears it after either reinsertion or discard.
- Preserve the public/private separation: full hands remain available only in
  private state and are never copied into `ServerGameState.players`.

### 2. Turn lifecycle service

- Add `backend/app/modules/game/turn_service.py` .
- Add explicit game-domain errors in `backend/app/modules/game/errors.py`:
  - `GameNotFoundError`
  - `GameNotInProgressError`
  - `PlayerNotFoundError`
  - `NotCurrentPlayerError`
  - `PlayerEliminatedError`
  - `PlayerDisconnectedError`
  - `InvalidTurnPhaseError`
  - `TurnActionLockedError`
  - `PendingResolutionError`
  - `InvalidPendingDrawsError`
  - `EmptyDrawPileError`
- Define a typed lifecycle result in `turn_service.py` or `models.py`.
  - Outcomes are `normal_draw`, `explosion_pending`, and `game_finished`.
  - Result fields are `outcome`, `runtime`, `player_id`, and
    `request_id: str | None`.
  - This is a domain result, not a socket payload; private card data remains in
    the aggregate and is mapped only for the owning player.
  - Do not include the drawn card in the result. The drawn card is visible only
    through the drawing player's private state.
- Add `TurnLifecycleService(registry)` with the main use case
  `draw_card(room_id: str, player_id: str, request_id: str | None = None)`.
- `draw_card(...)` loads `GameRuntimeState` from `GameRegistry` and raises
  `GameNotFoundError` when absent.
- Validate before mutation:
  - `runtime.game_state.room_status` is `in_game`
  - phase is `turn_action`
  - caller is `current_player_id`
  - caller exists and is not eliminated
  - caller status is `connected`
  - `action_lock` is false
  - no unresolved draw/explosion flow is active
  - `pending_draws >= 1`
  - `draw_pile` is not empty
- Set `phase = turn_draw` only after all validation succeeds, including the
  empty draw-pile invariant check.
- Draw the top card, update the private hand and matching public `hand_count`,
  decrement `pending_draws`, and update `updated_at`.
- Treat an empty draw pile in an `in_game` match as an invariant/domain error;
  it is not a normal gameplay branch.
- On an `exploding_kitten` draw, remove the card from the draw pile, store it
  as `pending_explosion_card`, set `phase = resolving_explosion` and
  `action_lock = true`; do not add it to a hand or discard pile.
- An exploding-kitten draw does not decrement `pending_draws` in this issue.
  The later explosion-flow issue decrements or clears pending draws when it
  resolves defuse or elimination.
- Return a typed result/outcome that distinguishes a normal draw from an
  explosion transition without exposing hidden card data to public payloads.

### 3. Turn helpers and extension points

- Add a `next_alive_player(...)` helper based on circular `seat_index` order;
  return `None` if there is no other non-eliminated player.
- Add a `complete_turn(runtime, pending_draws_for_next=1)` helper that first
  selects the next alive player. If one exists, increment `turn_number`, set
  them as current, set `pending_draws = pending_draws_for_next`, and set
  `phase = turn_action`.
- When `next_alive_player(...)` returns `None`, `complete_turn(...)` finishes
  the game and records the current player as winner instead of resetting a
  turn for the same player. In this branch it sets `phase = finished`,
  `room_status = finished`, `winner_player_id = current_player_id`,
  `action_lock = false`, and updates `updated_at`; it does not reset
  `pending_draws` or increment `turn_number`.
- Use these helpers for a completed normal draw in this issue.
- Keep the helpers reusable for later action-card handlers:
  - `Skip` will decrement `pending_draws` without drawing, then retain or end
    the turn using the same helpers.
  - `Attack` will end the turn and call `complete_turn(...)` with inherited
    draws plus one for `pending_draws_for_next`.
  - Other action cards will resolve during `turn_action` and normally return
    to that phase without changing `pending_draws`.

### 4. Realtime integration notes

- Do not implement action-card resolution in this issue.
- Do not wire Socket.IO `turn:draw-card` in this issue. A later
  realtime/application issue may call the lifecycle service only after it
  persists the game aggregate in the registry and implements idempotency.
- The application layer maps the result to public game-state updates and a
  private hand update for the drawing player; it must not broadcast the drawn
  card type to other players.
- For a normal draw, broadcast the final resolved state only; do not emit the
  transient `turn_draw` phase.
- For an explosion transition, broadcast the `resolving_explosion` state as
  appropriate, without exposing private hands.
- Preserve `request_id` on the lifecycle interface. Later orchestration must
  deduplicate `(player_id, request_id)` and replay its stored outcome for a
  retried request instead of invoking the draw a second time.
- On disconnect, leave the disconnected current player as current and pause
  further play until reconnect; do not auto-skip them in MVP.
- Session/realtime orchestration must synchronize a connectivity change to both
  the room player and the matching game-player summary before broadcasting it.
- Game-start orchestration must atomically persist the runtime aggregate and
  transition both `RoomState.status` and `ServerGameState.room_status` to
  `in_game` before it enables turn commands.
- When a lifecycle outcome is `game_finished`, application orchestration must
  also transition the authoritative `RoomState.status` to `finished` before
  broadcasting the completed game. The lifecycle service itself only mutates
  `ServerGameState` and returns the outcome.
- The realtime/application work above is documented as follow-up scope. This
  issue only adds the domain service, runtime aggregate, registry access,
  reusable turn helpers, and socket-independent tests.

### 5. Tests

- Add focused unit tests independent of Socket.IO for:
  - a valid normal draw adds the top card to only the current player's hand
  - construction from `GameSetupResult` preserves the same game state and
    private-player states in `GameRuntimeState`, with
    `pending_explosion_card = None`
  - the draw pile and public hand count are updated correctly
  - a normal draw leaves `pending_explosion_card` as `None`
  - `pending_draws = 2` becomes `1` and retains the same player/turn
  - `pending_draws = 1` completes the turn, advances seating order, increments
    `turn_number`, and resets `pending_draws = 1`
  - next-player selection wraps around and skips eliminated players
  - no next alive player yields a finished-game outcome instead of selecting
    the same player again
  - not-found, non-current, eliminated, locked, wrong-phase, and non-`in_game`
    requests are rejected without state mutation
  - a disconnected player cannot draw
  - selecting a disconnected next player advances to that player, and
    subsequent draw/action requests are rejected with `PlayerDisconnectedError`
    until reconnect
  - `pending_draws < 1` is rejected without state mutation
  - a draw is rejected without state mutation when
    `pending_explosion_card` is already present
  - an empty draw pile during an active game is rejected as an invariant error
    with `EmptyDrawPileError`
  - an exploding-kitten draw is removed from the deck and retained as
    `pending_explosion_card`, then follows the distinct explosion transition
    rather than being added to a hand as a normal card
  - validation failures raise the corresponding named game-domain error, and
    successful draws return the appropriate typed lifecycle outcome
  - lifecycle results include `outcome`, `runtime`, `player_id`, and the
    optional `request_id`, but never expose the drawn card directly
- Use deterministic card/deck fixtures; specifically assert that index `0` is
  drawn first.

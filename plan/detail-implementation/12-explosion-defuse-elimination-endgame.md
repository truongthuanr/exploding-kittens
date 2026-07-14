## Goal
Complete the core survival loop that ends turns, eliminates players, and decides the winner.

## Scope
- Resolve `Exploding Kitten` draws
- Auto-consume `Defuse` when available
- Reinsert the exploding card into the deck
- Eliminate players without `Defuse`
- Detect match end and winner

## Done when
- Explosions resolve according to the spec
- Defuse and elimination behavior are correct
- The server can finish a full match and declare a winner

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`

## Implementation checklist

### 1. Preserve the MVP resolution model

- [x] Keep `Defuse` as automatic server-side resolution for MVP.
- [x] Keep reaction-window gameplay out of this issue.
- [x] Do not allow normal `turn:play-card` or `turn:draw-card` actions while `pending_explosion_card` exists.
- [x] Keep the drawn `Exploding Kitten` in authoritative runtime state until the explosion is resolved.
- [x] Do not expose the pending bomb card through public payloads.
- [x] Keep `draw_card(...)` responsible only for transitioning into `EXPLOSION_PENDING`.
- [x] Resolve the pending explosion immediately from MVP orchestration by calling `resolve_pending_explosion(...)`.
- [x] Do not require the client to send a separate Defuse action.
- [x] Keep Socket.IO wiring out of scope; engine tests may call `resolve_pending_explosion(...)` directly after `draw_card(...)` returns `EXPLOSION_PENDING`.

Implementation note:

- A future post-MVP reaction window is tracked separately in GitHub issue #38.

### 2. Add an explosion resolution entrypoint

- [x] Add `TurnLifecycleService.resolve_pending_explosion(...)`.
- [x] Keep it engine/service-level only; Socket.IO wiring is not required in this issue.
- [x] Return the existing typed `TurnLifecycleResult` shape.
- [x] Preserve `request_id` passthrough behavior like `draw_card(...)`.
- [x] Add explosion-specific `TurnLifecycleOutcome` values:
  - `DEFUSED = "defused"`
  - `PLAYER_ELIMINATED = "player_eliminated"`
- [x] If resolving the explosion finishes the game, return the existing `GAME_FINISHED` outcome.

Suggested method inputs:

- `room_id: str`
- `player_id: str`
- `request_id: str | None = None`

### 3. Validate explosion resolution

- [x] Validate game exists in `GameRegistry`.
- [x] Validate `room_status == in_game`.
- [x] Validate `phase == resolving_explosion`.
- [x] Validate `action_lock == true` before resolution starts.
- [x] Validate `pending_explosion_card` exists.
- [x] Treat `pending_explosion_card` plus mismatched `phase` or `action_lock` as invalid runtime state and reject without mutation.
- [x] Validate player exists in public and private state.
- [x] Validate player is `current_player_id`.
- [x] Reject eliminated players.
- [x] Do not reject disconnected players; explosion resolution is server-owned and must not block on player connection status.
- [x] Validate `pending_draws >= 1`.
- [x] Ensure validation failures do not mutate runtime state.

Implementation notes:

- Add `NoPendingExplosionError` when there is no pending explosion to resolve.
- Add `InvalidExplosionStateError` for `pending_explosion_card` plus mismatched `phase` or `action_lock`.

### 4. Resolve explosion with `Defuse`

- [x] Find one `CardType.DEFUSE` in the current player's private hand.
- [x] Remove exactly one `Defuse` from private hand.
- [x] Append that same `Defuse` card to `discard_pile`.
- [x] Decrement the player's public `hand_count` by 1.
- [x] Reinsert `pending_explosion_card` into `draw_pile` at a server-chosen random position.
- [x] Clear `runtime.pending_explosion_card`.
- [x] Decrement `pending_draws` by 1.
- [x] Set `action_lock = false`.
- [x] If `pending_draws > 0`, keep the same current player and set `phase = turn_action`.
- [x] If `pending_draws == 0`, complete the turn and advance to the next alive player.
- [x] Update `updated_at`.
- [x] Return `DEFUSED` unless turn completion finishes the game.

Implementation notes:

- [x] Inject `random.Random` into `TurnLifecycleService` for deterministic tests.
- Insert position must allow every valid deck slot from `0` through `len(draw_pile)`.
- Use the injected randomizer to choose the insert position.
- The bomb must not enter the discard pile when it is defused.

Expected examples:

- [x] `pending_draws = 1`, player has `Defuse` -> consume Defuse, reinsert bomb, next alive player starts with `pending_draws = 1`.
- [x] `pending_draws = 3`, player has `Defuse` -> consume Defuse, reinsert bomb, same player remains current with `pending_draws = 2`.

### 5. Resolve explosion without `Defuse`

- [x] Mark the current player's public status as `eliminated`.
- [x] Add the player id to `eliminated_player_ids` if it is not already present.
- [x] Append `pending_explosion_card` to `discard_pile`.
- [x] Append the eliminated player's remaining hand cards to `discard_pile`.
- [x] Clear the eliminated player's private hand.
- [x] Clear `visible_future_cards` for the eliminated player.
- [x] Set the eliminated player's public `hand_count = 0`.
- [x] Clear `runtime.pending_explosion_card`.
- [x] Set `action_lock = false`.
- [x] Do not preserve the eliminated player's old `pending_draws`.
- [x] If more than one player remains alive, advance to the next alive player with `pending_draws = 1`.
- [x] If only one player remains alive, finish the game and set the surviving player as winner.
- [x] Update `updated_at`.
- [x] Return `PLAYER_ELIMINATED` unless the game finishes.

Implementation notes:

- Do not call `complete_turn(...)` directly for the final elimination branch if it would set the eliminated current player as winner.
- Add `alive_players(runtime)` or `sole_alive_player(runtime)` for elimination endgame resolution.
- The bomb must enter the discard pile when the player is eliminated.

Expected examples:

- [x] 3 players alive, current player has no `Defuse` -> current player is eliminated, next alive player starts with `pending_draws = 1`.
- [x] 2 players alive, current player has no `Defuse` -> current player is eliminated, game finishes with the other player as winner.

### 6. Keep turn progression consistent

- [x] Reuse existing next-player seat order rules.
- [x] Continue skipping eliminated players.
- [x] Preserve disconnected-but-not-eliminated players as possible next current players, matching current turn lifecycle behavior.
- [x] Set `phase = turn_action` for continued games after resolution.
- [x] Set `phase = finished` and `room_status = finished` for completed games.
- [x] Ensure `winner_player_id` is set only when the game is finished.

### 7. Add focused unit tests

- [x] Drawing `Exploding Kitten` still enters `EXPLOSION_PENDING` without decrementing `pending_draws`.
- [x] Resolving with `Defuse` consumes exactly one Defuse.
- [x] Resolving with `Defuse` appends Defuse to discard and does not discard the bomb.
- [x] Resolving with `Defuse` reinserts the bomb into the draw pile.
- [x] Resolving with `Defuse` and one pending draw advances to the next alive player.
- [x] Resolving with `Defuse` and multiple pending draws keeps the same current player and decrements by exactly one.
- [x] Resolving without `Defuse` eliminates the current player.
- [x] Resolving without `Defuse` discards the bomb and the eliminated player's remaining hand.
- [x] Resolving without `Defuse` clears the eliminated player's private hand and visible future cards.
- [x] Resolving without `Defuse` advances to the next alive player when more than one player remains alive.
- [x] Resolving without `Defuse` finishes the game with the surviving player as winner when one player remains alive.
- [x] Invalid explosion resolution requests are rejected without state mutation:
  - missing game
  - wrong phase
  - no `pending_explosion_card`
  - wrong current player
  - eliminated player
  - invalid `pending_draws`
- [x] Disconnected current player still resolves pending explosion because resolution is server-owned.
- [x] Normal draw/play-card requests remain rejected while `pending_explosion_card` exists.

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

- [ ] Keep `Defuse` as automatic server-side resolution for MVP.
- [ ] Keep reaction-window gameplay out of this issue.
- [ ] Do not allow normal `turn:play-card` or `turn:draw-card` actions while `pending_explosion_card` exists.
- [ ] Keep the drawn `Exploding Kitten` in authoritative runtime state until the explosion is resolved.
- [ ] Do not expose the pending bomb card through public payloads.
- [ ] Keep `draw_card(...)` responsible only for transitioning into `EXPLOSION_PENDING`.
- [ ] Resolve the pending explosion immediately from MVP orchestration by calling `resolve_pending_explosion(...)`.
- [ ] Do not require the client to send a separate Defuse action.
- [ ] Keep Socket.IO wiring out of scope; engine tests may call `resolve_pending_explosion(...)` directly after `draw_card(...)` returns `EXPLOSION_PENDING`.

Implementation note:

- A future post-MVP reaction window is tracked separately in GitHub issue #38.

### 2. Add an explosion resolution entrypoint

- [ ] Add `TurnLifecycleService.resolve_pending_explosion(...)`.
- [ ] Keep it engine/service-level only; Socket.IO wiring is not required in this issue.
- [ ] Return the existing typed `TurnLifecycleResult` shape.
- [ ] Preserve `request_id` passthrough behavior like `draw_card(...)`.
- [ ] Add explosion-specific `TurnLifecycleOutcome` values:
  - `DEFUSED = "defused"`
  - `PLAYER_ELIMINATED = "player_eliminated"`
- [ ] If resolving the explosion finishes the game, return the existing `GAME_FINISHED` outcome.

Suggested method inputs:

- `room_id: str`
- `player_id: str`
- `request_id: str | None = None`

### 3. Validate explosion resolution

- [ ] Validate game exists in `GameRegistry`.
- [ ] Validate `room_status == in_game`.
- [ ] Validate `phase == resolving_explosion`.
- [ ] Validate `action_lock == true` before resolution starts.
- [ ] Validate `pending_explosion_card` exists.
- [ ] Treat `pending_explosion_card` plus mismatched `phase` or `action_lock` as invalid runtime state and reject without mutation.
- [ ] Validate player exists in public and private state.
- [ ] Validate player is `current_player_id`.
- [ ] Reject eliminated players.
- [ ] Do not reject disconnected players; explosion resolution is server-owned and must not block on player connection status.
- [ ] Validate `pending_draws >= 1`.
- [ ] Ensure validation failures do not mutate runtime state.

Implementation notes:

- Add `NoPendingExplosionError` when there is no pending explosion to resolve.
- Add `InvalidExplosionStateError` for `pending_explosion_card` plus mismatched `phase` or `action_lock`.

### 4. Resolve explosion with `Defuse`

- [ ] Find one `CardType.DEFUSE` in the current player's private hand.
- [ ] Remove exactly one `Defuse` from private hand.
- [ ] Append that same `Defuse` card to `discard_pile`.
- [ ] Decrement the player's public `hand_count` by 1.
- [ ] Reinsert `pending_explosion_card` into `draw_pile` at a server-chosen random position.
- [ ] Clear `runtime.pending_explosion_card`.
- [ ] Decrement `pending_draws` by 1.
- [ ] Set `action_lock = false`.
- [ ] If `pending_draws > 0`, keep the same current player and set `phase = turn_action`.
- [ ] If `pending_draws == 0`, complete the turn and advance to the next alive player.
- [ ] Update `updated_at`.
- [ ] Return `DEFUSED` unless turn completion finishes the game.

Implementation notes:

- [ ] Inject `random.Random` into `TurnLifecycleService` for deterministic tests.
- Insert position must allow every valid deck slot from `0` through `len(draw_pile)`.
- Use the injected randomizer to choose the insert position.
- The bomb must not enter the discard pile when it is defused.

Expected examples:

- [ ] `pending_draws = 1`, player has `Defuse` -> consume Defuse, reinsert bomb, next alive player starts with `pending_draws = 1`.
- [ ] `pending_draws = 3`, player has `Defuse` -> consume Defuse, reinsert bomb, same player remains current with `pending_draws = 2`.

### 5. Resolve explosion without `Defuse`

- [ ] Mark the current player's public status as `eliminated`.
- [ ] Add the player id to `eliminated_player_ids` if it is not already present.
- [ ] Append `pending_explosion_card` to `discard_pile`.
- [ ] Append the eliminated player's remaining hand cards to `discard_pile`.
- [ ] Clear the eliminated player's private hand.
- [ ] Clear `visible_future_cards` for the eliminated player.
- [ ] Set the eliminated player's public `hand_count = 0`.
- [ ] Clear `runtime.pending_explosion_card`.
- [ ] Set `action_lock = false`.
- [ ] Do not preserve the eliminated player's old `pending_draws`.
- [ ] If more than one player remains alive, advance to the next alive player with `pending_draws = 1`.
- [ ] If only one player remains alive, finish the game and set the surviving player as winner.
- [ ] Update `updated_at`.
- [ ] Return `PLAYER_ELIMINATED` unless the game finishes.

Implementation notes:

- Do not call `complete_turn(...)` directly for the final elimination branch if it would set the eliminated current player as winner.
- Add `alive_players(runtime)` or `sole_alive_player(runtime)` for elimination endgame resolution.
- The bomb must enter the discard pile when the player is eliminated.

Expected examples:

- [ ] 3 players alive, current player has no `Defuse` -> current player is eliminated, next alive player starts with `pending_draws = 1`.
- [ ] 2 players alive, current player has no `Defuse` -> current player is eliminated, game finishes with the other player as winner.

### 6. Keep turn progression consistent

- [ ] Reuse existing next-player seat order rules.
- [ ] Continue skipping eliminated players.
- [ ] Preserve disconnected-but-not-eliminated players as possible next current players, matching current turn lifecycle behavior.
- [ ] Set `phase = turn_action` for continued games after resolution.
- [ ] Set `phase = finished` and `room_status = finished` for completed games.
- [ ] Ensure `winner_player_id` is set only when the game is finished.

### 7. Add focused unit tests

- [ ] Drawing `Exploding Kitten` still enters `EXPLOSION_PENDING` without decrementing `pending_draws`.
- [ ] Resolving with `Defuse` consumes exactly one Defuse.
- [ ] Resolving with `Defuse` appends Defuse to discard and does not discard the bomb.
- [ ] Resolving with `Defuse` reinserts the bomb into the draw pile.
- [ ] Resolving with `Defuse` and one pending draw advances to the next alive player.
- [ ] Resolving with `Defuse` and multiple pending draws keeps the same current player and decrements by exactly one.
- [ ] Resolving without `Defuse` eliminates the current player.
- [ ] Resolving without `Defuse` discards the bomb and the eliminated player's remaining hand.
- [ ] Resolving without `Defuse` clears the eliminated player's private hand and visible future cards.
- [ ] Resolving without `Defuse` advances to the next alive player when more than one player remains alive.
- [ ] Resolving without `Defuse` finishes the game with the surviving player as winner when one player remains alive.
- [ ] Invalid explosion resolution requests are rejected without state mutation:
  - missing game
  - wrong phase
  - no `pending_explosion_card`
  - wrong current player
  - eliminated player
  - invalid `pending_draws`
- [ ] Disconnected current player still resolves pending explosion because resolution is server-owned.
- [ ] Normal draw/play-card requests remain rejected while `pending_explosion_card` exists.

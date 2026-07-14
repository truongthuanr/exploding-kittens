## Goal
Implement the two turn-control cards that define most of the MVP turn pressure.

## Scope
- Resolve `skip`
- Resolve `attack`
- Update `pendingDraws` correctly
- Support attack chaining policy from the docs

## Done when
- `skip` reduces pending draws correctly
- `attack` hands off the turn and pending draws correctly
- Tests cover the documented `pendingDraws` behavior

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`

## Implementation checklist

### 1. Add action-card service entrypoints

- [ ] Add `TurnLifecycleService.play_skip(...)`.
- [ ] Add `TurnLifecycleService.play_attack(...)`.
- [ ] Keep both methods engine/service-level only; do not require Socket.IO wiring in this issue.
- [ ] Return the existing typed `TurnLifecycleResult` shape.
- [ ] Add action-specific `TurnLifecycleOutcome` values so action-card results do not reuse `NORMAL_DRAW`:
  - `SKIP_PLAYED = "skip_played"`
  - `ATTACK_PLAYED = "attack_played"`
- [ ] If an action-card play finishes the game, return the existing `GAME_FINISHED` outcome instead of the action-specific outcome.
- [ ] Preserve `request_id` passthrough behavior like `draw_card(...)`.

Suggested method inputs:

- `room_id: str`
- `player_id: str`
- `card_id: str`
- `request_id: str | None = None`

### 2. Add shared action-card validation

- [ ] Validate game exists in `GameRegistry`.
- [ ] Validate `room_status == in_game`.
- [ ] Reject if `pending_explosion_card` exists.
- [ ] Validate `phase == turn_action`.
- [ ] Reject if `action_lock == true`.
- [ ] Validate player exists in public and private state.
- [ ] Validate player is `current_player_id`.
- [ ] Reject eliminated players.
- [ ] Reject disconnected players.
- [ ] Validate `pending_draws >= 1`.
- [ ] Validate the requested `card_id` exists in the current player's hand.
- [ ] Validate the card type matches the action:
  - `play_skip` requires `CardType.SKIP`
  - `play_attack` requires `CardType.ATTACK`

Implementation note:

- [ ] Reuse as much of `validate_draw_request(...)` logic as practical, but do not check `draw_pile` for action cards.
- [ ] Add `CardNotInHandError` for a requested card id that is not in the player's hand.
- [ ] Add `InvalidCardTypeError` for a requested card id whose type does not match the action.
- [ ] Ensure validation failures do not mutate runtime state.

### 3. Move played card from hand to discard

- [ ] Remove the exact `card_id` from the player's private hand.
- [ ] Append that same `CardInstance` to `game_state.discard_pile`.
- [ ] Decrement the matching public `GamePlayerSummary.hand_count` by 1.
- [ ] Avoid exposing hidden hand card data through public result objects.
- [ ] Update `updated_at` for successful action-card resolution.

Implementation note:

- [ ] Treat `card_id` as globally unique within the runtime state.
- [ ] Use the removed `CardInstance` object for the discard pile; do not create a replacement card.

### 4. Implement `Skip`

- [ ] After discarding `skip`, decrement `game_state.pending_draws` by 1.
- [ ] If `pending_draws > 0`, keep the same `current_player_id`.
- [ ] If `pending_draws > 0`, keep/set `phase = turn_action`.
- [ ] If `pending_draws == 0`, call `complete_turn(runtime)`.
- [ ] Confirm normal turn completion resets the next player to `pending_draws = 1`.
- [ ] Confirm game-finished branch still works if no other alive player exists.
- [ ] Return `SKIP_PLAYED` unless `complete_turn(...)` returns `GAME_FINISHED`.

Expected examples:

- [ ] `pending_draws = 1`, player plays `skip` -> next alive player starts with `pending_draws = 1`.
- [ ] `pending_draws = 3`, player plays `skip` -> same player remains current with `pending_draws = 2`.

### 5. Implement `Attack`

- [ ] Capture current `pending_draws` before ending the turn.
- [ ] After discarding `attack`, end current turn without drawing.
- [ ] Call `complete_turn(runtime, pending_draws_for_next=current_pending_draws + 1)`.
- [ ] Confirm next alive player receives inherited pending draws plus one.
- [ ] Confirm game-finished branch still works if no other alive player exists.
- [ ] Return `ATTACK_PLAYED` unless `complete_turn(...)` returns `GAME_FINISHED`.

Expected examples:

- [ ] `pending_draws = 1`, player plays `attack` -> next alive player gets `pending_draws = 2`.
- [ ] `pending_draws = 3`, player plays `attack` -> next alive player gets `pending_draws = 4`.
- [ ] Attack chaining: player 1 attacks with `1` -> player 2 gets `2`; player 2 attacks -> player 3 gets `3`.

### 6. Add focused unit tests

- [ ] `skip` with one pending draw discards card, decrements hand count, advances turn, and next player has `pending_draws = 1`.
- [ ] `skip` successful result returns `SKIP_PLAYED`, except game-finished branch returns `GAME_FINISHED`.
- [ ] `skip` with multiple pending draws discards card, decrements hand count, keeps same current player, and decrements pending by exactly 1.
- [ ] `attack` with one pending draw discards card, decrements hand count, advances turn, and next player has `pending_draws = 2`.
- [ ] `attack` successful result returns `ATTACK_PLAYED`, except game-finished branch returns `GAME_FINISHED`.
- [ ] `attack` with multiple pending draws advances turn and sets next player pending to old value plus 1.
- [ ] Attack chaining preserves the documented stacking policy.
- [ ] Played cards are removed from private hand and appended to discard pile by identity or matching `card_id`.
- [ ] Other players' private hands are unchanged.
- [ ] Invalid action-card requests are rejected without state mutation:
  - wrong current player
  - eliminated player
  - disconnected player
  - locked action
  - wrong phase
  - game not in progress
  - pending explosion
  - invalid `pending_draws`
  - missing player
  - card not in hand
  - wrong card type for action

### 7. Run verification

- [ ] Run turn service tests.
- [ ] Run existing backend tests if feasible.
- [ ] Confirm no contract enum/schema changes are needed for this issue.

Suggested commands:

```bash
cd backend
pytest tests/test_turn_service.py
pytest
```

## Out of scope

- Socket.IO wiring for `turn:play-card`.
- Client payload/result mapping.
- Idempotency storage.
- `Shuffle`, `See the Future`, and `Favor`.
- Explosion, defuse, and elimination resolution.

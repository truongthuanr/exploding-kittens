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

- [x] Add `TurnLifecycleService.play_skip(...)`.
- [x] Add `TurnLifecycleService.play_attack(...)`.
- [x] Keep both methods engine/service-level only; do not require Socket.IO wiring in this issue.
- [x] Return the existing typed `TurnLifecycleResult` shape.
- [x] Add action-specific `TurnLifecycleOutcome` values so action-card results do not reuse `NORMAL_DRAW`:
  - `SKIP_PLAYED = "skip_played"`
  - `ATTACK_PLAYED = "attack_played"`
- [x] If an action-card play finishes the game, return the existing `GAME_FINISHED` outcome instead of the action-specific outcome.
- [x] Preserve `request_id` passthrough behavior like `draw_card(...)`.

Suggested method inputs:

- `room_id: str`
- `player_id: str`
- `card_id: str`
- `request_id: str | None = None`

### 2. Add shared action-card validation

- [x] Validate game exists in `GameRegistry`.
- [x] Validate `room_status == in_game`.
- [x] Reject if `pending_explosion_card` exists.
- [x] Validate `phase == turn_action`.
- [x] Reject if `action_lock == true`.
- [x] Validate player exists in public and private state.
- [x] Validate player is `current_player_id`.
- [x] Reject eliminated players.
- [x] Reject disconnected players.
- [x] Validate `pending_draws >= 1`.
- [x] Validate the requested `card_id` exists in the current player's hand.
- [x] Validate the card type matches the action:
  - `play_skip` requires `CardType.SKIP`
  - `play_attack` requires `CardType.ATTACK`

Implementation note:

- [x] Reuse as much of `validate_draw_request(...)` logic as practical, but do not check `draw_pile` for action cards.
- [x] Add `CardNotInHandError` for a requested card id that is not in the player's hand.
- [x] Add `InvalidCardTypeError` for a requested card id whose type does not match the action.
- [x] Ensure validation failures do not mutate runtime state.

### 3. Move played card from hand to discard

- [x] Remove the exact `card_id` from the player's private hand.
- [x] Append that same `CardInstance` to `game_state.discard_pile`.
- [x] Decrement the matching public `GamePlayerSummary.hand_count` by 1.
- [x] Avoid exposing hidden hand card data through public result objects.
- [x] Update `updated_at` for successful action-card resolution.

Implementation note:

- [x] Treat `card_id` as globally unique within the runtime state.
- [x] Use the removed `CardInstance` object for the discard pile; do not create a replacement card.

### 4. Implement `Skip`

- [x] After discarding `skip`, decrement `game_state.pending_draws` by 1.
- [x] If `pending_draws > 0`, keep the same `current_player_id`.
- [x] If `pending_draws > 0`, keep/set `phase = turn_action`.
- [x] If `pending_draws == 0`, call `complete_turn(runtime)`.
- [x] Confirm normal turn completion resets the next player to `pending_draws = 1`.
- [x] Confirm game-finished branch still works if no other alive player exists.
- [x] Return `SKIP_PLAYED` unless `complete_turn(...)` returns `GAME_FINISHED`.

Expected examples:

- [x] `pending_draws = 1`, player plays `skip` -> next alive player starts with `pending_draws = 1`.
- [x] `pending_draws = 3`, player plays `skip` -> same player remains current with `pending_draws = 2`.

### 5. Implement `Attack`

- [x] Capture current `pending_draws` before ending the turn.
- [x] After discarding `attack`, end current turn without drawing.
- [x] Call `complete_turn(runtime, pending_draws_for_next=current_pending_draws + 1)`.
- [x] Confirm next alive player receives inherited pending draws plus one.
- [x] Confirm game-finished branch still works if no other alive player exists.
- [x] Return `ATTACK_PLAYED` unless `complete_turn(...)` returns `GAME_FINISHED`.

Expected examples:

- [x] `pending_draws = 1`, player plays `attack` -> next alive player gets `pending_draws = 2`.
- [x] `pending_draws = 3`, player plays `attack` -> next alive player gets `pending_draws = 4`.
- [x] Attack chaining: player 1 attacks with `1` -> player 2 gets `2`; player 2 attacks -> player 3 gets `3`.

### 6. Add focused unit tests

- [x] `skip` with one pending draw discards card, decrements hand count, advances turn, and next player has `pending_draws = 1`.
- [x] `skip` successful result returns `SKIP_PLAYED`, except game-finished branch returns `GAME_FINISHED`.
- [x] `skip` with multiple pending draws discards card, decrements hand count, keeps same current player, and decrements pending by exactly 1.
- [x] `attack` with one pending draw discards card, decrements hand count, advances turn, and next player has `pending_draws = 2`.
- [x] `attack` successful result returns `ATTACK_PLAYED`, except game-finished branch returns `GAME_FINISHED`.
- [x] `attack` with multiple pending draws advances turn and sets next player pending to old value plus 1.
- [x] Attack chaining preserves the documented stacking policy.
- [x] Played cards are removed from private hand and appended to discard pile by identity or matching `card_id`.
- [x] Other players' private hands are unchanged.
- [x] Invalid action-card requests are rejected without state mutation:
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

- [x] Run turn service tests.
- [x] Run existing backend tests if feasible.
- [x] Confirm no contract enum/schema changes are needed for this issue.

Suggested commands:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_turn_service.py
PYTHONPATH=. .venv/bin/pytest
```

## Out of scope

- Socket.IO wiring for `turn:play-card`.
- Client payload/result mapping.
- Idempotency storage.
- `Shuffle`, `See the Future`, and `Favor`.
- Explosion, defuse, and elimination resolution.

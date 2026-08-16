## Goal
Implement the deck-manipulation and hidden-information card effects.

## Scope
- Resolve `shuffle`
- Resolve `see_the_future`
- Keep draw-pile order hidden from other players
- Produce the private payload for future-card visibility

## Done when
- `shuffle` randomizes the draw pile on the server
- `see_the_future` returns only private information to the acting player
- No public payload leaks deck order

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`

## Decisions

- [x] `see_the_future` with an empty draw pile resolves successfully and stores `[]`.
- [x] `shuffle` clears `visible_future_cards` for every player.
- [x] `see_the_future` overwrites the acting player's previous `visible_future_cards`.
- [x] `shuffle`, `draw_card`, and defused bomb reinsertion clear `visible_future_cards` for every player.
- [x] Shuffle tests must use deterministic randomizer behavior instead of relying on real randomness.

## Implementation checklist

### 1. Add deck-action service entrypoints

- [x] Add `TurnLifecycleService.play_shuffle(...)`.
- [x] Add `TurnLifecycleService.play_see_the_future(...)`.
- [x] Return the existing typed `TurnLifecycleResult` shape.
- [x] Preserve `request_id` passthrough behavior like the existing turn actions.
- [x] Add action-specific `TurnLifecycleOutcome` values:
  - `SHUFFLE_PLAYED = "shuffle_played"`
  - `SEE_THE_FUTURE_PLAYED = "see_the_future_played"`
- [x] Keep both methods server-authoritative; client payload must provide only `card_id`, not deck order or future-card contents.

Suggested method inputs:

- `room_id: str`
- `player_id: str`
- `card_id: str`
- `request_id: str | None = None`

### 2. Reuse existing action-card validation

- [x] Use `validate_action_card_request(...)` for both actions.
- [x] `play_shuffle` requires `CardType.SHUFFLE`.
- [x] `play_see_the_future` requires `CardType.SEE_THE_FUTURE`.
- [x] Preserve existing checks for:
  - game exists
  - room is `in_game`
  - no pending explosion
  - phase is `turn_action`
  - action is not locked
  - player exists in public and private state
  - player is current player
  - player is not eliminated
  - player is connected
  - `pending_draws >= 1`
  - requested card exists in hand
  - requested card has the expected type
- [x] Ensure validation failures do not mutate runtime state.
- [x] Do not require `draw_pile` to be non-empty for `shuffle`.
- [x] Allow `see_the_future` to resolve with fewer than 3 cards if the draw pile has fewer than 3 cards.
- [x] Allow `see_the_future` to resolve with an empty draw pile by storing `[]`.

### 3. Move played cards from hand to discard

- [x] Remove the exact played card from the current player's private hand.
- [x] Append that same `CardInstance` to `game_state.discard_pile`.
- [x] Decrement the matching public `GamePlayerSummary.hand_count` by 1.
- [x] Keep public payload limited to discard top type/count and hand counts.
- [x] Update `updated_at` for successful action resolution.

Implementation note:

- Reuse `_discard_card_from_hand(...)`; do not create replacement card instances.

### 4. Implement `Shuffle`

- [x] After discarding `shuffle`, randomize the full `game_state.draw_pile` on the server.
- [x] Use the injected `TurnLifecycleService.randomizer` so tests can be deterministic.
- [x] Do not trust or accept any client-provided deck order.
- [x] Keep `pending_draws` unchanged.
- [x] Keep `current_player_id` unchanged.
- [x] Keep `turn_number` unchanged.
- [x] Set/keep `phase = turn_action`.
- [x] Clear stale `visible_future_cards` for every player, because the previous future-card view is no longer valid after shuffle.
- [x] Return `SHUFFLE_PLAYED`.

Expected examples:

- [x] `pending_draws = 1`, player plays `shuffle` -> same player remains current with `pending_draws = 1`.
- [x] `pending_draws = 3`, player plays `shuffle` -> same player remains current with `pending_draws = 3`.
- [x] Draw pile with 0 or 1 card still resolves without error and does not leak deck contents.

### 5. Implement `See the Future`

- [x] After discarding `see_the_future`, read `game_state.draw_pile[:3]`.
- [x] Store only card types in the acting player's `visible_future_cards`.
- [x] Overwrite the acting player's previous `visible_future_cards`; do not append or merge with a previous view.
- [x] If the draw pile has fewer than 3 cards, store only the available card types.
- [x] If the draw pile is empty, store `[]`.
- [x] Do not mutate `game_state.draw_pile` order or card instances.
- [x] Keep `pending_draws` unchanged.
- [x] Keep `current_player_id` unchanged.
- [x] Keep `turn_number` unchanged.
- [x] Set/keep `phase = turn_action`.
- [x] Return `SEE_THE_FUTURE_PLAYED`.

Expected examples:

- [x] Top deck `[attack, defuse, exploding_kitten, skip]` -> acting player sees `[attack, defuse, exploding_kitten]`.
- [x] Top deck `[skip]` -> acting player sees `[skip]`.
- [x] Empty draw pile -> acting player sees `[]` and deck remains unchanged.

### 6. Wire Socket.IO `turn:play-card`

- [x] Add `CardType.SHUFFLE` branch in `handle_turn_play_card(...)`.
- [x] Add `CardType.SEE_THE_FUTURE` branch in `handle_turn_play_card(...)`.
- [x] Stop returning `unsupported_card_action` for these two cards.
- [x] Map `SHUFFLE_PLAYED` to `ActionType.PLAY_SHUFFLE`.
- [x] Map `SEE_THE_FUTURE_PLAYED` to `ActionType.PLAY_SEE_THE_FUTURE`.
- [x] Add recent-action summaries:
  - `"{nickname} played Shuffle"`
  - `"{nickname} played See the Future"`
- [x] Preserve room lock and duplicate `requestId` behavior.
- [x] Emit public `game:state` after each action.
- [x] Emit private state so only the acting player's private payload contains the future-card result.

Implementation note:

- Existing `emit_private_states(...)` is acceptable only if every private state is emitted directly to its owning player's socket.

### 7. Preserve hidden information boundaries

- [x] Confirm `PublicGameStateEvent` does not include `draw_pile`.
- [x] Confirm public payload does not include future-card results.
- [x] Confirm public payload does not include card ids/types from other players' hands.
- [x] Confirm `PlayerPrivateStateEvent.visibleFutureCards` is emitted only through private-state events.
- [x] Confirm non-acting players keep `visibleFutureCards` as their own prior value or `None`; they must not receive the acting player's result.
- [x] Confirm shuffle does not broadcast the new deck order.

### 8. Add focused unit tests

- [x] `shuffle` discards the played card.
- [x] `shuffle` decrements the acting player's public hand count.
- [x] `shuffle` randomizes the draw pile through deterministic test behavior, such as a fake randomizer that reverses the list.
- [x] `shuffle` keeps pending draws, current player, turn number, and phase unchanged except `updated_at`.
- [x] `shuffle` clears stale `visible_future_cards`.
- [x] `shuffle` succeeds with 0, 1, and multiple draw-pile cards.
- [x] `see_the_future` discards the played card.
- [x] `see_the_future` decrements the acting player's public hand count.
- [x] `see_the_future` stores the top 3 card types in the acting player's private state.
- [x] `see_the_future` handles draw piles with fewer than 3 cards.
- [x] `see_the_future` handles an empty draw pile by storing `[]`.
- [x] `see_the_future` overwrites any previous future-card view for the acting player.
- [x] `see_the_future` does not change draw-pile order.
- [x] Other players' private hands are unchanged.
- [x] Existing stale future visibility is cleared for every player when any player draws a card.
- [x] Existing stale future visibility is cleared for every player when a defused bomb is reinserted into the draw pile.
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

### 9. Add socket integration tests

- [x] Playing `shuffle` through `turn:play-card` resolves successfully instead of `unsupported_card_action`.
- [x] Playing `see_the_future` through `turn:play-card` resolves successfully instead of `unsupported_card_action`.
- [x] Public `game:state` after `shuffle` does not include `draw_pile` or deck order.
- [x] Public `game:state` after `see_the_future` does not include future-card contents.
- [x] Acting player receives `player:private-state.visibleFutureCards` after `see_the_future`.
- [x] Non-acting players do not receive the acting player's future-card result.
- [x] Duplicate `requestId` returns requester snapshot without applying the action twice.

### 10. Run verification

- [x] Run turn service tests.
- [x] Run socket room/session flow tests.
- [x] Run existing backend tests if feasible.
- [x] Confirm no shared enum changes are needed beyond already-existing `shuffle`, `see_the_future`, `play_shuffle`, and `play_see_the_future`.

Suggested commands:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_turn_service.py
PYTHONPATH=. .venv/bin/pytest tests/test_socket_room_session_flow.py
PYTHONPATH=. .venv/bin/pytest
```

## Out of scope

- `Favor`.
- Frontend UI changes.
- Persisting game state outside in-memory runtime.
- Client-side deck manipulation or client-side rule resolution.

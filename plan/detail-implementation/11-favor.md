## Goal
Implement the target-based hand transfer effect without leaking private card details.

## Scope
- Validate `favor` targets
- Transfer a random card from target to acting player
- Update both hands and hand counts
- Keep the transferred card hidden from the room

## Done when
- `favor` works against valid active targets only
- Public state reflects counts, not the actual transferred card
- Private state updates are correct for both affected players

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`

## Implementation checklist

### Decisions
- [ ] Treat a `favor` target as valid when the target exists, is not the acting player, is not `eliminated`, and has at least 1 card in hand.
- [ ] Allow `favor` against a disconnected target as long as the target is not eliminated.
- [ ] Return a target-required error when `targetPlayerId` is missing for `favor`.
- [ ] Return a target-empty-hand error when the target has no cards.
- [ ] Include actor and target in public recent action metadata, but never include the transferred card id or card type.
- [ ] Do not clear `visibleFutureCards` when resolving `favor`, because `favor` does not change draw pile order.

### Engine
- [ ] Add a `FAVOR_PLAYED` lifecycle outcome.
- [ ] Add explicit game errors for missing `favor` target and empty target hand.
- [ ] Add `TurnLifecycleService.play_favor(room_id, player_id, card_id, target_player_id, request_id=None)`.
- [ ] Reuse common active-turn and card validation for actor and `favor` card ownership.
- [ ] Validate target exists in public player summaries and private state.
- [ ] Reject self-target.
- [ ] Reject eliminated target.
- [ ] Reject target with empty private hand.
- [ ] Discard the acting player's `favor` card.
- [ ] Select one random target hand index through the service randomizer.
- [ ] Move the selected card from target hand to actor hand.
- [ ] Decrement target `hand_count` and increment actor `hand_count`.
- [ ] Keep `pendingDraws`, current player, turn number, and phase as `turn_action`.
- [ ] Update game state timestamp after mutation.

### Realtime handler
- [ ] Route `CardType.FAVOR` in `turn:play-card` instead of returning `unsupported_card_action`.
- [ ] Pass `payload.targetPlayerId` into `play_favor`.
- [ ] Import any new `favor` validation errors in the realtime server.
- [ ] Add new `favor` validation errors to `GAME_ERROR_CODES` so socket responses get stable error codes.
- [ ] Mark successful `favor` requests as processed for idempotency.
- [ ] Keep duplicate request behavior as snapshot-only with no second transfer.

### Public/private events
- [ ] Map `FAVOR_PLAYED` to `ActionType.PLAY_FAVOR`.
- [ ] Add a public summary such as `<actor> played Favor on <target>`.
- [ ] Update `summary_for_action` or add a `favor`-specific summary path so the target nickname can be included.
- [ ] Update `emit_action_result` to accept an optional `target_player_id`.
- [ ] Pass `targetPlayerId` into `RecentAction` for `favor`.
- [ ] Ensure `game:state` exposes only updated hand counts and discard top/count.
- [ ] Ensure `player:private-state` gives the actor their updated hand, including the received card.
- [ ] Ensure `player:private-state` gives the target their updated hand, without the transferred card.
- [ ] Ensure other players never receive the transferred card id or card type.

### Tests
- [ ] Unit test successful `favor` transfers a deterministic random target card.
- [ ] Unit test successful `favor` discards only the `favor` card, not the transferred card.
- [ ] Unit test hand counts update for actor and target.
- [ ] Unit test phase, current player, turn number, and pending draws stay unchanged.
- [ ] Unit test missing target is rejected.
- [ ] Unit test self-target is rejected.
- [ ] Unit test unknown target is rejected.
- [ ] Unit test eliminated target is rejected.
- [ ] Unit test disconnected target is allowed.
- [ ] Unit test empty target hand is rejected.
- [ ] Socket flow test successful `favor` emits public state and private states correctly.
- [ ] Socket flow test public recent action includes target but not transferred card details.
- [ ] Socket flow test missing target returns the agreed target-required error code.
- [ ] Socket flow test empty target hand returns the agreed target-empty-hand error code.
- [ ] Socket flow test duplicate request does not transfer a second card.
- [ ] Replace the existing unsupported `favor` socket test with the supported behavior.

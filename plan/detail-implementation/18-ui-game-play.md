## Goal
Implement the in-match UI needed to play a full multiplayer round in the browser.

## Scope
- Render current turn and pending draws
- Render player hand and playable actions
- Add draw-card control
- Render discard summary and public player state
- Render game log and eliminated state
- Render winner/result state

## Current state and implementation decisions
- `frontend/app/page.tsx` already has Home, Lobby, and the Game/Finished view boundaries. Game and Finished are placeholders to replace in this issue.
- `frontend/lib/socket/client.ts` already exposes authoritative room, public game, and private player state plus `playCard(cardId, targetPlayerId?)` and `drawCard()`. Reuse its provider and the synchronized public/private snapshot checks in `frontend/lib/socket/selectors.ts`.
- The current public payload contains only `recentAction`, not game-log history. A log that survives reload/reconnect requires bounded public action history in server snapshots and shared/backend contracts. Do not build the required log solely from browser-local events.
- The public discard payload has `discardTopCardType` and `discardCount`; render a summary from those fields, not an invented full discard pile. Render `visibleFutureCards` only from the current player's private payload.
- `Favor` requires a target player. `Defuse` and explosion resolution are automatic on the server; there is no manual Defuse control in this issue.
- Result display is in scope. Rematch action/state belongs to the later rematch flow and must not block completion of this issue.

## Decisions for this issue
- The public game log shows the latest 50 resolved actions, ordered by server sequence. Store it in room-scoped, in-memory game runtime and include it in every public game snapshot and reconnect/bootstrap snapshot. Reset it for a new match. Label the UI as recent actions so a longer match does not imply complete history.
- Record one log entry per successfully resolved start/play/draw request. A draw entry describes its final outcome, including automatic Defuse or elimination; do not create separate entries for intermediate phases. Use the resulting `stateVersion` as the stable entry ID. Keep `recentAction` equal to the newest entry for compatibility.
- Keep action submission pending until the server confirms that exact `requestId` and the client has applied a public/private snapshot pair at or above the confirmed `stateVersion`. Failed actions are cleared by a correlated `error` event. A timeout or lost connection has an unknown outcome: lock further actions, offer state restoration, and never automatically replay the request.
- During disconnect/restore, use the existing blocking Recovery view. Hide the game board and private hand until the session is ready and the current public/private pair is synchronized. An eliminated player with a ready session may still view the live board without action controls.
- Enable play and draw only in `phase === "turn_action"`. The backend remains authoritative for all other preconditions, including an empty draw pile.

## Implementation checklist

### 1. State selectors and action availability
- [x] Add pure selectors for the current player, local player, own turn, eliminated state, playable cards, valid Favor targets, and draw availability.
- [x] Require a connected socket, ready session, synchronized current public/private state, `in_game` room, `phase === "turn_action"`, and the local player's turn before enabling actions. Keep server validation authoritative.
- [x] Do not offer `exploding_kitten` or `defuse` as normal playable hand actions. Show why an action is unavailable without relying on color alone.
- [x] Allow one in-flight game action per tab. Match success to the submitted `requestId` and apply the paired snapshot at or above its confirmed `stateVersion` before releasing the pending state; clear a failed action only on its correlated error.

### 2. Game board and player information
- [x] Replace the Game placeholder with the current turn, turn number, `pendingDraws`, phase, and a clear indication of whose turn it is.
- [x] Render every public player with nickname, hand count, connection/elimination status, and a clear marker for the local player/current player.
- [x] Render the local private hand using `cardId` as the action identifier and `cardType` for the card label. Never render another player's private hand or hidden deck order.
- [x] Render discard top card and discard count from the public snapshot.
- [x] Show `visibleFutureCards` only to the local player when present, and update or clear them when a newer private snapshot arrives.
- [x] Keep the board readable but non-interactive for eliminated players with a ready session. During disconnect/restore, show the blocking Recovery view and hide the board/private hand until a synchronized bootstrap is applied.

### 3. Play and draw flows
- [x] Provide a play control for Skip, Attack, Shuffle, See the Future, and Favor cards that are currently available to the local player.
- [x] For Favor, let the player select an eligible living opponent with at least one card, review/cancel the choice, and send `targetPlayerId` with the selected `cardId`.
- [x] Add a draw control that sends `turn:draw-card` only when allowed; explain pending draws, turn ownership, and disabled states in the UI.
- [x] Reflect action results only after the authoritative public/private snapshot arrives, including Attack/Skip turn changes, Favor hand changes, automatic Defuse, explosion, and elimination.
- [x] Add a typed success acknowledgement for `turn:play-card` and `turn:draw-card` with `requestId` and resulting `stateVersion`; a duplicate request ID acknowledges without applying the action again, and failures keep correlated `error` events.
- [x] Return/expose the request ID and pending status through the frontend realtime client and consume the success acknowledgement.
- [x] On acknowledgement timeout or disconnect, show that the outcome is unknown and offer restore/reconciliation. Do not automatically resend the action or create a new request ID for an uncertain action.
- [x] Surface server action errors near the controls and allow a new valid action after the failed request is resolved. Do not optimistically change cards, turn ownership, or pending draws.

### 4. Public game log
- [x] Add `actionHistory` to the shared TypeScript contract and matching backend response model as the latest 50 public entries, ordered by `stateVersion`; include it in normal game state and reconnect/bootstrap snapshots.
- [x] Append one entry after each successful start/play/draw resolution and before broadcasting its state. Use `stateVersion` as the entry ID, retain `recentAction` as the latest entry, and reset history for a new match.
- [x] Keep private cards, deck order, and Favor's transferred card type out of public summaries. Render player names and final outcomes, label the list as the 50 most recent actions, and show a sensible empty state.

### 5. Elimination and result
- [x] Show elimination in the board/player list from authoritative public state, including the local player's read-only state.
- [x] Replace the Finished placeholder with winner nickname, local win/loss result, and final player statuses. Select the result from the synchronized finished game snapshot, not the notification event alone.
- [x] Keep the result correct after reload/reconnect and when `room:updated` / `game:state` arrive in either order.

### 6. UX and verification
- [x] Support mobile and desktop without horizontal overflow; use semantic controls, keyboard navigation, visible focus, and accessible status/error announcements.
- [x] Unit-test selector edge cases: wrong turn, disconnected/restoring, stale state pair, eliminated player, unplayable cards, invalid Favor targets, pending action, and finished match.
- [x] E2E-test a 3-player browser match from lobby through winner/result, including representative play/draw actions, action pending/error recovery, and the bounded log UI.
- [x] Cover every action type, Attack pending draws, automatic Defuse, elimination, and log outcomes with deterministic backend tests using a controlled deck/randomizer; do not make browser tests depend on random draws.
- [x] E2E-test reload/reconnect during a match and after finish; verify correct private hand, public log history, action lock while restoring, and no hidden-information leak to other players.
- [x] Test lost/delayed success acknowledgement, correlated action error, and restore after an unknown action outcome without a second action resolution. Backend duplicate/conflict and action-history tests are complete.
- [x] Run `npm test`, `npm run typecheck`, `npm run build`, and `npm run test:e2e` from `frontend/`; run relevant backend tests for the action-history contract change.

## Done when
- Players can use the browser UI to play a full match
- UI renders only from server state and private hand data
- Result state appears when the match ends
- Public game log and result remain correct after reload/reconnect
- Actions are locked for the wrong turn, eliminated player, or unsynchronized session

## Source docs
- `plan/implementation-plan.md`
- `plan/game-design.md`
- `plan/functional-spec.md`

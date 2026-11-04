## Goal

Give players a clear next step after a match: play another match with the same room or leave it.

## Context and dependencies

- `18-ui-game-play.md` already renders the authoritative result. Its scope explicitly defers rematch actions.
- The Finished view currently has no CTA. Shared contracts define rematch and leave-room requests; the backend handles rematch voting, while leave-room handling and the UI remain pending.
- `plan/functional-spec.md` requires a finished room to support rematch or leaving. `plan/implementation-plan.md` places rematch in Phase 5.
- Reuse the existing realtime client, room identity, view selector, and lobby screen. Do not create a second source of room state.

## Product decisions

- On the Finished screen, show **Play Again** as the primary CTA and **Leave Room** as the secondary CTA. Keep the result visible while players decide.
- **Play Again** means “I am ready for a rematch,” not “start immediately.” Show each player's rematch choice and the remaining wait clearly. Allow a player to withdraw their choice before the rematch transition.
- A rematch requires agreement from every current room member, including disconnected members while their seat is reserved. Once the first rematch vote is submitted, a disconnected member gets a 2-minute grace period to reconnect. On expiry, the server removes that member and revokes their session, then recalculates the vote. A new disconnect during voting starts its own 2-minute grace period. Reconnecting cancels that member's pending removal. Publish each pending removal deadline in the authoritative room snapshot and show the countdown and pending members on the Finished screen.
- If every rematch vote is withdrawn, cancel all pending removals caused by that voting round. The next first vote starts a new 2-minute grace period for members who are then disconnected. Before a timer removes anyone, recheck the room status, member connection, active votes, and deadline under the same mutation lock used for room changes.
- When all remaining members agree, reset the match and return the room to `waiting`, even if fewer than three remain. The room is joinable again at that point; the existing Lobby screen enforces 3–5 connected, ready players and host-only Start. Do not label a direct Finished → Lobby navigation as **Back to Lobby**: that transition requires the server's rematch decision.
- **Leave Room** removes the player from server room membership, clears only that room's saved identity after confirmation, and returns this tab to Home. It is not just a local redirect or socket disconnect. If the host leaves or times out, assign host to the earliest joined connected member; if none is connected, assign it to the earliest joined remaining member. Close the room when its last member leaves.
- Keep rematch and leave controls disabled while the session is disconnected, restoring, unsynchronized, or another post-game request is pending. Show a useful recovery action and never infer success solely from a button click.
- Treat a lost Leave Room acknowledgement as an unknown outcome. The server keeps a 10-minute terminal record keyed by `playerSessionId` and `requestId` after removing the session; post-game request IDs remain replayable for the same 10-minute window, independently of the shorter admission-request TTL. Reconnect with that session returns a distinct `room_left` result so the client can clear its identity. If reconnect succeeds, keep the leave request ID and offer an explicit retry with the same ID; the server must return the original result or perform the leave once. An `invalid_session` response also clears the unusable identity and returns Home. Do not create a new leave request ID while the original one can still be processed. After its 10-minute window expires, a successful restore proving continued room membership permits a new leave request.

- A Leave Room request includes `playerSessionId` and `requestId`. The server checks the terminal result record before requiring an active socket binding, so a duplicate can receive its original result after the session is removed. A request ID reused with different contents returns `request_conflict`. Persist the pending leave ID, its replay deadline, and the room identity together across reloads; clear them only after a confirmed leave, `room_left`, or `invalid_session`. Use server time to evaluate the replay deadline.

## Implementation checklist

### 1. Backend and shared contract

- [x] Define typed request/event contracts for rematch ready/withdraw and leave room, including request IDs and correlated success/error responses.
- [x] Accept rematch choices only from current members of a `finished` room. Make duplicate requests idempotent; reject stale or invalid requests without changing state.
- [x] Retain rematch request results for 10 minutes outside the game runtime, scoped to the player session and match. Replay the original result for the same ID and contents even after transition to `waiting`; return `request_conflict` if an ID is reused with different contents.
- [x] Include each member's rematch choice and any disconnect grace deadline in authoritative room state and in reconnect/bootstrap snapshots so the Finished screen survives reload and reconnect.
- [x] When a rematch vote or grace deadline changes the finished room's `stateVersion`, publish matching public game and per-player private snapshots at that version so the existing Finished selector stays synchronized. Let clients update the countdown locally from the server deadline; do not publish a snapshot every second.
- [ ] Count all current room members in the vote. After the first vote, schedule removal for disconnected members using the 2-minute grace period; cancel removal on reconnect. A leave or timeout updates the voting set and rechecks consensus atomically. Keep the room `finished` until the server commits the transition.
- [x] On transition to `waiting`, clear prior game runtime and rematch choices before publishing the room snapshot; reset readiness and elimination state, keep remaining memberships and sessions, and make reconnect/bootstrap return null game/private state. The next match must get fresh private/public game state and action history.
- [ ] Implement leave-room lifecycle for finished rooms. Notify remaining members, transfer host by the stated join-order rule, and close/retire an empty room. Remove the departed member's active socket binding and prevent that session from restoring as a room member.
- [ ] Keep a 10-minute leave-result record so duplicate requests with the same session and request ID return the same terminal result after session removal. Return `room_left` when that session reconnects during the retention window; distinguish this from a still-valid session and from `invalid_session` after expiry or server restart.
- [x] Reopen joining once the rematch returns the room to `waiting`. Keep the existing 3–5 player Start precondition and add tests for a rematch room with fewer than three members.

### 2. Realtime client and UI

- [ ] Expose rematch ready/withdraw and leave methods from the existing realtime client. Correlate replies with request IDs and reconcile with authoritative room snapshots; protect against duplicate submissions and unknown outcomes after timeout/disconnect.
- [ ] Add the Finished-screen CTAs and per-player rematch status. Explain who is still pending, including disconnected members and their grace-period countdown. Show pending, success, error, and restore states accessibly.
- [ ] Keep the Finished result on screen until an authoritative `waiting` room snapshot arrives. Then select Lobby without exposing stale finished-game data or letting old action controls reappear.
- [ ] After a leave acknowledgement or `room_left` reconnect result, clear the saved room identity and snapshots and show Home. If the session is `invalid_session`, clear the unusable identity and show Home. On a timeout or lost acknowledgement, restore first; if the session remains valid, offer an explicit same-ID retry while the request is replayable and keep other actions locked until resolved. Once the replay window expires, allow a new request only after a successful restore confirms continued membership.
- [ ] Support mobile layout, keyboard access, visible focus, and status announcements for the new controls.

### 3. Verification

- [ ] Test a multiplayer rematch from Finished through voting, Lobby, Ready, and a new match; verify old cards, winner, and action history do not carry over.
- [ ] Test withdraw, duplicate requests, reload/reconnect during voting, disconnected-member grace expiry/cancellation, and rematch/leave races.
- [x] Test withdrawal of the final vote cancels pending removals, a later first vote restarts grace periods, and stale timer callbacks cannot remove reconnected members.
- [ ] Test leaving as a regular player and as host, including deterministic host transfer, the final member leaving, room cleanup, identity cleanup, and the remaining players' view. Verify that a rematch room with fewer than three players accepts new joins but cannot start early.
- [ ] Test delayed/lost acknowledgements and correlated errors: `room_left` after a committed leave, restore and same-ID retry after an uncommitted leave, result-record expiry, and server restart, without duplicate room transitions or accidental loss of a valid session.
- [ ] Test rematch request replay after transition to `waiting`, request ID conflicts, and leave retry after reload using the persisted request ID and deadline.
- [ ] Run relevant backend and frontend tests, typecheck, build, and browser E2E checks for the changed flows.

## Done when

- A player can choose **Play Again** or **Leave Room** from the Finished screen.
- Rematch state is authoritative, survives restore, and takes consenting players back to Lobby for a clean next match.
- Leaving removes membership and returns the player to Home after a leave acknowledgement, a `room_left` reconnect result, or confirmation that the saved session is invalid.
- Pending, failed, disconnected, and raced actions have clear, recoverable UI states, including a lost Leave Room acknowledgement.

## Source docs

- `plan/detail-implementation/18-ui-game-play.md`
- `plan/functional-spec.md`
- `plan/implementation-plan.md`

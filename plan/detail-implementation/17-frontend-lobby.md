## Goal

Build the user-facing Home and Lobby flow so players can create or join a room, manage readiness, and transition into a match.

## Dependencies

- `16-frontend-socket-client.md` is complete.
- Reuse the existing realtime provider/hooks and shared contracts.
- Do not create another socket connection or a second authoritative room state.

## Design artifact

- `plan/detail-implementation/17-frontend-lobby-ui-design.md`

## Implementation decisions

- Use one application route for the MVP and select the Home, Lobby, or Game boundary from realtime state.
- Room, player, and game state remain authoritative in the realtime provider.
- Components may keep ephemeral UI state such as form values and pending button state.
- Unit-test pure view/eligibility helpers; verify rendered flows with Playwright. Do not add a separate component-test framework.

## Scope

### UI

- Replace the realtime development screen with polished MVP Home and Lobby views.
- Support desktop and mobile layouts.
- Provide clear loading, disabled, error, host, connection, and readiness states.
- Provide semantic forms, keyboard navigation, visible focus, accessible labels, and live status/error announcements.
- Deep visual polish and animation are not required.

### Home

- Provide Create Room and Join Room forms.
- Require a non-empty nickname; joining also requires a room code.
- Trim inputs before submission. Room-code normalization remains in the realtime client.
- Disable admission actions while a request is pending.
- Show actionable validation, admission, timeout, and unknown-outcome errors.
- Support retrying or discarding a pending admission through the existing client API.
- Enter Lobby only after receiving a valid identity and authoritative room snapshot.

### Lobby

- Render the room code, room status, player count, player list, host, current player, connection status, and readiness from `state.room` and `state.identity`.
- Update from `room:updated` without optimistic room-state mutations.
- Preserve the last lobby snapshot during transient connection loss when the client retains it, but disable actions until synchronization completes.
- Show a blocking recovery view for invalid, replaced, or unavailable sessions instead of stale lobby data.

### Ready and start controls

- Allow Ready/Unready only when the connection and session are ready, synchronization is complete, and the room is `waiting`.
- Disable repeated readiness submission until a newer room snapshot or an error is received.
- Only the host can submit `game:start`.
- Start is eligible only when:
  - The room is `waiting`.
  - There are 3-5 players.
  - Every player is ready.
  - Every player is connected.
  - The current session is ready and synchronized.
- Explain unmet start conditions to the host; eligible non-hosts see a waiting-for-host message.
- Lock lobby actions immediately after submitting Start until authoritative game state or an error arrives.
- Treat backend validation as authoritative.

### Match boundary

- Enter the Game boundary only when the room is `in_game`, the session is ready, synchronization is complete, and matching public/private game snapshots exist.
- Show a loading boundary while the room is `in_game` but game snapshots are still synchronizing.
- Restore an active match directly into the Game boundary.
- Provide only a temporary Game placeholder; playable game UI belongs to the next issue.

### Connection and session recovery

- Show connecting, reconnecting, restoring, restore-failed, replaced/session-in-use, and degraded-storage states.
- Provide retry restore and explicit takeover actions through the existing client API.
- Never show private or room data from another session.

## UI design checklist

- [ ] Define and document the Home, Lobby, Recovery, Game-loading, and Game-boundary view hierarchy in `17-frontend-lobby-ui-design.md`.
- [ ] Map the create, join, ready, start, reconnect, restore, and takeover user flows.
- [ ] Create low-fidelity wireframes for Home, Lobby, and Session Recovery.
- [ ] Design mobile and desktop layouts.
- [ ] Define the component inventory and UI states.
- [ ] Define basic visual tokens for color, typography, spacing, radius, and status badges.
- [ ] Design default, focus, disabled, loading, success, and error states for controls.
- [ ] Verify that every realtime and session state has a corresponding UI state.
- [ ] Review keyboard navigation, focus order, announcements, contrast, and non-color status indicators.
- [ ] Approve the wireframes and state matrix before implementation begins.

## Implementation checklist

### 1. View selection and shared states

- [ ] Replace the development screen with Home, Lobby, and Game-boundary views.
- [ ] Add pure selectors for active view, action availability, and start eligibility.
- [ ] Handle connection, restore, invalid-session, replaced-session, takeover, and degraded-storage states.
- [ ] Map backend error codes to concise user-facing messages.
- [ ] Add accessible live status/error announcements.

### 2. Home

- [ ] Build accessible Create Room and Join Room forms.
- [ ] Validate and trim required inputs.
- [ ] Implement pending, retry, discard, timeout, and admission-error states.
- [ ] Open Lobby only after identity and room bootstrap are ready.

### 3. Lobby

- [ ] Render room metadata and players from authoritative state.
- [ ] Mark the host, current player, readiness, and connection status.
- [ ] Handle missing snapshots and transient disconnection safely.
- [ ] Keep authoritative room data out of component-local state.

### 4. Ready and start actions

- [ ] Implement Ready/Unready with repeated-submission protection.
- [ ] Implement host-only Start with player-count, readiness, and connection checks.
- [ ] Explain why Start is unavailable.
- [ ] Lock actions while Start is pending and release them on authoritative success or error.

### 5. Match boundary

- [ ] Wait for synchronized public/private game snapshots before entering Game.
- [ ] Show a synchronization/loading boundary when required.
- [ ] Restore active games directly into the Game placeholder.

### 6. Responsive and accessible UI

- [ ] Verify desktop and mobile layouts without horizontal overflow.
- [ ] Provide keyboard operation and visible focus, disabled, loading, and error states.
- [ ] Do not use color as the only host/readiness indicator.
- [ ] Check basic text and control contrast.

### 7. Tests

- [ ] Unit-test pure view and eligibility selectors.
- [ ] E2E: create a room and join from two additional browser contexts.
- [ ] E2E: synchronize membership and readiness across all clients.
- [ ] E2E: block non-host, not-ready, disconnected-player, and fewer-than-three start cases.
- [ ] E2E: start as host and transition every client to Game.
- [ ] E2E: reload and reconnect into the correct Lobby or Game view.
- [ ] E2E: cover restore failure and explicit session takeover.

## Out of scope

- Playable game-board, cards, game actions, results, and rematch UI.
- Finished-room restore UI beyond a temporary boundary.
- Leaving rooms, kicking players, and transferring host ownership.
- Public room links, invitation sharing, lobby chat, and spectator mode.
- Sounds, notifications, and animation polish.
- Backend rules, socket contracts, or a second state-management implementation.
- A new component-testing framework.

## Done when

- Players can create or join a room and see synchronized lobby membership and readiness.
- Only an eligible host can start; disconnected or unready players block Start with a clear explanation.
- Lobby actions remain safe during pending, disconnected, restoring, and replaced-session states.
- All clients enter Game only after synchronized authoritative game snapshots are available.
- Reload restores the same player into the correct Lobby or Game boundary without duplication.
- Home and Lobby are usable on desktop, mobile, keyboard, and assistive-technology basics.

## Verification gates

- `npm test` passes.
- `npm run test:e2e` passes.
- `npm run typecheck` passes.
- `npm run build` passes.

## Source docs

- `plan/implementation-plan.md`
- `plan/functional-spec.md`
- `plan/detail-implementation/16-frontend-socket-client.md`

# Frontend Lobby UI Design

**Status:** Draft

This document is the UI/UX design artifact for `17-frontend-lobby.md`. The backend and realtime provider remain authoritative for room, player, session, and game state.

## View hierarchy

```text
Room flow
├── Home
├── Session recovery
│   ├── Restoring
│   ├── Restore failed
│   └── Session replaced / takeover
├── Lobby
├── Game loading
├── Game boundary
└── Finished boundary
```

The MVP uses one application route. A pure selector chooses the active view from realtime state.

## State-to-view matrix

Evaluation follows the order below so recovery states take precedence over retained room data.

| Priority | Realtime condition | View |
| --- | --- | --- |
| 1 | Session is `replaced` | Session replaced / takeover |
| 2 | Session is `restore_failed` | Restore failed |
| 3 | Identity exists and session is `none` or `restoring` | Restoring |
| 4 | Identity is absent, or session is `invalid` | Home |
| 5 | Session is `joining` or `join_failed` | Home with admission state |
| 6 | Session is ready and room is `waiting` | Lobby |
| 7 | Room is `in_game`, but synchronization or snapshots are incomplete | Game loading |
| 8 | Room is `in_game`, synchronization is complete, and public/private snapshots match | Game boundary |
| 9 | Room or game is `finished` | Finished boundary |
| 10 | State is incomplete or unsupported | Safe recovery/loading state |

Matching game snapshots means both snapshots exist, belong to the current identity/room, and have the same `stateVersion`.

## User flows

```text
Home → Create room → Lobby
Home → Join room → Lobby
Lobby → Ready/Unready → Updated lobby snapshot
Lobby host → Start → Game loading → Game boundary
Reload → Restore → Lobby or Game boundary
Restore failed → Retry restore
Session replaced → Explicit takeover → Restore
Invalid session → Home with an explanatory message
```

Admission failures remain on Home and provide an error plus retry/discard actions where supported.

## Home wireframe

```text
┌──────────────────────────────────────────┐
│ Exploding Kittens Lite     Connection ●  │
│                                          │
│ Play with friends                       │
│ Nickname                                │
│ [                                      ] │
│                                          │
│ [ Create room ]                         │
│                                          │
│ ─────────────── or ───────────────────  │
│ Room code                               │
│ [                                      ] │
│ [ Join room   ]                         │
│                                          │
│ Status, validation, or recovery panel   │
└──────────────────────────────────────────┘
```

- Nickname is shared by Create and Join.
- The primary action is clear for the selected form context.
- Pending admission locks both admission actions.
- Errors appear next to the affected flow and are announced through a live region.

## Lobby wireframe

```text
┌──────────────────────────────────────────┐
│ Room ABCD12                 Connected ●  │
│ 3 / 5 players                            │
│                                          │
│ ★ Host (You)          Ready       Online │
│   Player 2            Ready       Online │
│   Player 3            Not ready   Online │
│                                          │
│ Waiting for every player to be ready.    │
│                                          │
│ [ Ready / Unready ]       [ Start game ] │
└──────────────────────────────────────────┘
```

- Only the host sees the Start action.
- Non-hosts see a waiting-for-host message when the room is eligible.
- Host, current-player, ready, and connection states use text or icons in addition to color.
- When Start is pending, all lobby actions are disabled until authoritative success or error.

## Session recovery wireframe

```text
┌──────────────────────────────────────────┐
│ Session recovery                        │
│                                          │
│ This player session is active elsewhere.│
│ Continuing here will replace that tab.  │
│                                          │
│ [ Continue in this tab ]  [ Retry ]      │
└──────────────────────────────────────────┘
```

Messages and available actions vary for restoring, restore failure, invalid session, and replaced session. Stale lobby or private data is never rendered behind this view.

## Game loading and boundaries

- Game loading shows a non-interactive synchronization state.
- Game boundary appears only after matching public/private snapshots are ready.
- Game boundary is a placeholder until the game-board issue is implemented.
- Finished boundary is a placeholder until the result/rematch issue is implemented.

## Responsive behavior

- Desktop: center content in a constrained panel; player status may use columns.
- Mobile: use a single column, full-width form controls/actions, and stacked player metadata.
- Keep room code, status messages, and actions visible without horizontal scrolling.
- Content order and selector behavior remain identical across breakpoints.

## Component inventory

- `RoomFlow`: selects the active view.
- `ConnectionStatus`: shows connection health without controlling navigation.
- `HomeView`: owns admission form values and submission UI state.
- `AdmissionRecovery`: renders retry/discard states.
- `LobbyView`: renders the authoritative room snapshot.
- `PlayerList` and `PlayerRow`: render identity, host, readiness, and connection status.
- `ReadyControl`: submits ready/unready intent.
- `StartControl`: explains eligibility and submits start intent.
- `SessionRecovery`: handles retry restore and explicit takeover.
- `GameLoading`, `GameBoundary`, and `FinishedBoundary`: transition placeholders.
- `StatusMessage`: shared accessible status/error region.

## UI state inventory

- Controls: default, hover, focus, disabled, pending, and error.
- Admission: idle, joining, unknown outcome, retryable failure, and terminal failure.
- Session: none, restoring, restore failed, ready, invalid, and replaced.
- Lobby actions: available, unavailable with reason, and pending.
- Connection: connecting, connected, reconnecting, and disconnected.

## Visual tokens

Use a small page-level foundation rather than introducing a full design system:

- Semantic colors for surface, text, primary action, success, warning, error, and offline state.
- Consistent type scale for page title, section title, body, label, and helper text.
- Spacing scale based on a small set of reusable values.
- Shared input/button height, border radius, border, and focus ring.
- Reusable badges for Host, You, Ready, Not ready, and Offline.

Exact token values are selected during implementation and must satisfy basic contrast requirements.

## Accessibility notes

- Associate every input with a visible label.
- Support Enter submission and keyboard-only operation.
- Keep focus visible and move it only when a view transition requires it.
- Announce connection, admission, session, and action errors with an appropriate live region.
- Do not use color as the only status indicator.
- Use semantic headings, forms, lists, buttons, and status regions.

## Open questions

- Visual theme and branding direction are not specified; default to a clean, playful MVP using the existing project foundation.
- Final Game and Finished views are intentionally deferred to their respective issues.

## Approval checklist

- [ ] View hierarchy and selector priority approved.
- [ ] Home, Lobby, and Recovery wireframes approved.
- [ ] Mobile and desktop behavior approved.
- [ ] Component and UI-state inventories approved.
- [ ] Visual direction and accessibility expectations approved.

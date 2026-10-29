# Frontend Lobby UI Design

**Status:** Draft

This document is the UI/UX design artifact for `17-frontend-lobby.md`. The backend and realtime provider remain authoritative for room, player, session, and game state.

## View hierarchy

```text
Room flow
├── Home
├── Session recovery
│   ├── Saved-session / pending-admission conflict
│   ├── Restoring
│   ├── Restore failed
│   └── Session replaced / takeover
├── Lobby
├── Game loading
├── Game boundary
└── Finished boundary
```

The MVP uses one application route. A pure selector chooses the active view from realtime state. Connection and storage warnings, plus action errors, are messages within the selected view; they do not select a different view by themselves.

## State-to-view matrix

Evaluate the rows in order. A usable room snapshot belongs to `identity.roomId` and contains `identity.playerId`. A usable game pair has both public and private snapshots, belongs to the current room/player, and has the same `stateVersion`. A current game pair must also have `stateVersion >= room.stateVersion`; the room snapshot may be older because game actions do not always emit a room update. Never select a room or game view from snapshots that fail these checks.

| Priority | Realtime condition | View |
| --- | --- | --- |
| 1 | Session is `replaced` | Session replaced / takeover |
| 2 | Session is `invalid` | Home with invalid-session explanation |
| 3 | Identity exists and (`pendingAdmission` is true or session is `joining`/`join_failed`) | Blocking saved-session / pending-admission conflict; no room/private data or admission actions |
| 4 | No identity, and `pendingAdmission` is true or session is `joining`/`join_failed` | Home with admission pending, retry, or discard state |
| 5 | No identity | Home |
| 6 | Identity and usable waiting-room snapshot exist, connection is `disconnected` or `reconnecting`, and session is `restore_failed` | Read-only Lobby with reconnect/retry message |
| 7 | Identity exists and session is `none` or `restoring` | Restoring; do not show retained room/private data |
| 8 | Session is `restore_failed` | Restore failed; do not show retained room/private data |
| 9 | Session is `ready`, but the room snapshot is missing or unusable | Safe recovery/loading state; no room/private data |
| 10 | Session is `ready` and room is `waiting` | Lobby; disable actions unless connected and synchronized |
| 11 | Session is `ready`, room is `in_game` or `finished`, and (`syncing` is true, the current game pair is unavailable, or room is `finished` while game phase is not `finished`) | Game loading / finishing synchronization |
| 12 | Session is `ready`, room is `in_game` or `finished`, the current game pair is available, and game phase is `finished` | Finished boundary |
| 13 | Session is `ready`, room is `in_game`, the current game pair is available, and game phase is active | Game boundary |
| 14 | State is inconsistent or unsupported | Safe recovery/loading state; no room/private data |

The read-only Lobby in row 6 uses only the retained waiting-room snapshot. It exposes no actions, never renders private game data, and offers retry restore while offline. Once reconnect/restore begins, row 7 takes over until an authoritative bootstrap succeeds. A failed restore while connected uses row 8. `syncing` may also be true while a waiting-room snapshot remains visible; row 10 keeps the Lobby visible but disables Ready and Start.

`pendingAdmission` takes precedence over the generic no-identity Home row because Create/Join normally run without an identity. Row 3 can occur when saved identity and a pending admission coexist after reload or cross-tab storage changes. Explain that the pending request may have succeeded even if its acknowledgement was lost. Offer one explicit action, **Continue saved session**: abandon the pending admission, clear its local record, then restore the saved identity through the existing reconnect flow. This action needs a client API that can resolve the conflict atomically; `discardAdmission()` currently refuses to run while identity exists, and automatic restore currently waits while a pending admission exists. Keep this view blocking until the action completes. If restore fails, use row 8; never reveal retained room/private data during the conflict. An abandoned unknown admission may leave a disconnected seat on the server, so explain that consequence before the action. Do not silently clear either record or create another admission.

For rows 11-13, a newer room snapshot must not be paired with an older game pair. A finished room with an active or missing game pair remains in finishing synchronization until a current finished pair arrives. A finished game pair can select Finished while the room snapshot still says `in_game`, because the game pair is authoritative for the phase. Action errors and `storageDegraded` do not change the selected view: show them as accessible messages in the current view.

## User flows

```text
Home → Create room → Lobby
Home → Join room → Lobby
Lobby → Ready/Unready → Updated lobby snapshot
Lobby host → Start → Game loading → Game boundary
Reload → Restore → Lobby or Game boundary
Restore failed → Retry restore
Saved-session / pending-admission conflict → Continue saved session → Restore
Session replaced → Explicit takeover → Restore
Invalid session → Home with an explanatory message
```

Admission failures remain on Home and provide an error plus retry/discard actions where supported.

## Home wireframe

```text
┌──────────────────────────────────────────┐
│ Exploding Kittens Lite   Kết nối: ...    │
│                                          │
│ Chơi cùng bạn bè                         │
│ Tạo phòng mới hoặc nhập mã để tham gia.  │
│                                          │
│ Chọn cách tham gia                       │
│ (●) Tạo phòng    ( ) Vào phòng           │
│ Nickname                                 │
│ [                                      ] │
│ [ Create room ]                          │
│                                          │
│ Trạng thái, lỗi hoặc hành động khôi phục │
└──────────────────────────────────────────┘
```

When **Vào phòng** is selected, the Room code input appears between Nickname and the submit button, which changes to **Join room**. The nickname is shared by both choices. Pending admission locks the choices and submit button; the pending message offers retry or discard when applicable. Field errors appear below their inputs and are announced.

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
│ Kết nối: ...                             │
│                                          │
│ Phiên đang hoạt động ở tab khác          │
│ Tiếp tục tại tab này sẽ thay thế tab cũ. │
│                                          │
│ [ Tiếp tục ở tab này ]                   │
└──────────────────────────────────────────┘
```

The title, message, and action vary for restoring, restore failure, replaced session, and saved-session / pending-admission conflict. The conflict view offers **Tiếp tục phiên đã lưu**; restore failure offers **Thử khôi phục lại**. Stale lobby or private data is never rendered behind a blocking recovery view.

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

## Control states and realtime coverage

| Control | Default and success | Focus and disabled | Loading and error |
| --- | --- | --- | --- |
| Create / Join | Submit the selected form; success opens Lobby from a validated bootstrap. | Visible focus ring; unavailable while disconnected or admission is pending. | Pending request keeps Home visible with an explanation and retry/discard actions. Validation focuses the affected input; server errors use an alert. |
| Ready / Unready | Label reflects the current room snapshot; success appears in every player's row. | Visible focus ring; unavailable while offline, synchronizing, or another lobby action is pending. | Pending update locks repeat submission and explains the wait; server error releases the lock and appears in an alert. |
| Start game | Host sees Start; success moves through Game loading to Game. | Visible focus ring; non-host has no Start control; unmet conditions disable it with text reasons. | Pending start locks lobby actions; a backend error releases them and appears in an alert. |
| Retry / takeover | Retry repeats a recoverable request; takeover explicitly moves session ownership. | Visible focus ring; unavailable while the required client or connection is absent. | Recovery view explains the wait or failure; room/private data stays hidden until bootstrap succeeds. |

| Realtime or session state | UI representation |
| --- | --- |
| Connecting, disconnected, reconnecting | Header connection status; disconnected waiting room is read-only with retry action. |
| No identity, joining, join failed | Home with selected form, pending explanation, retry/discard, and error alert where relevant. |
| Invalid saved identity | Home with an invalid-session explanation and a fresh admission form. |
| Saved identity plus pending admission | Blocking conflict view with an explicit Continue saved session action. |
| Restoring, restore failed, replaced | Recovery heading and status; retry or explicit takeover when applicable. |
| Ready waiting room, including syncing | Lobby from room snapshot; syncing and pending actions disable controls. |
| Ready in-game or finished room without a current game pair | Game loading with synchronization status. |
| Ready game pair, current finished pair | Game or Finished boundary respectively. |
| Unusable room snapshot or unsupported state | Safe recovery view with retry; no stale room or private data. |
| Action error, connection error, degraded storage | Alert or status message in the selected view. |

## Accessibility review

- Tab order follows the visible controls: admission mode, nickname, room code when joining, submit; Lobby Ready then Start for the host; Recovery action. Enter submits Home. Validation focuses the first invalid field. A view change focuses its heading so keyboard users do not remain on a removed control.
- Inputs have visible labels and field errors have `aria-describedby` plus alert semantics. Connection, synchronization, recovery, and storage messages use status regions; action errors use alerts.
- Focus rings are visible. Disabled actions have text explanations. Host, readiness, and connection use explicit words, so color is not the only signal.
- Browser checks cover no horizontal overflow at 320, 375, and 1280 px and at least 4.5:1 contrast for representative heading, helper text, badges, and enabled button text. The current wireframe is an MVP; no full accessibility audit is claimed.

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

# Frontend realtime layer

Next.js + TypeScript, with shared wire contracts in `../shared/contracts/`.
The root page is a development smoke-test harness, not the lobby/game product UI.

## Run in development

Requirements: Docker Compose. The repository Compose stack runs the frontend,
backend and PostgreSQL together. The frontend source is bind-mounted, so Next.js
hot reload still works normally.

From the repository root, create the backend environment file once and start
the shared services:

```sh
cp backend/.env.example backend/.env
docker compose up --build
```

Open `http://localhost:3000`. Backend CORS defaults to this origin; using another
origin requires `APP_CORS_ORIGINS='["http://your-origin"]'` on the backend.
`NEXT_PUBLIC_SOCKET_PATH` must match `APP_SOCKET_IO_PATH` (default `/socket.io`).
Public environment values are captured at build time. Restore timeout defaults to
10 seconds and is configurable with `NEXT_PUBLIC_SOCKET_TIMEOUT_MS`.

Stop the shared services with `docker compose down` from the repository root.
`NEXT_PUBLIC_SOCKET_URL` is set to `http://localhost:8000` by Compose: this URL
is used by the browser, which cannot resolve Docker's internal `backend` hostname.
For a fully host-based backend setup, see [backend/README.md](../backend/README.md).

The lockfile is committed. `--legacy-peer-deps` avoids an npm 10 peer-resolution
crash involving optional Vitest browser tooling; test execution uses Node Vitest
and separate Playwright tests. No browser Vitest plugin is needed.

## Component API

`SocketProvider` owns one browser client per tab. `useRealtime()` returns
`{ state, client }`; the client is null during SSR/initial hydration.

- `client.createRoom(nickname)`, `joinRoom(roomCode, nickname)`
- `ready(boolean)`, `startGame()`, `drawCard()`, `playCard(cardId, targetPlayerId?)`
- `retryRestore()`, `takeOver()` (explicit user action)
- `retryAdmission()`, `discardAdmission()` (explicit recovery of an unknown request)

Read `state.connection`, `session`, `syncing`, `room`, `game`, `private`, `error`,
`connectionError`, `outcome` and `storageDegraded`. Never mutate snapshots.
Game intents are refused while disconnected/restoring/synchronizing. They are not
queued or automatically retried. Rules and turn ownership are checked by the server.
Listeners are registered before connect and detached by reference on disposal.
React Strict Mode reuses the client across its immediate effect remount.

## Session and ownership

Identity is stored under `boardgame.identity.v1` in localStorage. Only the session
token authenticates reconnect; player/room IDs are display metadata. No hand or
bootstrap snapshot is persisted. Instance and pending admission are stored in
sessionStorage. Storage failures fall back to memory, with a visible reload warning.

A new tab/instance never takes over automatically. It receives `session_in_use`
and stops automatic restoration. “Tiếp tục ở tab này” rotates the tab's instance ID
and sends explicit takeover. This also separates duplicated tabs that copied
sessionStorage. The backend changes ownership before notifying/disconnecting the
old socket. Offline old owners are rejected on return, even if they missed the
notification. Reloading the active tab retains its instance; if its previous socket
has not been detected as disconnected yet, explicit takeover is required.

## Bootstrap and ordering

Reconnect requests carry `attemptId`; errors correlate via `requestId = attemptId`.
The success ack contains identity, room, public game, private game and `stateVersion`.
Waiting rooms have null game/private snapshots. Finished games still return both.
The client ignores callbacks from expired attempts or previous connections.

The backend serializes socket mutations and snapshot creation through one gateway
transaction lock for this single-process MVP. This deliberately serializes different
rooms too; split it into room locks plus an admission lock before scaling throughput.
Existing engine room locks are retained. All live data remains process-local.

Versions increase per room mutation. Room snapshots can advance independently of
game snapshots. Public/private game events share a version and are committed together,
regardless of arrival order. During restore, live updates are buffered, bootstrap is
applied, then newer matching pairs are applied. Older versions cannot overwrite newer
state. Notification events (turn started, game ended, etc.) do not independently
mutate authoritative snapshots.

## Admission retries

Create/join use a request ID formatted as `serverEpoch:issuedAtMs:UUID` and include
`clientInstanceId`. Epoch, server time and TTL are supplied by `system:connected`;
the client estimates current server time from that handshake, avoiding client clock
offset. IDs and payloads are persisted before sending. A timeout has an unknown
outcome, not proof of failure. Retry uses the same ID and payload.

The backend retains successful identity results for **120 seconds**, with at most
**1,000 live entries**. It rejects admission when full rather than evicting a valid
result. Conflicting reuse is rejected; expired timestamps are rejected even after
cache cleanup. Requests from a previous backend epoch get `server_restarted`.
The cache does not survive restart, nor do rooms/sessions. The retry guarantee is
limited to the TTL and backend process lifetime.

A replay returns current state, not a cached room snapshot. If another socket owns
the recovered session, its ack has `requiresTakeover: true`: the client saves the
recovered identity but locks actions until the user explicitly takes over.
Discarding an unknown pending request closes that socket and permits a new request;
it does not delete a room or seat that may already have been created.

Existing backend-only clients may temporarily omit both admission ID/instance
fields and receive their original identity-only ack. Legacy sessions retain their
old event bootstrap. They do not get admission replay guarantees. Modern sessions
cannot bypass ownership by omitting the new reconnect fields.

## Verification

```sh
# Repository root
backend/.venv/bin/python -m pytest backend/tests -q

# frontend/
npm test
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright starts a backend on 8000 and a production frontend on 3000; keep those
ports free. Set `BACKEND_PYTHON` to an absolute Python path if using another venv.
Set `PLAYWRIGHT_BROWSERS_PATH` if browser binaries live outside the default cache.

Browser scenarios: create/join with three isolated player contexts, lobby reload,
game reload/private-hand recovery, explicit takeover, offline old-owner rejection,
invalid persisted session recovery, and a dropped create ack recovered after reload
with the same request ID. Unit tests exercise loss of ack, retry,
late callbacks, equal-version pairing, stale snapshots, offline action blocking,
storage fallback and listener cleanup. Backend tests cover concurrent admission,
TTL/process restart, capacity, ownership and bootstrap/action serialization.

Reference documentation: [Socket.IO offline behavior](https://socket.io/docs/v4/client-offline-behavior/),
[client options](https://socket.io/docs/v4/client-options/), and
[Next.js installation](https://nextjs.org/docs/app/getting-started/installation).

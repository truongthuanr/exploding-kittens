# Validation — 2026-09-22

- Backend regression and new realtime tests: **175 passed**.
- Frontend lifecycle/storage unit tests: **16 passed**.
- TypeScript typecheck: **passed**.
- Next.js production build: **passed**.
- Playwright against actual FastAPI/Socket.IO and production Next.js: **5 passed**.

Browser coverage:

1. Three isolated players create/join; lobby reload preserves identity; game reload
   restores the same private hand; public payload excludes card IDs.
2. A second tab requires explicit takeover; the old online tab locks actions and
   leaves shared identity storage intact.
3. An offline old owner cannot reclaim a session after another instance takes over.
4. Invalid persisted session clears identity and permits a new admission.
5. A real Socket.IO create ack is dropped by the browser's WebSocket route; timeout,
   reload and retry preserve request ID and recover a single seat.

Backend tests additionally cover concurrent create/replay/takeover, request conflict,
expiry, previous process epoch, capacity, versioned bootstrap concurrent with actions,
legacy session compatibility and hidden-information filtering. Client unit tests
cover stale callbacks/errors, out-of-order public/private payloads, offline actions,
listener ownership and storage failures.

Commands are documented in README.md. This environment used a Python venv at
`/tmp/boardgame-venv`, Playwright browsers at `/tmp/boardgame-browsers`, and unpacked
browser runtime libraries at `/tmp/boardgame-libs/usr/lib64`. These are machine-local
verification dependencies, not repository artifacts. The offline scenario waits
for the default Socket.IO heartbeat timeout; the suite takes about one minute.

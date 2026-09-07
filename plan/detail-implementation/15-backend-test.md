## Goal
Cover the backend core before UI work depends on it.

## Scope
- Unit tests for deck setup and turn flow
- Unit tests for `skip`, `attack`, `shuffle`, `see_the_future`, `favor`
- Tests for explosion, defuse, elimination, and end-game behavior
- Service tests for room/session lifecycle

## Done when
- Engine and room/session tests pass locally
- The documented core rules are covered by automated tests

## Source docs
- `plan/implementation-plan.md`
- `plan/game-engine-spec.md`
- `plan/functional-spec.md`

## Implementation checklist

### 1. Baseline and scope boundaries

- [x] Run the existing test suite: `cd backend && .venv/bin/python -m pytest -q` — 131 tests passed at the time of review.
- [x] Map `rule/scenario → test file::test name` for the engine and room/session core; explicitly identify untested items and items covered by other issues.
- [x] Limit lifecycle coverage in this issue to room create/join/ready/start and session create/bind/unbind/rebind. Record room leave/close, session expiry, and rematch as deferred follow-up work in the coverage map.
- [x] Retain existing handler tests for public/private payloads and duplicate requests; actual Socket.IO transport and concurrent requests belong to realtime integration/hardening.

### 2. Deck setup — `backend/tests/test_game_setup.py`

- [x] Verify that the bomb count equals `playerCount - 1` and that the draw pile has the expected size for 3, 4, and 5 players.
- [x] Verify five-card starting hands containing Defuse and no bombs, along with a valid initial state.
- [x] Extend starting-hand and initial-state assertions to all supported player counts: 3, 4, and 5.
- [x] Verify rejection of unsupported player counts, including 0, 2, and 6.
- [x] Verify the total card composition across all hands and the draw pile against the specification, with no duplicate `card_id` values.
- [x] Verify that the current player occupies the first seat; select the first seat independently of the host (regression fixed).

### 3. Turn flow and action cards — `backend/tests/test_turn_service.py`

- [x] Normal draw: add the correct card, reduce pending draws, and correctly retain or advance the turn.
- [x] Skip removes one pending draw; Attack transfers `pendingDraws + 1` and supports stacking.
- [x] Cover the effects and basic edge cases of Shuffle, See the Future, and Favor.
- [x] Reject invalid requests without mutating state; skip eliminated players when advancing turns.
- [x] Add an Attack → Skip → draw sequence to verify pending draws and turn numbers throughout.
- [x] Add a scenario with multiple action cards played before drawing to verify hand counts, discards, and permission to act after the turn advances.
- [x] Verify preservation of the set of `card_id` values and `handCount == len(hand)` after each step in action sequences.

### 4. Explosion, Defuse, and end-game

- [x] Drawing a bomb enters pending explosion resolution and locks actions.
- [x] Defuse automatically consumes exactly one card, reinserts the bomb, and continues or ends the turn according to pending draws.
- [x] Without Defuse, eliminate the player, discard their entire hand, and advance the turn or determine the winner.
- [x] Reject actions after the game has finished.
- [x] Add a case where the bomb is the last card in the draw pile and the player has Defuse: reinsert the bomb successfully, preserve all cards, and release the action lock.
- [x] Add an Attack → bomb draw scenario covering both Defuse and elimination with multiple pending draws.

### 5. Room/session services

- [x] Cover room create/join/ready/start preconditions and session create/bind/unbind/rebind.
- [x] Add cases for joining with a lowercase room code and a nonexistent room code.
- [x] Verify that join/ready/start requests are rejected in invalid states without mutating the room.
- [x] Verify that the old socket disconnecting after takeover does not remove the new binding.
- [x] Verify that one socket cannot create conflicting bindings across two sessions; reject conflicting bind/rebind operations without changing either session.
- [x] Verify that removing a session cleans up the socket index without affecting other sessions.

### 6. Full-match scenarios and hidden information

- [x] Handler tests verify that See the Future results are sent only to the acting player and that Favor does not expose the transferred card in public payloads.
- [x] Cover public/private state restoration on reconnect and ensure duplicate draw/Favor requests do not resolve a second time.
- [x] Add a complete match through service calls: create/join/ready → setup → actions/draw → elimination → winner.
- [x] Throughout the complete match, verify card conservation, hand counts, and that the current player is not eliminated while the game is running; resolve pending explosions before the next step.
- [x] Compare existing payload tests against hidden-information rules: do not expose other players' hands, draw order, the full discard pile, or other players' session tokens; add only missing assertions.

### 7. Test implementation and acceptance

- [x] Use shuffler/RNG stubs for scenarios requiring deterministic results; do not assert that a random shuffle always changes the order.
- [x] Reuse fixtures/helpers where they improve scenario readability; give each test its own registry/state.
- [x] If an implementation bug is found, record the violated rule and add a regression test; do not change expected results merely to make tests pass.
- [x] Update `backend/README.md` with instructions for installing dev dependencies (`python -m pip install -e '.[dev]'`) and running local tests (`python -m pytest -q`) in a Python 3.12+ virtual environment.
- [x] Rerun the entire backend test suite after changes and record the acceptance results.
- [x] Complete the rule → test mapping and explicitly list items deferred to other issues before closing this issue.


## Implementation results

- Validation: `cd backend && .venv/bin/python -m pytest -q` — **167 passed** (previous baseline: 131).
- Added deterministic action sequences and complete service matches for 3, 4, and 5 players.
- Fixed first-seat selection and conflicting socket/session bindings, with regression tests and gateway rejection handling.
- [Rule-to-test mapping, regression details, and deferred work](15-backend-test-coverage.md).
- Checked items describe completion within the scope above; deferred lifecycle and real transport work is not implemented by this issue.

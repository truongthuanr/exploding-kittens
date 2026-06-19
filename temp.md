# Issue #3

## Scope

- Lock shared contracts early so backend and frontend do not drift.
- Contracts must match current docs in `plan/implementation-plan.md`, `plan/game-engine-spec.md`, and `plan/technical-design.md`.
- Backend must be able to validate incoming socket payloads with Pydantic models before they reach services or the game engine.

## Core enums to define

- `RoomStatus`
  - `waiting`
  - `starting`
  - `in_game`
  - `finished`
- `GamePhase`
  - `lobby`
  - `setup`
  - `turn_action`
  - `turn_draw`
  - `resolving_explosion`
  - `finished`
- `CardType`
  - `exploding_kitten`
  - `defuse`
  - `skip`
  - `attack`
  - `shuffle`
  - `see_the_future`
  - `favor`
- `PlayerStatus`
  - `connected`
  - `disconnected`
  - `eliminated`
- `ActionType`
  - `start_game`
  - `play_skip`
  - `play_attack`
  - `play_shuffle`
  - `play_see_the_future`
  - `play_favor`
  - `draw_card`
  - `defuse`
  - `explode`
  - `eliminate`
  - `turn_advanced`

## Shared contract location

- Put canonical wire-level contracts in `shared/contracts/`.
- Files:
  - `enums.ts`
  - `event-names.ts`
  - `requests.ts`
  - `responses.ts`
  - `index.ts`

## Contract decisions to lock

- Return `playerSessionId` immediately after `room:create` and `room:join`.
- Use ack responses for `room:create` and `room:join`.
- Keep `RoomStatus` and `GamePhase` as separate enums.
- Remove `turn:defuse` from the MVP socket contract.
- Keep `Defuse` as backend auto-resolution for MVP.
- Use `ActionType` enum for `recentAction.actionType`.

## Naming convention

- Event names use `domain:action`.
- Field names on the wire use `camelCase`.
- Enum values use `snake_case`.
- Backend may use Python aliases internally, but serialized payloads must match wire contract names exactly.

## Public/private payload boundary

- `game:state` contains public data only:
  - `roomId`
  - `phase`
  - `currentPlayerId`
  - `pendingDraws`
  - `turnNumber`
  - `players`
  - `discardTopCardType`
  - `discardCount`
  - `winnerPlayerId`
  - `recentAction`
- `player:private-state` contains hidden data only:
  - `playerId`
  - `hand`
  - `visibleFutureCards`
- Do not broadcast the card type received from `Favor`.
- Do not broadcast full `discardPile` in MVP. Broadcast only `discardTopCardType` and `discardCount`.

## Socket events in scope for this issue

- Client -> server
  - `room:create`
  - `room:join`
  - `room:ready`
  - `game:start`
  - `turn:play-card`
  - `turn:draw-card`
  - `player:reconnect`

- Server -> client
  - `room:updated`
  - `game:started`
  - `turn:started`
  - `game:state`
  - `player:private-state`
  - `player:eliminated`
  - `game:ended`
  - `error`

## Schemas to add

- Shared TypeScript contracts in `shared/contracts/`:
  - enums
  - event names
  - request payloads
  - response/event payloads
- Backend Pydantic models in `backend/app/schemas/`:
  - `enums.py`
  - `requests.py`
  - `responses.py`
  - `__init__.py`

## Request/response schemas to define

- Client -> server requests
  - `RoomCreateRequest`
  - `RoomJoinRequest`
  - `RoomReadyRequest`
  - `GameStartRequest`
  - `PlayCardRequest`
  - `DrawCardRequest`
  - `ReconnectRequest`

- Ack responses
  - `RoomCreateResponse`
  - `RoomJoinResponse`

- Server -> client events
  - `RoomUpdatedEvent`
  - `GameStartedEvent`
  - `TurnStartedEvent`
  - `PublicGameStateEvent`
  - `PlayerPrivateStateEvent`
  - `PlayerEliminatedEvent`
  - `GameEndedEvent`
  - `ErrorEvent`

## Backend validation rules

- Validate every incoming payload with Pydantic before it reaches services or the game engine.
- Do not trust `cardType` from the client.
- `turn:play-card` accepts:
  - `requestId?`
  - `cardId`
  - `targetPlayerId?`
- `targetPlayerId` is valid only for `favor`.
- Reject payloads with invalid enum values, missing required fields, or unexpected action-specific fields.

## Documentation updates required

- Update docs to reflect that `turn:defuse` is not part of the MVP contract.
- Add ack response shapes for `room:create` and `room:join`.
- Document `ActionType` as the allowed value set for `recentAction.actionType`.
- Document the public/private payload boundary explicitly.

## Done when

- Core enums and payload schemas exist.
- Shared TypeScript contracts exist in `shared/contracts/`.
- Backend Pydantic models exist in `backend/app/schemas/`.
- Incoming socket payloads can be validated against backend schema models.
- Contracts match current docs after the documentation updates above are applied.

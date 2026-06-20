## Goal
Create the in-memory room model and registry used by the multiplayer flow.

## Scope
- Define room state structure
- Add room registry storage
- Support room lookup by id/code
- Track room status and player membership

## Done when
- Room state can be created and queried in memory
- Room lifecycle fields required by the docs are present
- The registry is ready for room service logic

## Source docs
- `plan/implementation-plan.md`
- `plan/functional-spec.md`
- `plan/technical-design.md`

## Implementation checklist

### 1. Backend model
- backend/app/modules/room/models.py
- RoomPlayerState: player_id, nickname, is_ready, status
- RoomState: room_id, room_code, status, host_player_id, players, created_at

### 2. Helper domain method
- get_player(player_id)
- has_nickname(nickname)
- is_joinable()
- is_host_player(player_id)
- to_room_updated_event()

### 3. Backend registry
- backend/app/modules/room/registry.py
- rooms_by_id: dict[str, RoomState]
- room_id_by_code: dict[str, str]
- API
    - add(room)
    - get_by_id(room_id)
    - get_by_code(room_code)
    - remove(room_id)

### 4. Room rule
- room_code is unique
- 1 host for each room
- nickname is room unique
- only joinable while status == waiting
- max 5 players

### 5. Unit test
- create room and store in registry
- lookup room by room_id
- lookup room by room_code
- reject duplicate room_code
- reject duplicate nickname in room
- reject join when room status is not waiting
- map RoomState to room:updated payload correctly

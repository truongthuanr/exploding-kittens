# Backend core test coverage

Paths below are relative to `backend/tests/`. Test names identify collected pytest
cases; parametrized tests cover the variants described in each row.

## Scope and acceptance

Issue 15 covers engine rules, room create/join/ready/start, session
create/bind/unbind/rebind/remove, and existing handler-level payload checks.
It does not claim complete functional-spec or real Socket.IO transport coverage.

Validation: `cd backend && .venv/bin/python -m pytest -q` — **167 passed**.
The previous baseline was 131 passing cases; this change adds 36 collected cases.
Random outcomes in the new scenarios use identity/reverse shufflers or fixed
insertion indexes. Each scenario creates its own registries and runtime state.

## Rule-to-test mapping

| Rule / scenario | Test file::test name |
| --- | --- |
| Setup for 3–5 players: bomb count and remaining deck size | `test_game_setup.py::test_setup_uses_expected_exploding_kitten_count_for_supported_player_counts`; `test_setup_draw_pile_size_matches_remaining_cards_after_dealing` in the same file |
| Five starting cards, at least one Defuse, no starting bombs for all supported counts | `test_game_setup.py::test_setup_deals_five_cards_and_at_least_one_defuse_to_each_player` |
| Initial phase, turn, pending draws, public hand counts, empty discard/winner | `test_game_setup.py::test_setup_initializes_turn_state_and_public_player_summaries` |
| Reject unsupported player counts (0, 2, 6) | `test_game_setup.py::test_setup_rejects_unsupported_player_counts` |
| Exact global deck composition and unique card IDs | `test_game_setup.py::test_setup_preserves_deck_composition_and_unique_ids` |
| The first seat starts, even when the host occupies another seat | `test_game_setup.py::test_setup_starts_with_first_seat_even_when_host_is_elsewhere` |
| Normal draw adds only the top card to the current hand and consumes one pending draw | `test_turn_service.py::test_valid_normal_draw_adds_top_card_to_only_current_player_hand` |
| Normal draw completes the turn when one draw remains | `test_turn_service.py::test_normal_draw_with_one_pending_draw_completes_turn` |
| Skip completes the turn or reduces outstanding draws | `test_turn_service.py::test_play_skip_with_one_pending_draw_discards_card_and_completes_turn`; `test_play_skip_with_multiple_pending_draws_keeps_current_player_and_reduces_one_draw` in the same file |
| Attack transfers outstanding draws plus one, including chaining | `test_turn_service.py::test_attack_chaining_preserves_stacking_policy` |
| Attack → Skip → draw: turn numbers, draw burden, card conservation | `test_game_sequences.py::test_attack_skip_draw_sequence_preserves_turns_and_cards` |
| Shuffle changes order through the injected RNG and permits 0/1 cards | `test_turn_service.py::test_play_shuffle_discards_card_and_randomizes_draw_pile`; `test_play_shuffle_allows_small_draw_piles` in the same file |
| See the Future reads up to three cards without modifying the deck | `test_turn_service.py::test_play_see_the_future_stores_top_three_card_types_without_changing_deck`; `test_play_see_the_future_handles_fewer_than_three_cards` in the same file |
| Multiple action cards before drawing; old actor cannot act after turn advancement | `test_game_sequences.py::test_multiple_actions_before_draw_and_old_actor_rejected` |
| Favor transfers one random target card without advancing the turn | `test_turn_service.py::test_play_favor_transfers_random_target_card_without_advancing_turn` |
| Favor rejects missing/self/unknown/eliminated/empty targets; disconnected targets remain eligible | `test_turn_service.py::test_play_favor_rejects_invalid_target`; `test_play_favor_rejects_eliminated_target`; `test_play_favor_rejects_empty_target_hand`; `test_play_favor_allows_disconnected_target` in the same file |
| Invalid turn, phase, status, lock, pending draws and empty deck do not mutate state | `test_turn_service.py::test_invalid_draw_requests_are_rejected_without_state_mutation`; `test_invalid_action_card_requests_are_rejected_without_state_mutation` in the same file |
| Missing card or wrong card type is rejected without mutation | `test_turn_service.py::test_card_not_in_hand_is_rejected_without_state_mutation`; `test_wrong_card_type_for_action_is_rejected_without_state_mutation` in the same file |
| Circular seat order skips eliminated players | `test_turn_service.py::test_next_alive_player_wraps_around_and_skips_eliminated_players` |
| Bomb draw locks actions and preserves pending draws until resolution | `test_turn_service.py::test_exploding_kitten_draw_enters_pending_explosion_without_decrementing_pending_draws` |
| Defuse consumes exactly one card, reinserts the bomb, releases the lock and advances/retains the turn | `test_turn_service.py::test_resolving_explosion_with_defuse_consumes_one_defuse_and_advances_turn`; `test_resolving_explosion_with_defuse_and_multiple_pending_draws_keeps_current_player` in the same file |
| Bomb is the last deck card; Attack followed by explosion covers Defuse and elimination | `test_game_sequences.py::test_attack_then_explosion_with_multiple_pending_draws` |
| No Defuse eliminates the player and discards the hand; last survivor wins | `test_turn_service.py::test_resolving_explosion_without_defuse_eliminates_player_and_advances_turn`; `test_resolving_explosion_without_defuse_finishes_game_with_surviving_winner` in the same file |
| Complete service match for 3/4/5 players, card conservation, accurate hand counts and rejection after finish | `test_game_sequences.py::test_complete_match_through_services` |
| Room creation establishes host and registry membership | `test_room_service.py::test_create_room_creates_host_and_stores_room` |
| Lowercase room codes work; missing rooms do not mutate registries | `test_room_service.py::test_join_room_adds_player_to_waiting_room`; `test_join_unknown_room_does_not_mutate_registry` in the same file |
| Full rooms and duplicate nicknames are rejected | `test_room_service.py::test_join_room_rejects_room_that_is_full`; `test_join_room_rejects_duplicate_nickname` in the same file |
| Ready updates and start require host, player count, readiness and connection | `test_room_service.py::test_set_ready_updates_player_state`; all `test_validate_start_preconditions_*` cases in the same file |
| Join/ready/start in starting/in_game/finished states fail without mutation | `test_room_service.py::test_lobby_actions_in_invalid_states_do_not_mutate_room` |
| Session creation, lookup and binding | `test_session_service.py::test_create_session_stores_session_in_registry`; `test_bind_socket_binds_session_and_marks_it_connected`; `test_get_session_by_player_returns_matching_room_player_session` in the same file |
| Unbind retains session; rebind replaces old socket | `test_session_service.py::test_unbind_socket_clears_binding_without_deleting_session`; `test_rebind_socket_reassigns_same_session_to_new_socket` in the same file |
| Late disconnect of old socket preserves new binding | `test_session_service.py::test_old_socket_disconnect_after_takeover_preserves_new_binding` |
| Occupied socket cannot bind/rebind another session; rejection preserves both sessions | `test_session_service.py::test_socket_conflict_is_rejected_without_changing_either_session` |
| Session removal cleans indexes without affecting other sessions | `test_session_service.py::test_remove_session_cleans_index_without_affecting_other_session` |
| Socket create/join/reconnect conflicts emit an error without registry mutation | `test_socket_room_session_flow.py::test_bound_socket_conflict_does_not_mutate_rooms_or_sessions` |
| Public payload omits hidden cards/full discard/session tokens; reconnect returns only owner's hand | `test_socket_room_session_flow.py::test_reconnect_snapshot_excludes_other_players_secrets` |
| Future results only reach actor; Favor does not expose transferred card publicly | `test_socket_room_session_flow.py::test_turn_play_see_the_future_emits_future_cards_only_to_actor`; `test_turn_play_favor_emits_public_and_private_state_without_leaking_card` in the same file |
| Duplicate draw/Favor does not resolve twice | `test_socket_room_session_flow.py::test_duplicate_draw_request_reemits_snapshot_only_to_requester`; `test_duplicate_favor_request_reemits_snapshot_without_second_transfer` in the same file |
| Game end synchronizes room status and emits result | `test_socket_room_session_flow.py::test_game_end_emits_game_ended_and_syncs_room_status` |

## Regression fixes and policy decisions

1. Setup selected the host even when the host was not at seat zero. The engine
   specification requires the first seat to start. Setup now selects the first
   player in seat order, independently of host privileges.
2. Binding an occupied socket overwrote its session index, leaving inconsistent
   session records. Policy: a socket belongs to at most one session. Reject a
   conflicting bind/rebind before releasing any existing binding. Takeover of
   the same session onto a free socket remains supported.
3. The gateway checks occupied sockets before create/join mutations and handles
   reconnect binding rejection using its existing `invalid_operation` error
   envelope. These checks keep the service fix from producing partial room
   creation or an uncaught reconnect exception.

## Deferred work and limits

These are follow-up items, not completed features or newly created tracker issues:

- Realtime integration/hardening (implementation plan Phase 3): real Socket.IO
  clients, simultaneous requests, lock behavior under contention and duplicate
  request behavior beyond the existing draw/Favor handler cases. Current tests
  invoke handlers and mock emissions; they do not prove transport delivery.
- Lifecycle/hardening (Phase 5): room leave/close, session expiry, rematch,
  reconnect of eliminated players and room/runtime connection-status consistency.
  Session binding tests alone do not establish these feature behaviors.
- Functional-contract reconciliation: rate limiting and the complete documented
  error-code catalog are not covered here. The gateway currently uses lowercase
  codes (including `invalid_operation`), while the functional spec lists uppercase
  names; resolving that mismatch requires a coordinated contract change.
- The complete-match test verifies the engine runtime through services. Room
  status synchronization at game end is separately covered by the existing
  handler test, because orchestration currently lives in the gateway.
- This is scenario coverage, not a measured line/branch coverage percentage.

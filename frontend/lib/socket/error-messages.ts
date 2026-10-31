import type { ErrorEvent } from "../../../shared/contracts";
import type { SessionStatus } from "./client";

export type RecoveryAction = "retry_admission" | "discard_admission" | "retry_restore" | "take_over" | null;
export type UserError = { message: string; action: RecoveryAction };

const messages: Record<string, UserError> = {
  room_not_found: { message: "Không tìm thấy phòng. Bỏ yêu cầu đang chờ để nhập mã khác.", action: "discard_admission" },
  duplicate_nickname: { message: "Tên này đã được dùng trong phòng. Bỏ yêu cầu đang chờ để chọn tên khác.", action: "discard_admission" },
  room_not_joinable: { message: "Phòng đã bắt đầu hoặc không còn nhận người chơi.", action: "discard_admission" },
  room_full: { message: "Phòng đã đủ người chơi.", action: "discard_admission" },
  invalid_request_id: { message: "Yêu cầu vào phòng không hợp lệ. Hãy bỏ yêu cầu đang chờ.", action: "discard_admission" },
  server_restarted: { message: "Máy chủ đã khởi động lại nên không thể kiểm tra yêu cầu cũ. Hãy bỏ yêu cầu đang chờ.", action: "discard_admission" },
  request_expired: { message: "Yêu cầu vào phòng đã hết hạn. Hãy bỏ yêu cầu đang chờ trước khi thử lại.", action: "discard_admission" },
  request_conflict: { message: "Yêu cầu này không còn khớp với dữ liệu đã gửi. Hãy bỏ yêu cầu đang chờ.", action: "discard_admission" },
  admission_busy: { message: "Máy chủ đang bận. Vui lòng thử lại cùng yêu cầu sau ít phút.", action: "retry_admission" },
  not_host: { message: "Chỉ chủ phòng có thể bắt đầu trận.", action: null },
  room_not_waiting: { message: "Phòng không còn ở trạng thái chờ.", action: null },
  player_not_in_room: { message: "Không tìm thấy bạn trong phòng. Hãy thử khôi phục phiên.", action: "retry_restore" },
  not_enough_players: { message: "Cần từ 3 đến 5 người chơi để bắt đầu.", action: null },
  players_not_ready: { message: "Tất cả người chơi cần Ready trước khi bắt đầu.", action: null },
  players_disconnected: { message: "Tất cả người chơi cần kết nối trước khi bắt đầu.", action: null },
  session_not_bound: { message: "Kết nối chưa gắn với phiên người chơi. Hãy thử khôi phục phiên.", action: "retry_restore" },
  session_in_use: { message: "Phiên này đang được dùng ở tab khác. Chọn tiếp tục ở tab này nếu muốn tiếp quản.", action: "take_over" },
  invalid_session: { message: "Phiên người chơi không còn hợp lệ. Hãy tạo hoặc vào phòng mới.", action: null },
  sync_overflow: { message: "Dữ liệu trận đấu chưa đồng bộ. Hãy thử khôi phục phiên.", action: "retry_restore" },
  not_ready: { message: "Đợi kết nối và phiên đồng bộ xong rồi thử lại.", action: null },
  game_not_found: { message: "Không tìm thấy trận đấu. Hãy thử khôi phục phiên.", action: "retry_restore" },
  game_not_in_progress: { message: "Trận đấu hiện không diễn ra.", action: null },
  player_not_found: { message: "Không tìm thấy người chơi trong trận.", action: null },
  not_current_player: { message: "Chưa đến lượt của bạn.", action: null },
  player_eliminated: { message: "Bạn đã bị loại khỏi trận.", action: null },
  player_disconnected: { message: "Người chơi chưa kết nối.", action: null },
  target_required: { message: "Chọn người chơi mục tiêu.", action: null },
  invalid_target: { message: "Không thể chọn chính mình làm mục tiêu.", action: null },
  target_hand_empty: { message: "Người chơi mục tiêu không còn lá bài nào.", action: null },
  card_not_in_hand: { message: "Lá bài này không có trên tay bạn.", action: null },
  invalid_card_type: { message: "Lá bài này không thể dùng cho thao tác đó.", action: null },
  invalid_turn_phase: { message: "Không thể thực hiện thao tác ở giai đoạn hiện tại.", action: null },
  turn_action_locked: { message: "Hãy hoàn tất thao tác đang chờ trước.", action: null },
  pending_resolution: { message: "Hãy xử lý tình huống đang chờ trước.", action: null },
  no_pending_explosion: { message: "Hiện không có lá Mèo Nổ cần xử lý.", action: null },
  invalid_explosion_state: { message: "Trạng thái Mèo Nổ chưa hợp lệ. Hãy thử khôi phục phiên.", action: "retry_restore" },
  invalid_pending_draws: { message: "Số lượt rút bài không hợp lệ. Hãy thử khôi phục phiên.", action: "retry_restore" },
  empty_draw_pile: { message: "Chồng bài rút đã hết.", action: null },
};

export function describeRealtimeError(error: ErrorEvent, session: SessionStatus): UserError {
  if (error.code === "timeout" || error.code === "invalid_ack") {
    if (session === "join_failed") {
      return { message: "Chưa xác định được kết quả tạo hoặc vào phòng. Hãy thử lại cùng yêu cầu; máy chủ có thể đã xử lý yêu cầu trước đó.", action: "retry_admission" };
    }
    return { message: "Chưa xác nhận được phiên người chơi. Hãy thử khôi phục lại.", action: "retry_restore" };
  }
  if (error.code === "not_connected") {
    return session === "join_failed"
      ? { message: "Chưa kết nối với máy chủ. Đợi kết nối lại rồi thử lại cùng yêu cầu.", action: "retry_admission" }
      : { message: "Chưa kết nối với máy chủ. Hãy thử khôi phục phiên khi có kết nối.", action: "retry_restore" };
  }
  if (error.code === "invalid_payload" || error.code === "invalid_operation") {
    return session === "join_failed"
      ? { message: "Thông tin tạo hoặc vào phòng không hợp lệ. Hãy bỏ yêu cầu đang chờ rồi nhập lại.", action: "discard_admission" }
      : { message: "Không thể thực hiện thao tác này. Vui lòng thử lại sau.", action: null };
  }
  return messages[error.code] ?? {
    message: "Có lỗi xảy ra. Vui lòng thử lại; nếu lỗi tiếp diễn, hãy tải lại trang.",
    action: session === "join_failed" ? "retry_admission" : null,
  };
}

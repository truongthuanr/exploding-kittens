## Goal
Xây dựng lớp realtime dùng chung cho frontend trước khi triển khai các màn hình room và game.

## Scope
- Dựng skeleton `frontend/` với Next.js + TypeScript vì repo hiện chưa có frontend.
- Khởi tạo socket client, cấu hình môi trường và quản lý connect/disconnect/reconnect lifecycle.
- Cung cấp API có type cho các request, ack và room/game events dựa trên `shared/contracts/`.
- Quản lý room state, public game state, private state, connection/session status và lỗi qua provider/hooks dùng chung.
- Persist identity để phục hồi session sau reload, mở lại trình duyệt hoặc mất kết nối.
- Mở rộng backend/shared contracts: reconnect bootstrap ack, version của state, ownership/takeover giữa các tab, create/join idempotency và nullable fields. Đây là phần triển khai backend trong scope, không chỉ bổ sung type.
- Chốt MVP chỉ có một socket active cho mỗi session. Reconnect tự động không giành ownership; tab khác phải được người dùng chủ động cho phép tiếp quản.
- Có component/trang kiểm tra tối giản để nghiệm thu tích hợp. UI sản phẩm cho home, lobby, bàn chơi và kết quả thuộc các issue sau.

## Definition of Done (DoD)
- Frontend chạy được theo hướng dẫn local, kết nối backend bằng cấu hình môi trường và nhận room/game events.
- Create/join lưu đúng identity, nhận được room snapshot đầu tiên dù event đến trước ack.
- Reload tại lobby khôi phục đúng player; reload giữa trận khôi phục đúng room, public state và private hand.
- Kết nối lại sau mất mạng phục hồi session trước khi cho phép gửi game action, không nhân đôi listener hoặc tự gửi lại action cũ.
- Reconnect trả identity và bootstrap snapshot nhất quán trong ack; client áp dụng bootstrap của lần thử hiện tại trước khi chuyển `ready`. Dữ liệu cũ không ghi đè state mới hơn.
- Create/join có nhánh `joining → ready`; retry sau mất ack dùng cùng request ID không tạo thêm room/player trong thời hạn idempotency đã chốt.
- Restore timeout chuyển `restore_failed`, có thao tác thử lại; callback đến muộn không thay đổi state của lần thử mới.
- `invalid_session` xóa identity/state cũ và đưa client về trạng thái cần create/join; lỗi mạng hoặc timeout giữ identity.
- Takeover chỉ xảy ra khi người dùng chọn tiếp quản. Tab cũ còn online nhận thông báo và khóa thao tác; tab cũ đang offline bị từ chối khi tự reconnect trở lại, không giành session ngược lại.
- Component mẫu đọc được state/status/lỗi và gửi intent qua API dùng chung, không phải tự quản lý socket lifecycle.
- Kiểm thử lifecycle/session và smoke test frontend với backend thật đạt các kịch bản trong checklist; typecheck/build frontend thành công.

## Checklist

### 1. Frontend foundation và cấu hình
- [ ] Dựng skeleton `frontend/` với Next.js + TypeScript và socket client dependency tương thích backend.
- [ ] Cấu hình `NEXT_PUBLIC_SOCKET_URL`, socket path và backend CORS cho origin frontend.
- [ ] Bổ sung env example và hướng dẫn cài đặt/chạy frontend cùng backend.
- [ ] Tái sử dụng `shared/contracts/`, tránh định nghĩa lại payload riêng trong frontend.

### 2. Chốt contract và bổ sung backend
- [ ] Định nghĩa typed event maps cho client requests, server events và ack.
- [ ] Đồng bộ nullable fields với payload Python thực tế, gồm `ErrorEvent.requestId` và `RecentAction.targetPlayerId`.
- [ ] Reconnect request gồm `playerSessionId`, `clientInstanceId`, `takeover` và `attemptId`; ack/error trả correlation tương ứng để đối chiếu lần thử.
- [ ] Success ack reconnect chứa identity (`roomId`, `roomCode`, `playerId`, `playerSessionId`), room snapshot, public game snapshot, private snapshot và `stateVersion`. Không yêu cầu client đếm các event để xác định restore thành công.
- [ ] Lobby chưa có game trả game/private snapshot là `null`; game đang chơi hoặc đã kết thúc trả đủ public/private snapshot. Không chờ `turn:started` để hoàn tất restore.
- [ ] Tạo và serialize bootstrap snapshot dưới cùng cơ chế khóa với các mutation liên quan của room/game, bảo đảm public/private state nhất quán.
- [ ] Định nghĩa `stateVersion` tăng đơn điệu theo room, gắn vào bootstrap và các state events liên quan; quy định cách ghép các payload public/private cùng version, không bỏ nhầm private payload vì public payload cùng version đã tới.
- [ ] Lỗi reconnect đi qua event `error` có correlation; ack rỗng không được xem là thành công.
- [ ] Backend ghi nhận instance sở hữu session từ create/join. Reconnect tự động dùng `takeover: false`; instance khác nhận `session_in_use` ngay cả khi owner cũ đang offline.
- [ ] Chỉ `takeover: true` do người dùng chủ động yêu cầu mới đổi owner; bảo vệ kiểm tra/đổi ownership và socket binding khỏi takeover đồng thời.
- [ ] Bổ sung `session:replaced`: sau khi đổi binding, thông báo rồi disconnect socket cũ; disconnect cũ không unbind session mới. Ownership không phụ thuộc vào việc tab cũ nhận được thông báo.
- [ ] Cùng instance ID nhưng socket khác còn active cũng phải yêu cầu tiếp quản; xử lý tab nhân bản có `sessionStorage` bị sao chép, không tự thay binding.
- [ ] Create/join request thêm `requestId` và `clientInstanceId`; error trả `requestId` để đối chiếu.
- [ ] Lưu kết quả create/join theo request ID với payload/instance tương ứng. Cùng ID và payload trả lại cùng identity; khác payload/instance bị từ chối. Bảo vệ kiểm tra trùng và tạo room/player khỏi xử lý đồng thời.
- [ ] Chốt TTL, giới hạn bộ nhớ và hành vi request hết hạn cho idempotency; client không retry quá hạn như một request mới. Ghi rõ cache/session in-memory không tồn tại qua backend restart.
- [ ] Retry create/join trên socket mới áp dụng kiểm tra ownership và bind/enter room an toàn; trả identity cũ kèm state hiện tại hoặc chạy bootstrap reconnect, không dùng snapshot cache đã lỗi thời để đánh dấu ready.
- [ ] Đồng bộ Python schemas và TypeScript contracts; bổ sung backend tests cho bootstrap, version, ownership và idempotency, giữ nguyên ranh giới public/private data.

### 3. Socket lifecycle và gửi request
- [ ] Khởi tạo socket ở browser, dùng chung trong mỗi tab; không truy cập browser storage khi server render.
- [ ] Đăng ký listener trước khi kết nối; không đăng ký lại toàn bộ listener sau mỗi reconnect.
- [ ] Cleanup đúng listener khi dispose, không ảnh hưởng subscriber khác; kiểm tra mount/unmount lặp lại không tạo kết nối trùng.
- [ ] Quản lý connection status: `disconnected`, `connecting`, `connected`, `reconnecting`; expose connection error riêng với lỗi nghiệp vụ.
- [ ] Cung cấp hàm gửi create/join, ready, start, play-card và draw-card theo contract.
- [ ] Chỉ giữ một create/join request đang chờ trong tab; lưu request ID, payload, instance và thời điểm gửi vào `sessionStorage` trước khi gửi.
- [ ] Create/join chuyển `none` hoặc `join_failed` sang `joining`; chỉ chuyển `ready` sau khi nhận identity ack hợp lệ và room snapshot đúng room. Xử lý ack rỗng và lỗi có correlation, bỏ qua kết quả cũ.
- [ ] Lỗi nghiệp vụ create/join chuyển `join_failed` với lỗi đã xác định; timeout chuyển `join_failed` với outcome `unknown`, không giả định server chưa xử lý.
- [ ] Đăng ký nhận và lưu room snapshot độc lập với create/join ack để không bỏ lỡ event đầu tiên.
- [ ] Gửi `requestId` cho game actions có hỗ trợ; đối chiếu error theo `requestId`, không tự thêm field vào request không hỗ trợ.
- [ ] Chỉ gửi thao tác cần session khi connection `connected` và session `ready`; backend vẫn kiểm tra luật và quyền thao tác.
- [ ] Không queue hoặc tự gửi lại game action trong lúc offline/restoring. Timeout không được xem là bằng chứng server chưa xử lý request.
- [ ] Expose retry create/join cho người dùng, giữ nguyên request ID/payload trong thời hạn đã chốt; không tự retry bằng ID mới sau timeout.
- [ ] Thành công thì persist identity và xóa pending request; reload khi còn pending request phải phục hồi trạng thái chờ/thử lại, không tự tạo một request mới.
- [ ] Request hết hạn hoặc backend restart phải có trạng thái lỗi/giới hạn phục hồi rõ ràng; không tự coi request cũ là thao tác mới.

### 4. Session persistence và reconnect
- [ ] Dùng `localStorage`, lưu object có `version`, `playerSessionId`, `playerId`, `roomId`, `roomCode` sau create/join thành công.
- [ ] Tạo `clientInstanceId` trong `sessionStorage` để giữ qua reload của tab; instance ID không thay thế session token để xác thực.
- [ ] Chỉ dùng `playerSessionId` làm thông tin xác thực reconnect; identity lưu phía client không thay thế xác thực của backend.
- [ ] Validate dữ liệu storage; xử lý JSON hỏng, version không hỗ trợ hoặc storage không khả dụng mà không làm ứng dụng crash.
- [ ] Nếu storage không khả dụng, giữ identity/instance/pending request trong bộ nhớ và expose giới hạn phục hồi qua reload.
- [ ] Đọc identity khi khởi động; sau mỗi socket connect, tự reconnect với `takeover: false` nếu có session và không bị chặn bởi trạng thái replaced/session-in-use.
- [ ] Quản lý session status riêng: `none`, `joining`, `join_failed`, `ready`, `restoring`, `restore_failed`, `invalid`, `replaced`.
- [ ] Mỗi lần restore tạo `attemptId`, gắn với kết nối hiện tại và timeout cấu hình được (mặc định 10 giây); bỏ qua ack/error đến muộn của lần thử hoặc kết nối cũ.
- [ ] Trong lúc restore, giữ các update mới tới; áp dụng bootstrap rồi hòa giải theo version trước khi chuyển `ready`. Không dùng state cũ để đánh dấu đã đồng bộ hoặc để bootstrap cũ ghi đè update mới.
- [ ] Dùng identity từ reconnect ack để xác nhận/cập nhật thông tin player và room đã lưu.
- [ ] Khi mất mạng, giữ identity và khóa action. Restore timeout chuyển `restore_failed`, expose `retryRestore()`; không chờ vô hạn hoặc tự tạo vòng retry lỗi nghiệp vụ.
- [ ] Khi nhận `invalid_session`, xóa identity/state cũ, đặt `invalid` và dừng restore session đó. Chỉ xóa storage nếu session đang lưu vẫn là session bị báo lỗi, tránh xóa identity mới của tab khác.
- [ ] Khi nhận `session_in_use` hoặc `session:replaced`, đặt `replaced`, khóa thao tác và dừng tự restore; expose thông báo cùng thao tác “Tiếp tục ở tab này”.
- [ ] Chỉ thao tác tiếp quản chủ động mới gửi `takeover: true`; quyền owner mới được backend thực thi kể cả khi tab cũ offline và bỏ lỡ thông báo.
- [ ] Tab bị thay thế không xóa `localStorage` chung vì tab mới vẫn cần session; không tự giành lại session qua reconnect hoặc storage event.

### 5. State và API cho component
- [ ] Subscribe `room:updated`, `game:started`, `turn:started`, `game:state`, `player:private-state`, `player:eliminated`, `game:ended`, `error` và `session:replaced`.
- [ ] Tách room/public/private state trong bộ nhớ; không persist hand hoặc hidden card information vào storage.
- [ ] Cập nhật state từ snapshot authoritative của server, không tự resolve luật game phía client.
- [ ] Xóa state không còn hợp lệ khi session bị vô hiệu hóa hoặc thay đổi identity; không hiển thị private state cũ cho session khác.
- [ ] Cung cấp provider/hooks để component đọc state, connection/session status, lỗi/outcome, gửi intent, retry restore/create/join và chủ động tiếp quản session.
- [ ] Dựng component/trang kiểm tra tối giản sử dụng API chung để kiểm chứng tích hợp, chưa xây UI lobby/game sản phẩm.

### 6. Kiểm thử và nghiệm thu
- [ ] Create/join nhận snapshot đầu tiên ngay cả khi `room:updated` đến trước ack; identity được lưu đúng.
- [ ] Reload tại lobby phục hồi đúng player, không tạo thêm player mới.
- [ ] Reload giữa trận nhận đúng public state và private hand; không nhận hand của player khác.
- [ ] Reconnect vào game đã kết thúc hoàn tất mà không chờ `turn:started`.
- [ ] Mất mạng rồi kết nối lại không nhân đôi listener, không replay action và chỉ mở thao tác sau khi đồng bộ xong.
- [ ] Session không hợp lệ hoặc backend mất session sau restart thoát được vòng reconnect.
- [ ] Create/join chuyển `joining → ready` đúng điều kiện; lỗi/timeout có trạng thái `join_failed` và outcome rõ ràng.
- [ ] Hai tab cùng session: tab mới bị chặn cho tới khi người dùng chọn tiếp quản; tab cũ dừng reconnect, disconnect cũ không làm mất binding mới.
- [ ] Tab A offline → tab B chủ động takeover → A online trở lại: A nhận `session_in_use`, không giành lại session.
- [ ] Tab nhân bản dùng cùng instance ID không tự thay socket active; takeover đồng thời vẫn chỉ có một owner/socket hợp lệ.
- [ ] Mất ack create/join rồi retry cùng ID trên cùng/socket mới hoặc sau reload không tạo thêm room/player, nhận được state hiện tại.
- [ ] Request ID trùng nhưng payload khác bị từ chối; request đồng thời, hết TTL và backend restart có hành vi đúng giới hạn đã tài liệu hóa.
- [ ] Restore timeout chuyển `restore_failed`, thử lại thành công; ack/error cũ đến muộn không ghi đè lần thử mới.
- [ ] Reconnect đồng thời với game action nhận public/private state nhất quán; bootstrap cũ không ghi đè update mới, các payload cùng version không bị bỏ nhầm.
- [ ] Storage hỏng/không khả dụng, ack rỗng và request timeout đều có trạng thái lỗi xác định, không crash hoặc chờ vô hạn.
- [ ] Component mount/unmount lặp lại không tạo socket/listener trùng.
- [ ] Chạy typecheck, build và các test frontend/backend liên quan.
- [ ] Smoke test với browser và backend thật; ghi lại cách chạy và kết quả nghiệm thu.

## Source docs
- `plan/implementation-plan.md`
- `plan/technical-design.md`

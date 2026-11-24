# Kế Hoạch Thực Thi: Xử Lý Logic Khách Hàng Có Nhiều Đơn Hàng (Multi-Order Disambiguation & Fallback Fixes)

> **Nguồn yêu cầu:** Kiểm thử thực tế trên nhân vật **Bùi Thị An (`CUST-1001` / `demo-customer`)** hiện có **14 đơn hàng** trong `data/mock_orders.json`, gửi request thật qua Gateway `:18000` / `:15173`.
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-multi-order-customer-disambiguation`
- **Tên Task:** `Sửa lỗi đồng bộ tên chủ đơn trong mock_orders, hỗ trợ tra cứu/làm rõ nhiều đơn hàng cùng lúc (Bùi Thị An) và sửa lỗi draft fallback in 'None' / sai trạng thái`
- **Thời gian tạo / cập nhật:** `2026-11-23T20:36:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `VERIFIED (Unit tests + Live Docker CUST-1001)`
- **Trạng thái phê duyệt:** `APPROVED (Đợt 4)`

---

## 2. Các lỗi thực tế vừa quan sát được khi test với Bùi Thị An (`Observed`)

Qua gửi request thực tế với `customer_id = "CUST-1001"` (tương ứng `demo-customer`, **14 đơn hàng** từ `ORD-1001` đến `ORD-1095`):

1. **Lỗi dữ liệu nghiêm trọng: 13/14 đơn của `demo-customer` đang mang TÊN KHÁCH HÀNG KHÁC (`mock_orders.json`):**
   - Trong 14 đơn của `demo-customer` (`Bùi Thị An`), chỉ `ORD-1001` ghi `"Bùi Thị An"`; 13 đơn còn lại ghi ngẫu nhiên `"Trần Mai Khánh"` (`ORD-1026`), `"Dương Thu Cường"` (`ORD-1030`), `"Đặng Mai Bình"` (`ORD-1095`), `"Võ Thị Quân"` (`ORD-1005`), v.v.!
   - Đây chính là nguyên nhân khiến khi test với Bùi Thị An ở trang `real_testing.pdf` Trang 3, chatbot gọi nhầm tên khách khác dù tra đúng mã đơn của tài khoản này!
2. **Câu hỏi chung chung (*"Kiểm tra đơn hàng của tôi"*, *"Tôi muốn hủy đơn hàng"*) luôn bị khóa cứng vào đúng 1 đơn mới nhất `ORD-1095` (`Delivered`):**
   - `TelemetryRepository.get_order("CUST-1001")` chạy `ORDER BY order_id DESC LIMIT 1`, chỉ lấy `ORD-1095` (`Delivered`, Tai nghe Sony) và bỏ qua toàn bộ 13 đơn kia.
   - Hậu quả khi nói *"Tôi muốn hủy đơn hàng"*: hệ thống tự gắn `pending_action` vào `ORD-1095` (`Delivered` → báo không đủ điều kiện hủy!), trong khi `Bùi Thị An` đang có **2 đơn `Processing` hoàn toàn hủy được** (`ORD-1026`, `ORD-1030`), còn câu trả lời bị chặn thành fallback `ESCALATE_HUMAN` chung chung thay vì hỏi lại khách chọn mã đơn nào!
3. **Câu hỏi lọc theo trạng thái (*"Tôi có những đơn hàng nào đang bị giao trễ hoặc chưa giao?"*) không trả lời được:**
   - Pipeline chỉ nạp 1 `order_data` đơn lẻ vào `CopilotDraftEngine` thay vì danh sách tóm tắt các đơn của khách (`customer_orders`), nên không thể liệt kê `ORD-1005`, `ORD-1010`, `ORD-1015` (`Delivery_Delayed`), `ORD-1001` (`Shipping`), `ORD-1026`, `ORD-1030` (`Processing`).
4. **Câu hỏi theo tên sản phẩm trùng ở nhiều đơn (*"Đơn Giày thể thao Biti's Hunter"*) âm thầm chọn 1 đơn mà không làm rõ:**
   - `Bùi Thị An` có tới **3 đơn** mua *"Giày thể thao Biti's Hunter"* (`ORD-1005`, `ORD-1015`, `ORD-1051`), **2 đơn** mua *"Bàn phím cơ Logitech MX Mechanical"* (`ORD-1026`, `ORD-1040`), **2 đơn** mua *"Quạt tích điện"* (`ORD-1060`, `ORD-1085`), **2 đơn** mua *"Tai nghe Sony"* (`ORD-1091`, `ORD-1095`).
   - `OrderMatcher.match()` chỉ trả về 1 kết quả đầu tiên thay vì phát hiện mơ hồ (`ambiguous_matches`) để hỏi lại khách.
5. **Câu hỏi nhắc nhiều mã đơn trong 1 câu (*"Đơn ORD-1095 ... đơn ORD-1030 ..."*):**
   - `ORDER_RE` hiện tại chỉ lấy mã đơn đầu tiên (`ORD-1095`), bỏ sót mã đơn thứ hai (`ORD-1030`).
6. **Bug hiển thị của `CopilotDraftEngine._build_semantic_fallback_draft()` (khi LLM chính lỗi/offline):**
   - In thẳng chữ **`"dự kiến giao đến mình None"`** khi `estimated_delivery` là `None` (`Processing`/`Delivered`/`Cancelled`).
   - Luôn khẳng định *"đơn hàng đang được vận chuyển bởi bưu tá"* kể cả khi đơn đang **`Delivered`**, **`Processing`**, **`Cancelled`** hay **`Payment_Failed`**.
   - Đính nhầm toàn bộ `[POL-*]` mà RAG trả về (VD: chèn `[POL-WARRANTY-005]`, `[POL-RET-007]` vào câu trả lời tra cứu giao hàng).

---

## 3. Hướng giải quyết đề xuất

1. **Làm sạch nhất quán chủ tài khoản trong `data/mock_orders.json` (và `new_mock_orders.json` nếu cần):**
   - Chuẩn hóa toàn bộ 14 đơn của `customer_id = "demo-customer"` mang cùng `customer_name = "Bùi Thị An"` và `phone = "0938.242.854"` (khớp với bảng `customers` trong `services/telemetry_service/src/database.py`), đồng thời đảm bảo các đơn `Processing`/`Shipping`/`In_Transit` có `estimated_delivery` hợp lệ (không để chuỗi rác hoặc `None` gây hiểu nhầm).
   - Kiểm tra xem còn `customer_id` nào khác bị lệch `customer_name` giữa các đơn cùng chủ hay không để đồng bộ nhất quán (trong khi giữ nguyên `order_id`, `total_amount`, `items`, `order_status` để không làm gãy bất kỳ test nào).
2. **Nâng cấp `OrderMatcher` & `_resolve_scoped_order_and_guard()` hỗ trợ Multi-Order:**
   - Thêm hàm `match_all(query, customer_id)` trong `order_matcher.py` và `extract_all_order_ids(text)` trong `fact_extractor.py`:
     - Nếu câu hỏi chứa nhiều `ORD-*` → đính kèm `mentioned_orders` vào ngữ cảnh.
     - Nếu câu hỏi **không nêu rõ `ORD-*`** mà khách hàng có **>= 2 đơn khớp sản phẩm** hoặc **hỏi chung chung / lọc theo trạng thái / muốn hủy-đổi nhưng có nhiều đơn ứng viên**:
       - Nạp danh sách `customer_orders` (tối đa 10–15 đơn gần nhất thuộc đúng `customer_id`) vào state/prompt (`multi_order_context`).
       - Nếu khách muốn **hủy / đổi địa chỉ / trả hàng** mà chưa rõ `ORD-*` và có **> 1 đơn hợp lệ** (hoặc đơn mới nhất không hợp lệ nhưng khách có đơn khác đang `Processing` hủy được): **KHÔNG** ép `pending_action` vào đơn `Delivered` sai ngữ cảnh; trả về danh sách các đơn hợp lệ để khách xác nhận (`needs_order_disambiguation = True`).
       - Nếu có đúng **1 đơn hợp lệ** cho hành động đó (VD: chỉ có 1 đơn `Delivered` khi khách đòi trả hàng, hoặc chỉ 1 đơn `Processing` khi khách đòi đổi địa chỉ): ưu tiên gợi ý chính xác đơn hợp lệ đó kèm xác nhận từ khách!
3. **Xử lý truy vấn lọc danh sách theo trạng thái đơn (*"những đơn nào đang trễ / đang giao / chờ xử lý?"*):**
   - Nhận diện các từ khóa liệt kê trạng thái (`đơn nào`, `các đơn`, `những đơn`, `đang trễ`, `chưa giao`, `đang xử lý`, `tổng hợp đơn`) → lọc trực tiếp trên `customer_orders` của đúng `customer_id` và trả bảng/danh sách rõ ràng từng `ORD-*` + sản phẩm + trạng thái + lịch hẹn giao.
4. **Sửa triệt để `CopilotDraftEngine._build_semantic_fallback_draft()` & `build_full_context_prompt()`:**
   - Phân nhánh template theo đúng `order_status` (`Processing`, `Shipping` / `In_Transit`, `Delivery_Delayed`, `Delivered`, `Cancelled`, `Returned`, `Payment_Failed`), tuyệt đối không in `None` hay nói *"bưu tá đang giao"* cho đơn `Delivered`/`Processing`/`Cancelled`.
   - Khi có `multi_order_context` / `ambiguous_orders`, trình bày lịch sự từng đơn ứng viên (mã đơn + sản phẩm + trạng thái) để khách chọn chính xác trước khi thao tác.
   - Chỉ trích dẫn `[POL-*]` liên quan đúng intent thay vì rải tất cả top-K citations ngẫu nhiên.
5. **Tiện ích chọn nhanh đơn trên UI Chat (`CustomerPortalView` / `ChatView`):**
   - Hiển thị chip chọn nhanh mã đơn (`ORD-...`) trong danh sách đơn của khách nếu Copilot đang yêu cầu làm rõ (`needs_order_disambiguation`), giúp khách bấm 1 chạm gửi lại đúng mã đơn.

---

## 4. Phạm vi triển khai (`In Scope` / `Non-Goals`)

- **In Scope:**
  - `data/mock_orders.json` (đồng bộ `customer_name` / `phone` cho cùng `customer_id`, giữ nguyên `order_id`, `total_amount`, `items`, `order_status`).
  - `services/conversation_service/src/input_pipeline/fact_extractor.py` & `order_matcher.py` (`extract_all_order_ids`, `match_all`).
  - `services/conversation_service/src/main.py` & `contracts/order_actions.py` (nạp `customer_orders` khi khách có nhiều đơn, lọc ứng viên hợp lệ theo `action_type`, cờ `ambiguous_orders`).
  - `services/conversation_service/src/policies/copilot_draft_engine.py` (sửa triệt để `_build_semantic_fallback_draft`, bỏ lỗi `"None"`, hỗ trợ multi-order listing & prompt).
  - `tests/test_multi_order_disambiguation.py` + cập nhật test liên quan (`test_module3_orders.py` phải tiếp tục pass 100%).
- **Non-Goals:**
  - Không thay đổi mã `ORD-1001`..`ORD-1100` hoặc `total_amount` / `items` đã khóa trong các test regression cũ.

---

## 5. Ràng buộc & Tiêu chí Nghiệm thu (`Definition of Done`)

- [ ] Toàn bộ 14 đơn của `Bùi Thị An` (`demo-customer` / `CUST-1001`) đều thống nhất tên `"Bùi Thị An"` và SĐT `"0938.242.854"`.
- [ ] Khách hỏi *"Tôi có đơn nào đang giao trễ?"* trả về đủ các đơn `Delivery_Delayed` / `Shipping` thuộc đúng tài khoản đó.
- [ ] Khách hỏi *"Tôi muốn hủy đơn hàng"* khi có nhiều đơn không tự gán nhầm vào đơn `Delivered` (`ORD-1095`), mà liệt kê các đơn `Processing` hủy được (`ORD-1026`, `ORD-1030`) để xác nhận.
- [ ] Khách hỏi sản phẩm trùng ở nhiều đơn (*"Giày Biti's Hunter"*) liệt kê cả `ORD-1005`, `ORD-1015`, `ORD-1051` để làm rõ thay vì đoán mù 1 đơn.
- [ ] Không còn chuỗi `"None"` trong bất kỳ phản hồi fallback nào của `CopilotDraftEngine`.
- [ ] Toàn bộ test offline (`pytest`, `tsc --noEmit`, `npm run test:unit`) và test thực tế với `CUST-1001` trên Gateway `:18000` pass 100%.

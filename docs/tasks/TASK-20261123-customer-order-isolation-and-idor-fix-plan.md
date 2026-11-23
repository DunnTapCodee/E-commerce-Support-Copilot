# Kế Hoạch Thực Thi: Cô Lập Đơn Hàng Theo Khách Hàng & Vá Lỗ Hổng Lộ PII (IDOR)

> **Tài liệu nguồn:** `docs/new_tasks/real_testing.pdf` (Mục 1 & Mục 3, Trang 1–3)
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-customer-order-isolation-idor-fix`
- **Tên Task:** `Siết quyền sở hữu khách hàng khi tra cứu đơn hàng, trích xuất thực thể và đưa ngữ cảnh vào prompt LLM (Fix IDOR / Lộ PII)`
- **Thời gian tạo / cập nhật:** `2026-11-23T17:34:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_OFFLINE`
- **Trạng thái phê duyệt:** `APPROVED (Chủ dự án xác nhận triển khai Đợt 1 ngày 2026-11-23)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:** Ngăn chặn tình trạng Khách hàng A (VD: `Lê Văn Sơn`, `Bùi Thị An`, `Huỳnh Đức Linh`) hỏi ngẫu nhiên mã `CUST-*` khác, nhập nhầm mã đơn của người khác, hoặc nhắc tên sản phẩm trùng dẫn đến chatbot trả về `order_id`, tên người nhận, SĐT và lịch trình giao hàng của Khách hàng B (`Bùi Mai Phong`, `Huỳnh Đức Linh`, `Huỳnh Hữu Linh`, v.v.).
- **Kết quả kỳ vọng:**
  - Mọi luồng tra cứu đơn (`telemetry_service`, `conversation_service`, và fallback của `gateway`) đều bắt buộc kiểm tra quyền sở hữu theo `request.customer_id` đang đăng nhập/chọn phiên (trừ ngữ cảnh Nhân viên tra cứu có chủ đích).
  - Gỡ bỏ quy tắc suy diễn sai `CUST-XXXX -> ORD-XXXX` trong `TelemetryRepository.get_order()`.
  - Bộ khớp đơn theo sản phẩm/từ khóa (`OrderMatcher`) chỉ được phép tìm trong các đơn hàng thuộc về đúng `request.customer_id`.
  - Có bộ test hồi quy tái hiện đủ các tình huống lộ PII trong `real_testing.pdf` để chặn tái diễn.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (In Scope):**
  - `services/telemetry_service/src/repository.py` (`get_order`, truy vấn đơn có lọc theo `customer_id`)
  - `services/conversation_service/src/input_pipeline/fact_extractor.py` & `order_matcher.py` (truyền và áp dụng bộ lọc `customer_id`)
  - `services/conversation_service/src/main.py` (`/chat` và `/chat_stream`: kiểm tra quyền sở hữu `order_data` trước khi khóa vào `state.active_order_id`)
  - `services/gateway/src/main.py` (bộ kiểm tra sở hữu cho luồng degraded fallback `lookup_order`)
  - Test đơn vị / tích hợp (`tests/`) và cập nhật tài liệu ([copilot-workflow.md](../specs/copilot-workflow.md), [requirements.md](../product/requirements.md))
- **Ngoài phạm vi (Non-Goals):**
  - Xây dựng hệ thống đăng nhập JWT/OAuth hoàn chỉnh (là hạng mục auth riêng; task này siết chặt cô lập `customer_id` trên contract phiên/portal hiện tại)
  - Thay đổi quyền xem khách hàng của Nhân viên trên `StaffCustomerManagerView`

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-ORD-001`, `SC-007`, `NFR-SEC-002` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [Copilot Workflow Spec (`SPEC-WF-001`)](../specs/copilot-workflow.md)
- **Kiến trúc:** [Architecture Overview v1](../architecture/overview.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R3` (Chạm vào ranh giới bảo mật/phân quyền dữ liệu & bảo vệ PII liên dịch vụ — xem [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md))
- **Ràng buộc cứng:**
  - Tuyệt đối không đưa `order_data` có `customer_id != state.customer_id` vào `CopilotDraftEngine.build_full_context_prompt()` hoặc `GatewayResponse`.
  - Phải fail-closed an toàn (từ chối lịch sự khi thông tin đơn/mã KH không thuộc phiên hiện tại hoặc chuyển nhân viên kiểm tra) mà không làm lộ tên, SĐT, mã vận đơn của khách hàng khác.
  - Toàn bộ test chạy offline trên `tempfile.TemporaryDirectory()`.
- **Điểm cần duyệt:** Chủ dự án xác nhận cách xử lý dữ liệu mẫu bị lệch ID (`Bùi Thị An` mang `demo-customer` trong `mock_orders.json` so với `CUST-1001` trên UI) và quy tắc gỡ bỏ fallback `CUST-XXXX -> ORD-XXXX`.

---

## 6. Nguyên nhân gốc đã xác minh trong code (`Observed`)

Qua đối chiếu `docs/new_tasks/real_testing.pdf` (Trang 1–3) với mã nguồn hiện tại:

1. **Suy diễn chéo `CUST-XXXX -> ORD-XXXX` (`services/telemetry_service/src/repository.py#L336-L340`):**
   - Hàm `get_order("CUST-1007")` cắt số `"1007"` rồi chạy `WHERE order_id = 'ORD-1007' OR customer_id = 'cust-1007'`. Dù khách hàng đang chọn có `0` đơn hàng, việc gõ `"CUST-1007"` vẫn trả về **`ORD-1007` của `Huỳnh Đức Linh`**.
2. **Tìm kiếm sản phẩm toàn cục không lọc chủ đơn (`fact_extractor.py#L50-L60`, `order_matcher.py`):**
   - Khi câu hỏi không nêu rõ `ORD-XXXX` (VD: `Huỳnh Đức Linh` khiếu nại *"Bộ drap ga giường cotton lụa cao cấp"* hoặc `Bùi Thị An` hỏi giao đúng giờ), `extract_facts(text)` gọi `HybridOrderMatcher.match(text)` quét **toàn bộ `mock_orders.json`**, khớp nhầm sang `ORD-1001` (`Bùi Thị An`) hoặc `ORD-1026` (`Huỳnh Hữu Linh`), rồi `conversation_service/src/main.py#L296-L297` khóa nhầm mã đơn đó vào `state.active_order_id`.
3. **Thiếu kiểm tra quyền sở hữu khi nạp `order_data` (`conversation_service/src/main.py#L458-L476`, `#L638-L654`):**
   - Cả `/chat` và `/chat_stream` đều không đối chiếu `order_data["customer_id"] == state.customer_id` và không chặn khi người dùng hỏi thẳng mã `CUST-YYYY` khác với phiên của mình.
4. **Lộ PII qua Prompt LLM (`copilot_draft_engine.py`):**
   - Vì `order_data` sai chủ được truyền thẳng vào prompt, LLM đọc nguyên tên (`Bùi Mai Phong`, `Bùi Thị An`, `Huỳnh Hữu Linh`), SĐT và hành trình giao hàng của người khác.

---

## 7. Hướng giải quyết đề xuất

1. **Gỡ bỏ alias nguy hiểm `CUST-XXXX -> ORD-XXXX`** trong `TelemetryRepository.get_order()`, chỉ tra cứu khớp chính xác `customer_id` (và rà soát đồng bộ mapping `demo-customer` của `Bùi Thị An` nếu được duyệt).
2. **Bổ sung tham số lọc `customer_id`** vào `extract_facts(text, customer_id=...)` và `OrderMatcher.match(text, customer_id=...)` để chỉ tìm đơn trong tập đơn của đúng khách hàng đang hỏi.
3. **Thêm hàm kiểm tra tập trung `verify_order_ownership(order_data, session_customer_id)`** vào `contracts/safety.py` (dùng chung cho cả `conversation_service` và `gateway` fallback):
   - Nếu khách hỏi `CUST-YYYY` không khớp `session_customer_id` hoặc nhập `ORD-XXXX` của người khác -> đặt `order_data = None`, không ghi vào `state.active_order_id`, trả về thông báo bảo mật an toàn (`blocked_unauthorized_order_access`).
4. **Viết test hồi quy IDOR đầy đủ** mô phỏng lại tất cả các ca trong `real_testing.pdf` (hỏi `CUST-*` lạ, hỏi `ORD-*` lạ, hỏi sản phẩm trùng tên).

---

## 8. Các bước triển khai (Milestones)

- [x] **M1 (`[DONE]`):** Chốt phương án đồng bộ dữ liệu mẫu (`demo-customer` <-> `CUST-1001` cho `Bùi Thị An` qua `canonical_customer_ids()` trong `contracts/safety.py`).
- [x] **M2 (`[DONE]`):** Gỡ fallback `CUST-XXXX -> ORD-XXXX` trong `TelemetryRepository.get_order()` và thêm lọc `customer_id` tại SQLite, JSON fallback, `/orders/{identifier}` và `/orders/phone/{phone}`.
- [x] **M3 (`[DONE]`):** Áp dụng `is_order_owned_by_customer()` / `detect_foreign_customer_query()` và bộ lọc `customer_id` tại `fact_extractor.py`, `order_matcher.py`, `input_classifier.py`, `order_tools.py`, `conversation_service/src/main.py`, `gateway/src/main.py`.
- [x] **M4 (`[DONE]`):** Bổ sung bộ test bảo mật/IDOR offline vào `tests/test_module3_orders.py`, `tests/test_guardrails.py`, `tests/test_conversation_service.py` và chạy kiểm thử CI offline.

---

## 9. Chiến lược kiểm thử & Tiêu chí nghiệm thu

- **Lệnh kiểm thử an toàn đã chạy:**
  - `pytest` (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`) cho `tests/test_module3_orders.py`, `tests/test_guardrails.py`, `tests/test_conversation_service.py` và toàn bộ CI offline.
- **Tiêu chí hoàn thành (Definition of Done):**
  - [x] Khách hàng A không bao giờ đọc được hoặc gán được `order_data` của Khách hàng B vào `state.active_order_id` hay prompt LLM.
  - [x] `TelemetryRepository.get_order("CUST-1007", customer_id="demo-customer")` và `CUST-1003` không tự trả về `ORD-1007` hay `ORD-1003`.
  - [x] Toàn bộ CI offline pass, không phát sinh hồi quy.

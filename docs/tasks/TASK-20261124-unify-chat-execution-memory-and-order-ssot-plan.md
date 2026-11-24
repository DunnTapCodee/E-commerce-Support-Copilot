# Kế Hoạch Thực Thi (Task 3/6): Hợp Nhất Luồng `/chat` & `/chat_stream`, Sửa Ghi Nhận Bộ Nhớ Hội Thoại & Đồng Bộ Nguồn Sự Thật Đơn Hàng (SSoT)

> **Trình tự thực thi:** **Bước 3 / 6** — Thực hiện sau **Task 2** (`TASK-20261124-nlu-pipeline-consolidation-and-anti-hardcoding`) để gom gọn tầng điều phối `conversation_service` và dữ liệu liên service.
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261124-unify-chat-execution-memory-and-order-ssot`
- **Tên Task:** `Xóa bỏ trùng lặp code giữa /chat và /chat_stream, sửa lỗi lưu nhầm câu chờ vào bộ nhớ ngữ cảnh hội thoại, chuẩn hóa xuất Continual Learning CSV và đồng bộ Single Source of Truth cho dữ liệu đơn hàng`
- **Thời gian tạo / cập nhật:** `2026-11-24T23:12:00+07:00`
- **Trạng thái Task (`Task Status`):** `NOT_STARTED`
- **Trạng thái triển khai (`Implementation Status`):** `PLANNED`
- **Trạng thái kiểm thử (`Verification Status`):** `NOT_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `PENDING_APPROVAL (Chờ chủ dự án xác nhận triển khai)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. Triệt tiêu ~300 dòng code lặp lại giữa hai endpoint `/api/v1/conversation/chat` và `/api/v1/conversation/chat_stream` trong `services/conversation_service/src/main.py` — hiện đã phát sinh sai lệch thực tế (`/chat_stream` dòng 778 vẫn báo cáo cứng `"Mô hình LLM gpt-oss (Streaming SSE)"` trái với `FR-UI-004`, và dòng 824 quên truyền `computed_summary` vào bước đối soát an toàn đa đơn hàng).
  2. Khắc phục lỗi `MemoryWorker.update_memory_task` đang lưu `agent_response=customer_ack` (câu chờ *"Dạ anh/chị đợi em một xíu..."*) vào `state.turns`, khiến các lượt hỏi kế tiếp mất ngữ cảnh câu trả lời thực tế của nhân viên/Copilot.
  3. Chấm dứt việc tự động ghi nhãn giả `human_action="AUTO_LLM"` vào `data/continual_learning_dataset.csv` ngay lúc mới sinh nháp (trước khi nhân viên CSKH thực hiện `APPROVE` / `EDIT` / `REJECT` theo `PG-004` & `BR-001`).
  4. Khắc phục tình trạng lệch dữ liệu đơn hàng (Split-Brain State) khi `OrderMatcher` / `OrderTools` trong `conversation_service` đọc tĩnh từ `data/mock_orders.json` thay vì lấy trạng thái đã cập nhật (sau khi duyệt hủy đơn / đổi địa chỉ / đổi người nhận) từ SQLite của `telemetry_service`.
- **Kết quả kỳ vọng:**
  - Một hàm hậu xử lý hợp nhất duy nhất (`finalize_copilot_turn`) phục vụ cho cả chế độ thường và SSE streaming, đảm bảo 100% đồng nhất về kiểm tra an toàn, nhãn `components_used`, lưu hàng đợi nháp và ghi log kiểm toán.
  - Lịch sử `state.turns` phản ánh đúng nội dung tư vấn thực tế; bản ghi học liên tục mang trạng thái minh bạch (`PENDING_REVIEW` hoặc cập nhật khi có hành động thật từ nhân viên).
  - Mọi thay đổi đơn hàng được duyệt qua HITL trên `telemetry_service` được phản ánh tức thời vào bộ khớp đơn hàng của `conversation_service`.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `services/conversation_service/src/main.py` (tách mô-đun điều phối hậu xử lý dùng chung để giảm quy mô `main.py` từ ~990 dòng xuống gọn sạch)
  - `services/conversation_service/src/memory/async_worker.py` & `services/conversation_service/src/dialogue_state/sqlite_state_store.py`
  - `services/conversation_service/src/tools/order_tools.py`, `services/conversation_service/src/input_pipeline/order_matcher.py`, `services/conversation_service/src/clients/telemetry_client.py`
  - Tách phần ghi CSV học liên tục thành tiện ích chuẩn thay vì import chéo từ thư mục `scripts/` vào runtime microservice (giữ tương thích ngược cho `scripts/export_continual_learning_dataset.py`)
  - Cập nhật/bổ sung test tại `tests/test_conversation_service.py`, `tests/test_e2e_customer_staff_sync.py`, `tests/test_order_actions_and_proactive_delay.py`
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không thay đổi cấu trúc bảng SQLite hiện có theo cách phá vỡ dữ liệu cũ.
  - Không chỉnh sửa giao diện React (thuộc **Task 4**) hay bộ đánh giá `evaluation/` (thuộc **Task 5**).

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `PG-004`, `BR-001`, `FR-UI-003`, `FR-UI-004`, `FR-DLG-001`, `FR-ORD-001`, `FR-TEL-001`, `FR-TEL-002`, `SC-005` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [SPEC-WF-001 (Copilot End-to-End Workflow)](../specs/copilot-workflow.md)
- **ADR & Kiến trúc:** [Architecture Overview v1 §3.1, §4.1](../architecture/overview.md), [ADR-003](../decisions/ADR-003-vietnam-time-no-12h-offset.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Tái cấu trúc điều phối trung tâm trong `conversation_service`, cập nhật bộ nhớ phiên và luồng đồng bộ dữ liệu đơn hàng liên service — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Giữ nguyên định dạng sự kiện SSE (`event: meta`, `event: token`, `event: done`) và hợp đồng `GatewayResponse` để không ảnh hưởng tới Frontend và Gateway.
  - Bảo toàn hoàn toàn cơ chế che thông tin cá nhân `redact_pii()` và biến môi trường `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT` đã được kiểm chứng trong `TestPrivacyContinualLearningCsvExport`.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án trước khi bắt đầu triển khai.

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Tách `TurnFinalizer` / `OrchestrationHelper` dùng chung cho `/chat` và `/chat_stream`:**
   - Gom toàn bộ các bước: làm sạch tiêu đề nháp (`clean_draft_header`), dựng `grounding_order_data` đầy đủ (`candidates` + `computed_summary`), chạy `evaluate_runtime_safety_envelope`, trích xuất đề xuất thao tác đơn (`_build_pending_order_action`), tính nhãn động `components_used` (dùng đúng `OPENAI_MODEL` thực tế cho cả streaming), đẩy nháp vào `state_store.set_copilot_draft` và tạo `AuditLogCreate` vào một hàm duy nhất.
2. **Chuẩn hóa cập nhật Bộ nhớ Phiên (`state.turns` & `context_summary`):**
   - Khi Copilot mới sinh bản nháp (chưa gửi khách), lưu bản nháp dự kiến vào ngữ cảnh tạm nhưng ngay khi nhân viên gửi phản hồi chính thức qua `POST /api/v1/conversation/message` (`role="agent"`, `is_acknowledgement=False`), cập nhật lượt trả lời thật vào `state.turns` và làm mới `context_summary`. Nhờ đó lượt chat thứ 2 trở đi luôn nắm chính xác nội dung nhân viên vừa tư vấn cho khách.
3. **Minh bạch hóa Continual Learning Export & Gỡ khớp nối chéo `scripts/`:**
   - Chuyển hàm `redact_pii()` và ghi dòng dữ liệu học liên tục vào module dùng chung sạch sẽ (ví dụ `contracts/continual_learning.py` được cả `conversation_service` lẫn `scripts/export_continual_learning_dataset.py` gọi lại), ghi đúng trạng thái `DRAFT_GENERATED` (hoặc chỉ xuất mẫu đạt chuẩn khi nhân viên `APPROVE`/`EDIT` tại telemetry) thay vì gán nhãn sai `"AUTO_LLM"`.
4. **Đồng bộ Nguồn Sự Thật Đơn Hàng (`telemetry_service` -> `OrderMatcher`):**
   - Cho phép `OrderMatcher` nhận danh sách `customer_orders` tươi vừa tải từ `telemetry_client.get_customer_orders(customer_id)` ở đầu lượt chat để so khớp tên sản phẩm/mã vận đơn/SĐT trực tiếp trên dữ liệu mới nhất của khách hàng; chỉ đọc `data/mock_orders.json` khi `telemetry_service` ngoại tuyến.

---

## 7. Các bước triển khai (Milestones)

- [ ] **M1 (`[PLANNED]`):** Trích xuất bộ hậu xử lý dùng chung cho `/chat` và `/chat_stream`, xóa bỏ chuỗi `"Mô hình LLM gpt-oss"` và đồng bộ `grounding_order_data` có đủ `computed_summary`.
- [ ] **M2 (`[PLANNED]`):** Cập nhật `MemoryWorker` và `persist_chat_message` để `state.turns` & `context_summary` lưu câu trả lời thật của nhân viên/Copilot thay vì câu chờ `customer_ack`.
- [ ] **M3 (`[PLANNED]`):** Tách tiện ích `continual_learning` khỏi `scripts/` (giữ tương thích ngược cho script CLI và test quyền riêng tư) và sửa nhãn hành động trung thực.
- [ ] **M4 (`[PLANNED]`):** Cấp danh sách đơn hàng sống từ `telemetry_service` cho `OrderMatcher` (chống lệch trạng thái sau khi hủy/đổi địa chỉ) và bổ sung test kiểm chứng toàn diện.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn dự kiến chạy (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`):**
  - `python -m pytest tests/test_contracts_and_integration.py tests/test_conversation_service.py tests/test_e2e_customer_staff_sync.py tests/test_order_actions_and_proactive_delay.py tests/test_multi_order_disambiguation.py -v`
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `NOT_YET_RUN`
  - `Result:` `NOT_YET_RUN`
  - `Limitations:` `Chưa thực thi (Task đang ở trạng thái PLANNED).`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Thực hiện sau **Task 1** và **Task 2** để tránh xung đột hợp nhất trên `services/conversation_service/src/main.py`.
- **Điểm nghẽn hiện tại:** Chờ chủ dự án phê duyệt kế hoạch.

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [ ] `/chat` và `/chat_stream` dùng chung 100% logic kiểm định an toàn, trích xuất đề xuất thao tác đơn, lưu nháp và tạo nhãn `components_used` (không còn chuỗi `"gpt-oss"` cứng ở chế độ streaming).
- [ ] Ở hội thoại nhiều lượt, sau khi nhân viên duyệt gửi câu trả lời ở Lượt 1, `state.turns` và `context_summary` ở Lượt 2 chứa nội dung câu trả lời thật chứ không phải câu chờ.
- [ ] Sau khi nhân viên duyệt đổi địa chỉ hoặc hủy đơn trên `telemetry_service`, truy vấn tiếp theo tìm đơn theo tên sản phẩm qua `OrderMatcher` nhận được ngay trạng thái/địa chỉ mới nhất (không đọc đè bản cũ từ `mock_orders.json`).
- [ ] `conversation_service` không còn import ngược vào thư mục `scripts/`; toàn bộ bài kiểm thử hợp đồng & quyền riêng tư (`TestPrivacyContinualLearningCsvExport`) pass 100%.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-24T23:12:00+07:00` | Lập kế hoạch Task 3 tách riêng việc hợp nhất điều phối, sửa bộ nhớ lượt chat & đồng bộ SSoT đơn hàng | Phát hiện lệch code giữa `/chat` và `/chat_stream` (`main.py#L778`, `#L824`), lưu nhầm `customer_ack` vào `state.turns`, và khớp nối chéo sang `scripts/` + `mock_orders.json` | `Observed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Xác định đầy đủ các điểm lệch điều phối/dữ liệu và lập kế hoạch (`PLANNED`).
- **Hành động tiếp theo:** Triển khai sau khi hoàn thành **Task 2**.
- **Tham chiếu:** [overview.md](../architecture/overview.md), [copilot-workflow.md](../specs/copilot-workflow.md), [verification.md](../development/verification.md).

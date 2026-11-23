# Kế Hoạch Thực Thi: Xử Lý Race Condition Ghi Đè Bản Nháp (Hàng Đợi Draft Theo Tương Tác)

> **Tài liệu nguồn:** `docs/new_tasks/real_testing.pdf` (Note Trang 4: *"KH hỏi câu hỏi 1, chatbot phân tích chưa xong, hỏi câu 2 -> tự chuyển sang câu 2 và drop luôn bản nháp câu 1"*)
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-session-draft-queue-race-condition-fix`
- **Tên Task:** `Thay thế cột copilot_draft đơn lẻ bằng hàng đợi bản nháp theo interaction_id để không làm mất bản nháp câu hỏi trước`
- **Thời gian tạo / cập nhật:** `2026-11-23T17:34:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_OFFLINE`
- **Trạng thái phê duyệt:** `APPROVED (Chủ dự án xác nhận triển khai Đợt 1 ngày 2026-11-23)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:** Khi khách hàng gửi liên tiếp nhiều câu hỏi trước lúc nhân viên kịp duyệt bản nháp câu 1, hệ thống không được ghi đè làm mất bản nháp câu 1 và giao diện nhân viên không được tự nhảy dòng *"Đang trả lời câu hỏi của..."* khiến nhân viên mất dấu hoặc duyệt nhầm.
- **Kết quả kỳ vọng:**
  - Các bản nháp Copilot đang chờ duyệt được lưu theo từng `interaction_id` trong hàng đợi FIFO (`copilot_draft_queue`) thay vì 1 ô đơn lẻ trên `conversation_sessions`.
  - Nhân viên trên Staff Workbench xem và duyệt lần lượt từng bản nháp (hoặc thấy badge báo có thêm bản nháp mới đang chờ) mà không bị mất bản nháp cũ hay mất phần nội dung đang gõ dở.
  - Vẫn giữ tương thích ngược với các trường `copilotDraft` / `copilotResponse` hiện tại trong giai đoạn chuyển tiếp.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (In Scope):**
  - `services/conversation_service/src/dialogue_state/sqlite_state_store.py` (thêm bảng `copilot_draft_queue` bằng `CREATE TABLE IF NOT EXISTS` và các hàm đọc/duyệt theo FIFO)
  - `services/conversation_service/src/main.py` (`/chat`, `/chat_stream`, `/session/{id}/details`, và endpoint duyệt/bỏ qua từng draft)
  - `services/gateway/src/main.py`, `frontend/src/lib/api-client.ts`, `frontend/src/types/index.ts`
  - `frontend/src/features/chat/ChatView.tsx` & `frontend/src/features/staff/StaffCustomerManagerView.tsx` (hiển thị hàng đợi draft, không xóa nội dung nhân viên đang sửa khi polling)
  - Test đồng bộ & tải (`tests/test_e2e_customer_staff_sync.py`, `tests/test_conversation_service.py`)
- **Ngoài phạm vi (Non-Goals):**
  - Đổi toàn bộ cơ chế polling sang WebSocket (giữ kiến trúc polling + SSE hiện tại, giải quyết dứt điểm race condition ở DB và UI state)

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-DLG-001`, `FR-UI-001`, `FR-TEL-001` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [Copilot Workflow Spec (`SPEC-WF-001`)](../specs/copilot-workflow.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Mở rộng schema SQLite bền vững và hợp đồng API giữa `conversation_service`, `gateway`, `frontend` — xem [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md))
- **Ràng buộc cứng:**
  - Migration SQLite phải mang tính bổ sung (`CREATE TABLE IF NOT EXISTS`), tuyệt đối không phá hủy dữ liệu hiện có trong `conversation_sessions` & `conversation_turns`.
  - Giữ an toàn song song chế độ SQLite WAL (`test_load_concurrency.py`).
  - Không bao giờ ghi đè `editedDraft` nhân viên đang gõ dở trên UI khi polling nền nhận thêm draft của câu 2.
- **Điểm cần duyệt:** Chốt phương án UX khi câu 2 về trong lúc nhân viên đang xem câu 1 (khóa hiển thị câu 1 kèm badge *"Còn N bản nháp tiếp theo đang chờ"* hay cho tab chuyển đổi qua lại giữa các bản nháp chờ).

---

## 6. Nguyên nhân gốc đã xác minh trong code (`Observed`)

1. Bảng `conversation_sessions` trong `sqlite_state_store.py` hiện chỉ có **1 cặp cột duy nhất** (`copilot_draft`, `copilot_response_json`) cho mỗi `session_id`.
2. Khi khách gửi Câu 1 rồi gửi tiếp Câu 2 lúc Câu 1 chưa được duyệt, cả `/chat` và `/chat_stream` đều gọi `state_store.set_copilot_draft(session_id, draft, meta)` (`conversation_service/src/main.py#L620`, `#L748`), ghi đè thẳng lên bản nháp của Câu 1.
3. UI Staff Workbench poll `/session/{id}/details` định kỳ ~2.5s và hiển thị `findRepliedCustomerQuestion` + `copilotDraft` mới nhất, khiến giao diện tự nhảy sang Câu 2 và mất hoàn toàn bản nháp Câu 1.

---

## 7. Hướng giải quyết đề xuất

1. **Thêm bảng hàng đợi `copilot_draft_queue` (`sqlite_state_store.py`):**
   - Schema: `(id, session_id, interaction_id, customer_question, draft_text, response_json, status, created_at)` với `status IN ('PENDING', 'APPROVED', 'DISMISSED')`.
   - Khi `/chat` hoặc `/chat_stream` sinh xong nháp -> chèn vào hàng đợi với `status='PENDING'`, đồng thời cập nhật `conversation_sessions.copilot_draft` luôn trỏ vào **bản nháp `PENDING` cũ nhất (đầu hàng đợi FIFO)** để tương thích ngược.
   - Khi nhân viên bấm Duyệt/Gửi hoặc Bỏ qua -> chỉ đánh dấu đúng `interaction_id` đó là `APPROVED`/`DISMISSED`, và tự đẩy bản nháp `PENDING` kế tiếp (nếu có) lên đầu.
2. **Cập nhật API & UI (`ChatView.tsx`, `StaffCustomerManagerView.tsx`):**
   - `/session/{id}/details` trả thêm mảng `pending_drafts`.
   - UI giữ nguyên `activeDraftInteractionId` & nội dung `editedDraft` đang thao tác, hiển thị thêm nhãn số lượng bản nháp đang chờ để nhân viên xử lý tuần tự không sót câu nào.

---

## 8. Các bước triển khai (Milestones)

- [x] **M1 (`[DONE]`):** Chốt phương án khóa bản nháp đang thao tác trên UI (`activeDraftInteractionId`) kèm thanh chọn hàng đợi FIFO.
- [x] **M2 (`[DONE]`):** Triển khai bảng `copilot_draft_queue` và cơ chế đồng bộ head FIFO trong `sqlite_state_store.py`.
- [x] **M3 (`[DONE]`):** Cập nhật `conversation_service/src/main.py`, `frontend/src/types/index.ts`, `api-client.ts`, và `ChatView.tsx`.
- [x] **M4 (`[DONE]`):** Bổ sung test `test_fifo_draft_queue_prevents_overwrite_race_condition` trong `tests/test_e2e_customer_staff_sync.py` và chạy lại toàn bộ CI + `tsc --noEmit` + `npm run test:unit`.

---

## 9. Chiến lược kiểm thử & Tiêu chí nghiệm thu

- **Lệnh kiểm thử an toàn đã chạy:**
  - `pytest` (`DISABLE_EXTERNAL_LLM=true`) cho `tests/test_e2e_customer_staff_sync.py` và `tests/test_load_concurrency.py`, kèm `npx tsc --noEmit` và `npm run test:unit`.
- **Tiêu chí hoàn thành (Definition of Done):**
  - [x] Gửi 2+ câu hỏi liên tiếp không làm mất bản nháp câu trước.
  - [x] Duyệt câu 1 chỉ đóng bản nháp câu 1 và giữ nguyên / tự đẩy bản nháp câu 2 lên đầu hàng đợi.
  - [x] Không phát sinh lỗi `database is locked` trong `test_load_concurrency.py`.

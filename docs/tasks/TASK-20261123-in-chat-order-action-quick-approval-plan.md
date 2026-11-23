# Kế Hoạch Thực Thi: Tiếp Nhận Yêu Cầu Đơn Hàng Trong Chat & Giao Diện "Duyệt Yêu Cầu Nhanh"

> **Tài liệu nguồn:** `docs/new_tasks/recommend.txt` (Mục 1: *"Tiếp nhận yêu cầu hủy đơn, đổi địa chỉ, đổi thông tin người nhận, trả hàng ngay trong khung chat + giao diện duyệt yêu cầu nhanh kèm lý do"*)
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-in-chat-order-action-quick-approval`
- **Tên Task:** `Nhận diện yêu cầu thay đổi đơn/trả hàng trong chat và bổ sung thẻ "Duyệt yêu cầu nhanh" kèm diff và audit log cho nhân viên`
- **Thời gian tạo / cập nhật:** `2026-11-23T18:00:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_OFFLINE`
- **Trạng thái phê duyệt:** `APPROVED (Chủ dự án xác nhận triển khai Đợt 2 ngày 2026-11-23)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:** Cho phép khách hàng gửi yêu cầu tác nghiệp ngay trong đoạn chat (hủy đơn, đổi địa chỉ giao, đổi SĐT/tên người nhận, yêu cầu trả hàng) mà **không để LLM tự sửa DB**, thay vào đó hệ thống tách thành đề xuất có cấu trúc và bật khung **"Duyệt yêu cầu nhanh"** trên màn hình nhân viên: hiển thị thay đổi trước–sau (diff), bấm **Duyệt & Cập nhật hệ thống** hoặc **Từ chối kèm lý do**.
- **Kết quả kỳ vọng:**
  - Contract `OrderActionProposal` và `OrderActionDecisionRequest` trong `contracts/schemas.py` & `frontend/src/types/index.ts`.
  - Luật kiểm tra điều kiện hợp lệ theo trạng thái đơn (VD: đơn đã `Delivered` hoặc `Cancelled` không cho đổi địa chỉ/hủy; bắt buộc qua kiểm tra quyền sở hữu đơn từ `TASK-20261123-customer-order-isolation-idor-fix`).
  - API lưu đề xuất chờ duyệt và thực thi cập nhật nguyên tử (atomic) trên SQLite + vô hiệu hóa `OrderLRUCache` + ghi audit log khi nhân viên bấm Duyệt/Từ chối.
  - Card UI **"Duyệt yêu cầu nhanh"** tích hợp ngay trong `ChatView` / `StaffCustomerManagerView`.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (In Scope):**
  - `contracts/schemas.py` (`OrderActionProposal`, `OrderActionDecisionRequest`)
  - `services/conversation_service/src/` (trích xuất trường thay đổi, kiểm tra điều kiện hợp lệ, đính kèm `pending_action` vào `GatewayResponse` mà không ghi DB)
  - `services/telemetry_service/src/` (bảng SQLite `order_action_requests` + endpoint duyệt/từ chối `/orders/{order_id}/actions` cập nhật bảng `orders`)
  - `services/gateway/src/` (route proxy) & `frontend/` (thẻ Duyệt yêu cầu nhanh trong chat nhân viên)
  - Bộ test unit + tích hợp offline (`tests/`)
- **Ngoài phạm vi (Non-Goals):**
  - Để LLM/chatbot tự động cập nhật bảng `orders` không qua nhân viên duyệt (bị cấm tuyệt đối theo nguyên tắc an toàn)
  - Kết nối webhook với hệ thống đơn vị vận chuyển / cổng thanh toán thật bên ngoài

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-ORD-001`, `FR-UI-001`, `SC-001`, `SC-007` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [Copilot Workflow Spec (`SPEC-WF-001`)](../specs/copilot-workflow.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R3` (Chỉnh sửa bản ghi đơn hàng, thông tin người nhận/địa chỉ, và trạng thái hủy/trả hàng — xem [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md))
- **Ràng buộc cứng:**
  - **Bắt buộc Human-in-the-Loop:** Luồng `/chat` hay `/query` chỉ được phép tạo `OrderActionProposal` trạng thái `PENDING`, chỉ khi nhân viên gửi quyết định `APPROVE` kèm `performed_by` mới được cập nhật bảng `orders`.
  - **Điều kiện tiên quyết (Dependency):** Phải áp dụng kèm cơ chế cô lập chủ đơn (`TASK-20261123-customer-order-isolation-idor-fix`) để Khách A không thể tạo yêu cầu sửa/hủy đơn của Khách B.
  - Từ chối yêu cầu (`REJECT`) bắt buộc phải nhập lý do không rỗng (`HTTP 422`), tương tự `SC-007`.
- **Điểm cần duyệt:** Chủ dự án chốt danh sách trường được phép đề xuất sửa (`shipping_address`, `receiver_name`, `phone`, `cancel_order`, `return_product`) và quy tắc theo từng `order_status` (`Processing` vs `Shipping` vs `Delivered`).

---

## 6. Hướng giải quyết đề xuất

1. **Tạo Đề xuất Thay đổi (Không ghi DB ở bước chat):**
   - Khi `conversation_service` phát hiện ý định `cancel_order`, `return_product` hoặc đổi địa chỉ/người nhận cho đơn hàng đã xác minh đúng chủ sở hữu -> sinh `OrderActionProposal` gồm `action_type`, `order_id`, `before_values`, `proposed_values`, `eligible`, `ineligibility_reason`, `status="PENDING"`.
2. **Lưu trữ & Thực thi khi Nhân viên duyệt (`telemetry_service` + `gateway`):**
   - Lưu đề xuất vào bảng `order_action_requests` (SQLite WAL).
   - Cung cấp endpoint `POST /api/v1/copilot/orders/actions/{action_id}/decide` nhận `{decision: "APPROVE" | "REJECT", reason, performed_by}`:
     - Nếu `APPROVE`: kiểm tra lại trạng thái `order_status` hiện tại trong transaction, cập nhật `orders`, xóa cache `OrderLRUCache`, ghi audit log, và trả nội dung xác nhận để gửi vào phiên chat.
     - Nếu `REJECT`: bắt buộc có `reason`, lưu quyết định và gợi ý mẫu câu giải thích lịch sự kèm lý do để gửi cho khách.
3. **Thẻ Duyệt Yêu Cầu Nhanh trên UI (`frontend/`):**
   - Hiển thị khung diff `Giá trị cũ -> Giá trị mới` ngay cạnh khung chat nhân viên với 2 nút **Duyệt & Cập nhật** / **Từ chối (nhập lý do)**.

---

## 7. Các bước triển khai (Milestones)

- [x] **M1 (`[DONE]`):** Chốt ma trận điều kiện hợp lệ theo `order_status` trong `contracts/order_actions.py` (`Processing`/`Payment_Failed` cho đổi địa chỉ/người nhận; chưa `Delivered`/`Cancelled`/`Shipping` cho hủy đơn; `Delivered`/`Return_Approved` cho trả hàng).
- [x] **M2 (`[DONE]`):** Định nghĩa DTO Pydantic & TypeScript (`OrderActionProposal`, `OrderActionDecisionRequest` trong `contracts/schemas.py` và `frontend/src/types/index.ts`).
- [x] **M3 (`[DONE]`):** Triển khai bảng `order_action_requests`, endpoint `/orders/actions/propose`, `/orders/actions`, `/orders/actions/{id}/decide` + invalidation `OrderLRUCache` ở `telemetry_service`, proxy ở `gateway`, và trích xuất `pending_action` ở `conversation_service` (gắn bảo vệ chủ đơn).
- [x] **M4 (`[DONE]`):** Xây dựng thẻ "Duyệt yêu cầu nhanh" trong `ChatView.tsx` + `tests/test_order_actions_and_proactive_delay.py` (`npx tsc --noEmit`, `npm run test:unit`, `pytest`).

---

## 8. Chiến lược kiểm thử & Tiêu chí nghiệm thu

- **Lệnh kiểm thử an toàn đã chạy:**
  - `tests/test_order_actions_and_proactive_delay.py` (`DISABLE_EXTERNAL_LLM=true`) cùng toàn bộ bộ test CI offline + `npx tsc --noEmit` + `npm run test:unit`.
- **Tiêu chí hoàn thành (Definition of Done):**
  - [x] Không có con đường nào để LLM tự sửa dữ liệu đơn hàng khi chưa có nhân viên duyệt.
  - [x] Nhân viên xem được diff trước–sau và Duyệt/Từ chối kèm lý do trực tiếp trên UI.
  - [x] Toàn bộ test CI offline + `npx tsc --noEmit` + `npm run test:unit` pass.

# Kế Hoạch Thực Thi (Task 4/6): Mô-đun Hóa Giao Diện `ChatView`, Xóa Phân Loại Từ Khóa Dưới Trình Duyệt & Chuẩn Hóa Hiển Thị Lỗi Kiểm Định

> **Trình tự thực thi:** **Bước 4 / 6** — Thực hiện sau các task Backend lõi (**Task 1–3**), hoàn toàn độc lập trong phạm vi `frontend/` để chuẩn bị nền tảng sạch cho kiểm thử tự động UI ở **Task 6**.
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261124-frontend-chat-modularization-and-state-cleanup`
- **Tên Task:** `Tách nhỏ God Component ChatView.tsx (~2.530 dòng) thành các hooks/sub-components rõ trách nhiệm, gỡ bỏ bộ if/else đoán từ khóa câu đệm ở trình duyệt và chuẩn hóa hiển thị lỗi ERROR/WARNING trên EvaluationDashboardView`
- **Thời gian tạo / cập nhật:** `2026-11-24T23:12:00+07:00`
- **Trạng thái Task (`Task Status`):** `NOT_STARTED`
- **Trạng thái triển khai (`Implementation Status`):** `PLANNED`
- **Trạng thái kiểm thử (`Verification Status`):** `NOT_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `PENDING_APPROVAL (Chờ chủ dự án xác nhận triển khai)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. Giải quyết cấu trúc "God Component" của `frontend/src/features/chat/ChatView.tsx` (~2.530 dòng trộn lẫn quản lý danh sách khách hàng, polling SQLite 2.5s, SSE streaming, khóa bản nháp FIFO, duyệt nhanh thao tác đơn hàng và hiển thị chính sách) — nguyên nhân gốc gây khó bảo trì, khó viết unit test và dễ nảy sinh lỗi tranh chấp trạng thái (race-condition).
  2. Xóa bỏ khối `if / else if` bắt từ khóa tiếng Việt cứng (bao gồm cả `ronaldo`, `thời tiết`, `phương trình`...) tại `ChatView.tsx#L1003-L1020` đang tự sinh câu phản hồi đệm dưới trình duyệt; chuyển sang dùng thống nhất phản hồi từ `/api/v1/copilot/fast_ack` (kèm 1 câu chờ lịch sự chung duy nhất khi chờ mạng).
  3. Sửa lỗi hiển thị trên `EvaluationDashboardView.tsx` (hiện đang tô màu xám trung tính `neutral` cho các module bị crash `status === 'ERROR'` và dùng chuỗi điều kiện nối tạm để lọc danh mục `category`).
- **Kết quả kỳ vọng:**
  - `ChatView.tsx` gọn nhẹ, chỉ đóng vai trò bố cục (layout container) kết nối các custom hooks (`useCopilotSessions`, `useCopilotStreaming`) và các component con chuyên biệt, giữ nguyên 100% tính năng và giao diện người dùng hiện tại.
  - Không còn logic đoán ý định/từ khóa nghiệp vụ bị nhân bản dưới tầng trình duyệt.
  - Mọi trạng thái `ERROR` / `FAILED` / `WARNING` trên Tab Kiểm định hiển thị đúng mức độ cảnh báo trực quan (đỏ/vàng) và lọc chính xác theo danh mục chuẩn.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `frontend/src/features/chat/ChatView.tsx` và các module tách ra trong `frontend/src/features/chat/` (`hooks/`, `components/`)
  - `frontend/src/features/evaluation/EvaluationDashboardView.tsx`
  - `frontend/src/types/index.ts` (bổ sung kiểu dữ liệu chặt chẽ cho `EvaluationSummary`, `EvaluationModule`, `PendingDraftItem` thay cho `any`)
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không thay đổi thiết kế mỹ thuật/bố cục UX đã được duyệt của màn hình Nhân viên và Khách hàng.
  - Không đụng tới giao diện cũ Streamlit (`services/ui_service/` — giữ nguyên theo `ADR-001`).
  - Việc cài đặt Vitest / viết bộ test tự động cho các hooks & components mới được tách riêng ở **Task 6**.

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `PG-002`, `FR-UI-001`, `FR-UI-003`, `FR-UI-004` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [SPEC-WF-001](../specs/copilot-workflow.md)
- **ADR & Kiến trúc:** [ADR-001 (Primary UI React, Legacy Streamlit)](../decisions/ADR-001-primary-ui-react-legacy-streamlit.md), [AGENTS.md](../../AGENTS.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R1`–`R2` (Tái cấu trúc nội bộ thư mục `frontend/src/` không đổi hợp đồng API backend — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Bảo toàn tuyệt đối toàn bộ các bản vá chống lỗi giao diện đã thực hiện trước đó: (1) không ghi đè ô soạn thảo khi nhân viên đang gõ (`isDraftDirty`), (2) khóa hàng đợi nháp FIFO theo `activeDraftInteractionId`, (3) khóa chống gọi trùng luồng sinh nháp (`inFlightSessionsRef`) và chống lặp câu phản hồi đệm (`hasExistingAck`).
  - Loại bỏ kiểu `any` lỏng lẻo ở các props/state mới tách; `npx tsc --noEmit` và `npm run build` phải sạch lỗi 100%.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án trước khi triển khai.

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Phân tách `ChatView` theo kiến trúc Hooks + Presentational Components:**
   - **Hooks (`frontend/src/features/chat/hooks/`):**
     - `useSessionPollingSync.ts`: Quản lý tải danh sách phiên chat, đồng bộ định kỳ 2.5s từ SQLite mà không đè lên bản nháp đang chỉnh sửa (`isDraftDirty`).
     - `useCopilotInference.ts`: Quản lý luồng SSE streaming (`onMeta`, `onToken`, `onDone`, `onError`), khóa chống chạy trùng theo phiên (`inFlightSessionsRef`), và khử trùng lặp câu đệm / bản nháp hàng đợi.
   - **Components (`frontend/src/features/chat/components/`):**
     - `CustomerSessionSidebar.tsx` (Cột 1: chọn khách hàng, tìm kiếm, quản lý phiên chat).
     - `ConversationStreamPanel.tsx` (Cột 2: luồng tin nhắn, trích dẫn câu hỏi trả lời, thanh nhập liệu & chuyển chế độ).
     - `CopilotWorkbenchPanel.tsx` (Cột 3: hàng đợi nháp FIFO, trình soạn thảo/duyệt nháp, thẻ duyệt nhanh thao tác đơn `OrderQuickApprovalCard`, chẩn đoán pipeline & danh sách đơn hàng của khách).
     - `PolicyViewerModal.tsx` & `CustomerOrdersDrawer.tsx`.
2. **Chuẩn hóa sinh câu phản hồi đệm (`fast_ack`) ở chế độ giả lập khách hàng:**
   - Khi gửi tin nhắn giả lập khách hàng có bật tự động gọi Copilot, gọi `apiClient.getFastAck()` (hoặc hiển thị câu đệm trung tính ngắn gọn trong lúc chờ rồi cập nhật theo `customer_acknowledgement` từ sự kiện `meta` đầu tiên của SSE chỉ sau vài chục ms), xóa hoàn toàn 20 dòng `if/else` bắt từ khóa cứng ở client.
3. **Sửa hiển thị trạng thái trên `EvaluationDashboardView.tsx`:**
   - Hiển thị `<Badge variant="danger">ERROR</Badge>` cho `mod.status === 'ERROR'`, `<Badge variant="warning">WARNING</Badge>` cho `mod.status === 'WARNING'`, và hiển thị rõ thông báo `mod.error` ngay bên trong thẻ module khi bị lỗi để kỹ sư nhận biết tức thì.
   - Định nghĩa kiểu TypeScript `EvaluationRunReport` chặt chẽ trong `frontend/src/types/index.ts`.

---

## 7. Các bước triển khai (Milestones)

- [ ] **M1 (`[PLANNED]`):** Bổ sung các interface TypeScript đầy đủ vào `frontend/src/types/index.ts` và tách 2 custom hooks (`useSessionPollingSync`, `useCopilotInference`) giữ nguyên toàn bộ bất biến chống race-condition.
- [ ] **M2 (`[PLANNED]`):** Tách 3 cột giao diện và các modal/card con ra `frontend/src/features/chat/components/`, rút gọn `ChatView.tsx` và xóa khối `if/else` đoán từ khóa câu đệm ở trình duyệt.
- [ ] **M3 (`[PLANNED]`):** Cập nhật `EvaluationDashboardView.tsx` hiển thị chính xác trạng thái `ERROR` / `WARNING`, chi tiết lỗi module và đồng bộ bộ lọc danh mục.
- [ ] **M4 (`[PLANNED]`):** Kiểm tra biên dịch TypeScript (`tsc --noEmit`), đóng gói production (`vite build`) và chạy unit test helper hiện có.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn dự kiến chạy:**
  - `npm --prefix frontend run test:unit`
  - `npm --prefix frontend run build`
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `NOT_YET_RUN`
  - `Result:` `NOT_YET_RUN`
  - `Limitations:` `Chưa thực thi (Task đang ở trạng thái PLANNED; kiểm thử tự động mức component sẽ được bổ sung ngay ở Task 6).`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Có thể chạy độc lập ở tầng UI, nhưng theo trình tự tổng thể thực hiện ở Bước 4 sau khi các hợp đồng Backend (Task 1–3) đã ổn định.
- **Điểm nghẽn hiện tại:** Chờ chủ dự án phê duyệt kế hoạch.

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [ ] `ChatView.tsx` giảm xuống dưới ~350 dòng (chỉ làm nhiệm vụ ghép nối layout & truyền state từ hooks sang sub-components), mỗi file con có trách nhiệm đơn nhất rõ ràng để dễ dàng gắn unit/component test ở **Task 6**.
- [ ] Không còn đoạn `if/else` bắt từ khóa tiếng Việt (`hủy`, `ronaldo`, `thời tiết`...) để chế câu đệm trong mã nguồn Frontend.
- [ ] Trên `EvaluationDashboardView.tsx`, bất kỳ module nào trả về `status: "ERROR"` đều hiện huy hiệu đỏ cảnh báo và bóc tách rõ thông điệp lỗi `mod.error`.
- [ ] `npx tsc --noEmit`, `npm run build` và `npm run test:unit` pass 100% không có lỗi hay cảnh báo kiểu dữ liệu.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-24T23:12:00+07:00` | Lập kế hoạch Task 4 tách riêng phần mô-đun hóa Frontend & chuẩn hóa hiển thị lỗi | `ChatView.tsx` hiện dài >2.500 dòng gây khó test tự động; `EvaluationDashboardView.tsx#L527` đang gán badge xám `neutral` cho module bị `ERROR` | `Observed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Thiết kế phân rã hooks/components cho `ChatView` và lập kế hoạch (`PLANNED`).
- **Hành động tiếp theo:** Triển khai sau **Task 3**, làm tiền đề trực tiếp cho việc viết Frontend Component Tests ở **Task 6**.
- **Tham chiếu:** [ADR-001](../decisions/ADR-001-primary-ui-react-legacy-streamlit.md), [REPO_GUIDE.md](../agent/REPO_GUIDE.md), [verification.md](../development/verification.md).

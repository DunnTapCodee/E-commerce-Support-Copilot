# Kế Hoạch & Xử Lý Lỗi: Polling 2.5s Ghi Đè Nội Dung Nhân Viên Đang Chỉnh Sửa Bản Nháp

> **Nguồn báo cáo:** Test trực tiếp trên giao diện Staff `/staff` (`http://localhost:15173/staff`): khi nhân viên bấm **Chỉnh sửa** bản nháp Copilot, nội dung gõ bị nhảy giật ngược về bản nháp gốc sau vài giây.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-draft-editor-polling-overwrite-fix`
- **Tên Task:** `Bảo toàn activeDraftInteractionId và cờ isDraftDirty trong chu kỳ polling 2.5s của ChatView để không ghi đè nội dung nhân viên đang sửa`
- **Thời gian tạo / cập nhật:** `2026-11-23T20:39:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_TYPECHECK_AND_UNIT`

---

## 2. Nguyên nhân gốc đã xác minh trong `frontend/src/features/chat/ChatView.tsx`

1. Trong `syncSessionFromSqlite()` (`ChatView.tsx#L472-L485`), khi map lại `dbSessions` từ API `/sessions`, object trả về đã **bỏ quên không sao chép `activeDraftInteractionId` và `pendingDrafts`** từ `prevSess`.
2. Hậu quả là cứ mỗi **2.5 giây**, `s.activeDraftInteractionId` bị reset về `undefined`, làm biểu thức kiểm tra `isSameLocked` luôn trả `false` → nhánh `else` ép `editedDraft` quay ngược về `activeItem.copilotDraft` (bản gốc từ SQLite).
3. Ngoài ra:
   - Chuyển tab `Xem bản thảo` ↔ `Chỉnh sửa` (`draftMode`) kích hoạt lại `useEffect` chạy `syncSessionFromSqlite(false)`.
   - Thiếu cờ `isDraftDirty` khiến nếu nhân viên xóa trắng ô sửa để gõ lại hoặc chuyển qua xem trích dẫn rồi quay lại gửi, nội dung vừa sửa vẫn có thể bị reset.

---

## 3. Thay đổi đã thực hiện (`frontend/src/features/chat/ChatView.tsx`)

- Thêm `isDraftDirty?: boolean` vào `ConversationSession`, bật `isDraftDirty: true` trong `handleUpdateDraft()` và reset `false` khi duyệt gửi (`handleApproveDraft`), bỏ qua (`handleDismissDraft`), hoặc chọn item khác trong hàng đợi (`handleSelectQueuedDraft`).
- Bảo toàn `isDraftDirty`, `activeDraftInteractionId`, `pendingDrafts` khi merge `dbSessions` trong cả `loadBackendSessions()` và `syncSessionFromSqlite()`.
- Tách `draftMode` ra khỏi dependency array của `useEffect` polling 2.5s để việc chuyển tab Xem/Sửa không tự kích hoạt overwrite từ server.

---

## 4. Kiểm định & Trạng thái

- [x] `npx tsc --noEmit` (kiểm tra TypeScript toàn frontend) → exit `0`.
- [x] `npm run test:unit` → `4/4 passed`.
- **Gợi ý kiểm thử tay trên trình duyệt:** Vào `http://localhost:15173/staff` (Vite HMR tự cập nhật), bấm **Chỉnh sửa** bản nháp, gõ thay đổi bất kỳ và chờ > 5 giây (qua 2 chu kỳ poll) → chữ bạn gõ phải giữ nguyên 100%, không bị giật về bản gốc.

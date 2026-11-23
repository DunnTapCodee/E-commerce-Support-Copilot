# Kế Hoạch Thực Thi: Gom Cụm Sự Vụ Diện Rộng, Tác Tử Quét Đơn Trễ > 3 Ngày & Chuẩn Hóa Ngày Đơn Hàng

> **Tài liệu nguồn:** `docs/new_tasks/recommend.txt` (Mục 2, Mục 3 và Mục 4)
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-incident-clustering-and-proactive-delay-agent`
- **Tên Task:** `Xây dựng dashboard gom nhóm sự vụ diện rộng, tác tử quét đơn giao trễ > 3 ngày kèm voucher 30k giả lập và chuẩn hóa ngày mock_orders`
- **Thời gian tạo / cập nhật:** `2026-11-23T18:00:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_OFFLINE`
- **Trạng thái phê duyệt:** `APPROVED (Chủ dự án xác nhận triển khai Đợt 2 ngày 2026-11-23)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. **Chuẩn hóa ngày đơn hàng (`recommend.txt` #4):** Chỉnh lại dữ liệu ngày giao dự kiến trong `data/mock_orders.json` (hoặc cấu hình ngày tham chiếu làm việc cho môi trường demo/eval) để tránh việc gần như toàn bộ đơn `Shipping` cũ bị coi là trễ > 3 ngày so với `get_vn_today()`, chỉ để chủ đích một số case trễ > 3 ngày để demo/test.
  2. **Tác tử chủ động quét đơn trễ > 3 ngày (`recommend.txt` #3):** Thêm tác tử quét DB đơn hàng: đơn nào đang `Shipping` mà trễ > 3 ngày thì chủ động gửi thông báo xin lỗi kèm voucher giả lập `30.000 VNĐ` (idempotent — chống gửi trùng nhiều lần cho cùng 1 đơn).
  3. **Gom cụm sự vụ diện rộng (`recommend.txt` #2):** Tự động gom các câu hỏi/khiếu nại giống nhau phát sinh đồng loạt trong cùng khung thời gian (VD: nhiều khách phản ánh giao chậm do bão/thời tiết xấu) lên một Dashboard sự vụ để nhân viên xử lý hàng loạt hoặc phát thông báo chung.
- **Kết quả kỳ vọng:**
  - Trường ngày giao chuẩn hóa `promised_delivery_date` (`YYYY-MM-DD`) trong `mock_orders.json` (kèm tùy chọn `DELAY_REFERENCE_DATE` riêng cho tác tử demo mà không ảnh hưởng giờ thật `ADR-003`).
  - Endpoint & giao diện Dashboard gom nhóm sự vụ hàng loạt.
  - Tác tử quét trễ đơn có sổ theo dõi chống cấp trùng voucher và tùy chọn duyệt hàng loạt / bật tắt rõ ràng.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (In Scope):**
  - `data/mock_orders.json` (bổ sung/chuẩn hóa ngày giao — **chờ chủ dự án duyệt**)
  - `services/telemetry_service/src/` (truy vấn quét trễ đơn, bảng log chống gửi lặp `delay_notifications`, thuật toán gom cụm câu hỏi từ `telemetry_logs` / `conversation_sessions`)
  - `services/gateway/src/` & `frontend/src/features/` (màn hình Dashboard Sự vụ Diện rộng & Danh sách đơn trễ chủ động)
  - Bộ test offline với ngày tham chiếu cố định (`get_vn_today()` của `ADR-003` vẫn được giữ nguyên)
- **Ngoài phạm vi (Non-Goals):**
  - Khôi phục lại kiểu cộng `+12h` sai đã bị loại bỏ ở `ADR-003` (vẫn bị CI static guard cấm tuyệt đối)
  - Tích hợp gửi SMS/Email thật hoặc thanh toán voucher tài chính thật

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-ORD-001`, `FR-TEL-001`, `NFR-TIME-001`, `SC-001`, `SC-002` ([Requirements Baseline v1](../product/requirements.md))
- **ADR:** [ADR-003 Giờ Việt Nam](../decisions/ADR-003-vietnam-time-no-12h-offset.md) — lưu ý: ngày tham chiếu demo chỉ phục vụ logic tính số ngày trễ của tác tử, tuyệt đối không làm sai lệch timestamp `+07:00` của log hệ thống.

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R3` (Sửa dataset `data/mock_orders.json`, gửi tin chủ động và phát sinh mã voucher giả lập `30k` — xem [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md))
- **Ràng buộc cứng:**
  - **Chống gửi trùng (Idempotency):** Tác tử phải ghi nhận `order_id` đã xử lý vào SQLite để không cấp lặp nhiều voucher `30k` khi chạy quét lại nhiều lần.
  - **Kiểm soát giới hạn:** Có cơ chế giới hạn số lượng/trạng thái (`Shipping` mới kích hoạt, không áp dụng `Delivered`/`Cancelled`) và tùy chọn cho nhân viên xác nhận gửi hàng loạt nếu cần.
  - **Không làm gãy test hiện có:** Sửa `mock_orders.json` không được làm thay đổi danh sách mã đơn / dữ liệu test đang dùng trong `tests/test_module3_orders.py` và `tests/test_data_and_pipeline_quality.py`.
- **Điểm cần duyệt:**
  1. Cách xử lý ngày ở Mục #4: cập nhật trực tiếp ngày mới trong `data/mock_orders.json` hay dùng thêm biến `DELAY_REFERENCE_DATE` cho demo?
  2. Chế độ phát voucher 30k ở Mục #3: **tạo hàng đợi để nhân viên bấm Gửi hàng loạt** (khuyên dùng) hay **tự động gửi tin vào chat khi chạy quét trong môi trường demo**?

---

## 6. Hiện trạng đã kiểm tra trong `data/mock_orders.json`

- Khi đọc trực tiếp `data/mock_orders.json`, các đơn hàng như `ORD-1001` hiện chỉ có trường chữ `"estimated_delivery": "Trong 1-2 ngày làm việc"` và các mốc `"shipping_timeline"` nằm ở **`2026-10-19`..`2026-10-21`**, chưa có trường ngày cam kết chuẩn `promised_delivery_date`.
- Nếu đối chiếu thẳng với ngày thực tế `get_vn_today()` (`2026-11-23`), hầu hết các đơn `Shipping` từ tháng 10 đều bị tính là trễ > 30 ngày, không phản ánh đúng vài ca trễ > 3 ngày có chủ đích như mục tiêu #4 nêu ra.

---

## 7. Hướng giải quyết đề xuất

1. **Chuẩn hóa trường ngày đơn hàng (`#4`):**
   - Bổ sung `promised_delivery_date` (`YYYY-MM-DD`) vào `mock_orders.json` (kèm tham số `DELAY_REFERENCE_DATE` tách biệt hoàn toàn với `get_system_now()` của `ADR-003`), chỉ thiết lập đúng 2–3 đơn `Shipping` trễ > 3 ngày làm dữ liệu kiểm thử/demo.
2. **Tác tử quét trễ > 3 ngày (`#3`):**
   - Tạo bảng `delay_notifications (order_id UNIQUE, days_overdue, voucher_code, voucher_amount, status, created_at)` trong `telemetry_service`.
   - Quét các đơn `Shipping` có `(ref_date - promised_delivery_date).days > 3` và chưa nằm trong `delay_notifications` -> tạo tin nhắn xin lỗi kèm voucher giả lập `30.000 VNĐ` và đẩy vào phiên chat / hàng đợi duyệt.
3. **Gom cụm sự vụ diện rộng (`#2`):**
   - Tổng hợp các tương tác gần đây trong một cửa sổ thời gian (VD: 24h gần nhất) theo nhóm `(intent, đơn vị vận chuyển / từ khóa sự cố)`; khi một cụm vượt ngưỡng tối thiểu (VD `>= 3` khách phản ánh cùng lúc), hiển thị thẻ **Sự vụ diện rộng** trên Dashboard kèm nút phát thông báo chung / xử lý hàng loạt.

---

## 8. Các bước triển khai (Milestones)

- [x] **M1 (`[DONE]`):** Chốt cơ chế `promised_delivery_date` + `DELAY_REFERENCE_DATE` và hàng đợi duyệt gửi hàng loạt cho tác tử voucher 30k.
- [x] **M2 (`[DONE]`):** Chuẩn hóa `promised_delivery_date` và `shipping_address` cho 100 đơn trong `data/mock_orders.json` (đúng 3 đơn `Shipping` trễ > 3 ngày là `ORD-1009`, `ORD-1011`, `ORD-1012` so với `2026-11-23`), xác nhận `test_module3_orders.py` và `test_data_and_pipeline_quality.py` pass 100%.
- [x] **M3 (`[DONE]`):** Cài đặt tác tử quét trễ (`scan_overdue_shipping_orders`, bảng `delay_notifications` chống cấp trùng) ở `telemetry_service` & `gateway`.
- [x] **M4 (`[DONE]`):** Xây API gom cụm sự vụ (`get_incident_clusters`, `record_incident_broadcast`), sub-tab "🚨 Sự vụ & Quét Trễ Đơn" trong `TelemetryDashboardView.tsx`, và `tests/test_order_actions_and_proactive_delay.py`.

---

## 9. Chiến lược kiểm thử & Tiêu chí nghiệm thu

- **Lệnh kiểm thử an toàn đã chạy:**
  - `tests/test_order_actions_and_proactive_delay.py`, `tests/test_module3_orders.py`, `tests/test_data_and_pipeline_quality.py` và toàn bộ CI offline.
- **Tiêu chí hoàn thành (Definition of Done):**
  - [x] Chỉ đúng các đơn `Shipping` trễ > 3 ngày được xử lý và tuyệt đối không cấp trùng voucher 30k.
  - [x] Dashboard gom nhóm chính xác các khiếu nại bùng phát cùng chủ đề để xử lý hàng loạt.
  - [x] Các bộ test đơn hàng & chất lượng dữ liệu hiện có không bị hồi quy.

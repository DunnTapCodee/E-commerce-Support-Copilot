# Kế Hoạch Thực Thi: Công Cụ Tái Lập Lỗi Hệ Thống (Replay) & Cơ Chế Rollback Phiên Bản Vận Hành

> **Tài liệu nguồn:** `docs/new_tasks/recommend.txt` (Mục 6: *"Thành phần tái tạo lại khi phiên bản mới không đem lại hiệu quả cho Hệ thống, thành phần tái lập lại lỗi Hệ thống"*)
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-regression-replay-and-rollback-ops`
- **Tên Task:** `Xây dựng công cụ tái lập lỗi từ log thực tế (Incident Replay) và cơ chế lưu snapshot/rollback phiên bản cấu hình khi bản mới suy giảm chất lượng`
- **Thời gian tạo / cập nhật:** `2026-11-23T18:14:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_OFFLINE`
- **Trạng thái phê duyệt:** `APPROVED (Chủ dự án xác nhận triển khai Đợt 3 ngày 2026-11-23)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. **Thành phần tái lập lại lỗi Hệ thống (Error Reproducer / Incident Replay):** Tạo tiện ích CLI (`scripts/replay_incident.py`) nhận `interaction_id` hoặc `session_id` từ SQLite telemetry & conversation DB, tự động che PII (`redact_pii()`), và xuất ra bộ fixture JSON + khung test `unittest` để tái hiện chính xác lỗi đó ở môi trường offline.
  2. **Thành phần khôi phục khi phiên bản mới không hiệu quả (Versioned Config/Model Rollback):** Bổ sung bên cạnh cơ chế rollback chính sách đã có (`PolicyManager.rollback_policy()`) và giám sát (`/audit/drift`, `/audit/shadow/evaluate`) một bộ lưu **Snapshot & Rollback Cấu hình Phiên bản** (`OPENAI_MODEL`, `RETRIEVAL_METHOD`, `INTENT_BACKEND`, ngưỡng guardrail, mã phiên bản prompt/model), giúp quay lui nhanh về bản ổn định trước đó khi bản mới rớt Release Gate hoặc cảnh báo trôi chất lượng (`drift_detected`).
- **Kết quả kỳ vọng:**
  - Script `scripts/replay_incident.py` trích xuất sự cố thành fixture replay offline an toàn PII.
  - Sổ lưu phiên bản cấu hình vận hành (Release Config Registry) hỗ trợ `create_snapshot()` & `rollback_to_version()` có audit log dấu thời gian `+07:00`.
  - Liên kết cảnh báo rollback từ `run_release_gates.py` (`RELEASE_BLOCKED`) và `GET /audit/drift`.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (In Scope):**
  - `scripts/replay_incident.py` (tái sử dụng `redact_pii()` từ `scripts/export_continual_learning_dataset.py` — không lặp logic)
  - Bộ quản lý snapshot cấu hình & rollback (trong `services/telemetry_service/` hoặc module config dùng chung với bản ghi audit)
  - Gắn gợi ý/liên kết với `evaluation/run_release_gates.py` và `/audit/drift`
  - Bộ test offline (`tests/test_replay_and_rollback.py`) + hướng dẫn vận hành trong [verification.md](../development/verification.md)
- **Ngoài phạm vi (Non-Goals):**
  - Tự động chạy `git reset` hay tự động deploy lại Docker container trên server (thuộc tầng hạ tầng CI/CD)
  - Sửa đổi hay xóa dữ liệu log lịch sử trong quá trình trích xuất replay

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-POL-001`, `FR-TEL-001`, `NFR-REL-001`, `NFR-SEC-002` ([Requirements Baseline v1](../product/requirements.md))
- **Thành phần sẵn có tái sử dụng:** `PolicyManager.rollback_policy()` (`document_service`), `/audit/drift` & `/audit/shadow/evaluate` (`telemetry_service`), `redact_pii()` (`scripts/export_continual_learning_dataset.py`), `evaluation/run_release_gates.py`

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Đọc dữ liệu telemetry/hội thoại chứa câu hỏi khách hàng và bổ sung trạng thái rollback cấu hình — xem [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md))
- **Ràng buộc cứng:**
  - **Bảo vệ PII (`NFR-SEC-002`):** Mọi fixture sinh từ `replay_incident.py` bắt buộc phải đi qua `redact_pii()` để ẩn SĐT, email, số giấy tờ trước khi ghi ra đĩa (`tests/` hoặc `reports/`).
  - **Tái lập 100% offline:** Khi chạy lại fixture đã xuất, test phải chạy với `DISABLE_EXTERNAL_LLM=true` trên ngữ cảnh đã chụp (0 request LLM tốn phí).
  - Khi chạy trong test tự động, không ghi đè file `reports/mlip_release_gates_results.json` đang track trong Git.
- **Điểm cần duyệt:** Chủ dự án xác nhận danh sách tham số cấu hình cần lưu trong mỗi snapshot rollback (`RETRIEVAL_METHOD`, `INTENT_BACKEND`, ngưỡng guardrail, mã prompt/model, gói `POL-*`).

---

## 6. Hướng giải quyết đề xuất

1. **Công cụ Tái lập Lỗi (`scripts/replay_incident.py`):**
   - Tham số vào: `--interaction-id <id>` hoặc `--session-id <id>`, kèm đường dẫn `--tel-db` / `--conv-db`.
   - Đọc ngữ cảnh sự cố (`customer_query`, `active_intent`, `retrieved_doc_ids`, `order_id`, `guardrail_action`, `raw_draft_text`, `components_used`), chạy `redact_pii()` rồi xuất ra:
     - File JSON fixture phục vụ đầu vào cho `IntentTracker` / `ResponsePolicyDispatcher` / `evaluate_runtime_safety_envelope`.
     - Khung test `unittest` tự động tái hiện đúng luồng lỗi để lập trình viên chạy trước và sau khi sửa lỗi.
2. **Sổ Snapshot & Rollback Phiên Bản Hệ Thống:**
   - Lưu từng phiên bản cấu hình bất biến (`version_id`, `intent_backend`, `retrieval_method`, `thresholds`, `prompt_hash`, `timestamp` theo `ADR-003`, `previous_version_id`) và hàm `rollback_to_version(target_version_id, reason)` có ghi lịch sử người/lý do khôi phục.
   - Tích hợp khuyến nghị hoặc trigger rollback khi `detect_telemetry_drift()` cảnh báo `CONCEPT_DRIFT` / `DATA_DRIFT` hoặc `run_release_gates.py` trả về `RELEASE_BLOCKED (NO-GO)`.

---

## 7. Các bước triển khai (Milestones)

- [x] **M1 (`[DONE]`):** Chốt danh sách tham số đưa vào Release Config Snapshot trong `contracts/release_config.py::capture_current_runtime_config()`.
- [x] **M2 (`[DONE]`):** Xây dựng `scripts/replay_incident.py` tái sử dụng `redact_pii()` và đọc SQLite ở chế độ read-only URI (`?mode=ro`) cùng `replay_fixture_offline()`.
- [x] **M3 (`[DONE]`):** Xây dựng `ReleaseConfigRegistry` lưu snapshot & rollback cấu hình tuân thủ timestamp `+07:00` (`ADR-003`), endpoint `/ops/releases/*` ở `telemetry_service` & `gateway`, và tích hợp `rollback_advisory` vào `evaluation/run_release_gates.py`.
- [x] **M4 (`[DONE]`):** Thêm unit test `tests/test_replay_and_rollback.py`, cập nhật `.github/workflows/ci-offline.yml` và `docs/development/verification.md`.

---

## 8. Chiến lược kiểm thử & Tiêu chí nghiệm thu

- **Lệnh kiểm thử an toàn đã chạy:**
  - `tests/test_replay_and_rollback.py` (`DISABLE_EXTERNAL_LLM=true`) cùng toàn bộ CI offline.
- **Tiêu chí hoàn thành (Definition of Done):**
  - [x] Có thể trích xuất bất kỳ sự cố nào từ telemetry thành fixture replay offline an toàn PII chỉ bằng 1 lệnh (`scripts/replay_incident.py`).
  - [x] Hỗ trợ lưu snapshot và rollback cấu hình phiên bản song hành cùng rollback chính sách (`FR-POL-001`).
  - [x] Toàn bộ CI offline pass, không làm bẩn DB gốc hay report đang track Git.

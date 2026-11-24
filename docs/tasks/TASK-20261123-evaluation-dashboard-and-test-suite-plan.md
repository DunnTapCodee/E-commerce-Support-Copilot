# Kế Hoạch Thực Thi: Nâng Cấp Toàn Diện Testing, Evaluation Runner & Tab "Kiểm Định"

> **Nguồn yêu cầu:** Phản hồi test trực tiếp giao diện `/staff` (Tab **Kiểm định** trống module, số liệu fallback giả) và kết quả kiểm tra thực tế container `gateway`.
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-evaluation-dashboard-and-test-suite`
- **Tên Task:** `Sửa lỗi runtime EvaluationRunner trên Gateway, loại bỏ KPI cứng giả và nâng cấp Tab Kiểm định hiển thị đầy đủ Data Slicing, Release Gates 4 tầng & Kiểm định Đợt 1–3`
- **Thời gian tạo / cập nhật:** `2026-11-23T20:36:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `VERIFIED (Unit tests + Gateway exec + Frontend tsc/unit)`
- **Trạng thái phê duyệt:** `APPROVED (Đợt 4)`

---

## 2. Hiện trạng & Nguyên nhân gốc quan sát được (`Observed`)

Qua gọi trực tiếp `GET /api/v1/copilot/evaluation/summary` và kiểm tra trong container `gateway`:

1. **Tab Kiểm định đang bị lỗi `ModuleNotFoundError: No module named 'requests'` ngầm ở `gateway`:**
   - Khi `gateway` gọi `EvaluationRunner.run_full_suite()` → `evaluation/chaos_safeguard_tests.py` → `copilot_draft_engine.py` → `contracts/llm_failover.py` → `import requests`, container `gateway` thiếu thư viện `requests` (do `services/gateway/requirements.txt` dùng `httpx`).
   - `services/gateway/src/main.py#L580-L586` bắt exception này và trả về JSON fallback `{"overall_pass_rate": 97.6, "modules": []}`.
   - `EvaluationDashboardView.tsx#L100-L113` tiếp tục điền các hằng số giả (`97.6%`, `41/42`, `9/9`, `95.0%`, `0.0%`, `100.0%`) khiến giao diện hiện KPI đẹp nhưng danh sách bên dưới hoàn toàn trống (`modules: []`).
2. **KPI và bộ lọc trên UI đang bị lệch & cứng (`evaluation_runner.py` & `EvaluationDashboardView.tsx`):**
   - `evaluation_runner.py#L295-L300` trả về `kpi_metrics` là 4 chuỗi **hardcode cố định** thay vì tính từ kết quả thực tế của từng run.
   - Bộ lọc category trên `EvaluationDashboardView.tsx#L92-L97` (`"Safety & Guardrails"`, `"System Quality Assurance"`) **không khớp** tên category thực tế mà `evaluation_runner.py` xuất ra (`"Safety Guardrail"`, `"Adversarial Robustness"`, `"Quality Governance"`, `"Governance & Telemetry"`).
3. **Thiếu hẳn những phần đánh giá "đắt giá" nhất của dự án đã có ở backend:**
   - Chưa hiển thị **Model Benchmark & 7 Data Slices** (`clean`, `typo_unaccented`, `polite`, `short`, `long_complex`, `out_of_scope`, `adversarial` — Accuracy, Macro F1, P90 Latency) từ `evaluation/model_benchmarks.py`.
   - Chưa tích hợp **4-Layer Release Gates (`RELEASE_READY (GO)` / `RELEASE_BLOCKED (NO-GO)`)** kèm blockers/warnings từ `evaluation/run_release_gates.py`.
   - Chưa có module kiểm định cho **toàn bộ tính năng mới Đợt 1–3** (IDOR isolation, voucher/warehouse/brand guardrails, FIFO draft queue, HITL order action eligibility, proactive delay idempotency, PII-safe replay & config rollback).
   - Chưa hiển thị kết quả **Production Drift + Shadow Mode Comparison** và **Test Suite Pytest Breakdown** (19 suites offline).

---

## 3. Mục tiêu & Kiến trúc Kiểm định Mới (Làm cho phần Testing & Evaluation thực sự có giá trị)

### Tầng A — Sửa triệt để lỗi runtime & Loại bỏ số liệu giả
1. Xử lý `requests` trong `contracts/llm_failover.py` (chỉ import lazy khi chạy nhánh `requests` hoặc dùng chung `httpx` / thêm dependency an toàn) để `gateway` chạy `EvaluationRunner` thành công `100%` không lỗi.
2. Khi endpoint `/evaluation/summary` lỗi, trả lỗi minh bạch + banner cảnh báo thật trên UI thay vì giả vờ `97.6%`.
3. Tính **KPI thật từ kết quả thực thi** (`faithfulness_pass_rate`, `financial_leakage_rate`, `prompt_injection_blocked_rate`, `temporal_guard_rate`, `idor_isolation_rate`), không hardcode chuỗi tĩnh.
4. Đồng bộ 100% mã category giữa backend và filter tabs trên UI (`all`, `Behavioral Testing`, `Safety & Security`, `Model Slicing & RAG`, `Ops & Release Gate`).

### Tầng B — Mở rộng Evaluation Runner thành 4 khối toàn diện (hơn hẳn 9 bài check nhỏ cũ)
1. **Khối 1: Behavioral CheckList & Sliced Model Benchmark (`Ch. 15`)**
   - Giữ và nâng cấp **MFT / INV / DIR** (tăng số lượng ca tiếng Việt không dấu, phủ định đảo chiều).
   - Chạy **`ModelBenchmarkRunner`** trên 7 lát cắt (`clean`, `typo_unaccented`, `polite`, `short`, `long_complex`, `out_of_scope`, `adversarial`) và trả bảng **Accuracy / Macro F1 / P90 Latency** từng lát cắt về UI (vẽ thanh progress bar lộ rõ điểm yếu/điểm mù từng lát cắt!).
2. **Khối 2: Security, Safety Envelopes & Đợt 1–2 Adversarial Suite (`Ch. 18`)**
   - `Financial & Voucher Hard Gate` (bao gồm cả dụ voucher 1 triệu, bù đắp, trừ thẳng vào đơn).
   - `Warehouse Parcel Seal & Brand Comparison Guard` (`POL-BRAND-001`).
   - `IDOR Cross-Customer Isolation` (test chéo `CUST-*`, `ORD-*`, sản phẩm trùng tên).
   - `Temporal Policy Trap` (chính sách hết hạn/superseded) & `NLI Faithfulness / Dynamic Order Grounding`.
   - `Chaos & Prompt Injection` (bẻ khóa, circuit breaker khi service down).
3. **Khối 3: Pipeline, System Sync & In-Chat Order Actions (`Ch. 17–18`)**
   - `FIFO Draft Queue Race-Condition Check` (gửi Q1 + Q2 liên tiếp không mất nháp 1).
   - `HITL Order Action Matrix` (chỉ đề xuất + duyệt nguyên tử, `REJECT` thiếu lý do phải `422`).
   - `Proactive Delay Agent Idempotency` (chỉ đúng đơn `Shipping` trễ > 3 ngày, quét lại sinh `0` trùng).
4. **Khối 4: Production Governance, Release Gates & Ops (`Ch. 19`)**
   - Chấm **Release Gate Decision**: `RELEASE_READY (GO)` hoặc `RELEASE_BLOCKED (NO-GO)` kèm danh sách blockers/warnings cụ thể.
   - Đọc telemetry thật từ `telemetry_service` (`/audit/drift`, `/ops/releases/health-gate`) để hiện trạng thái Drift (Data Drift, Concept Drift, Rubber-stamping) và **Nút gợi ý Rollback / Export Incident Replay**.
   - Tùy chọn nút **Chạy Pytest Offline Summary** (chỉ đọc kết quả an toàn hoặc chạy subset nhanh an toàn, tách biệt rõ *Unit/Contract* vs *Behavioral/Model Evaluation* vs *Live Smoke*).

### Tầng C — Thiết kế lại Giao diện `EvaluationDashboardView.tsx`
- **Header + Release Gate Banner:** Hiện huy hiệu lớn `RELEASE_READY (GO)` / `RELEASE_BLOCKED (NO-GO)` + timestamp `+07:00` + thời gian chạy thật + nút **Chạy Kiểm định Toàn diện** (có thanh tiến trình từng giai đoạn hoặc chia 2 nút: *Chạy Nhanh Behavioral & Safety* vs *Chạy Full Benchmark + 7 Slices*).
- **Bảng Data Slicing Breakdown (7 Lát Cắt):** Hiện Accuracy, Macro F1, Latency P90 và badge cảnh báo lát cắt nào dưới ngưỡng (`< 75%`).
- **Tích hợp Sandbox Kiểm Thử Nhanh (Interactive Probe):** Cho phép gõ thử 1 câu bất kỳ (hoặc chọn preset tấn công: IDOR, dụ voucher 1tr, Shopee vs Tiki, gõ không dấu) để xem trực tiếp pipeline đánh giá **Intent + Guardrail + Faithfulness + Oracle Score** ngay tại tab Kiểm định.
- **Lịch sử các lần chạy (Run History & Diff):** Lưu tối đa 10 lần chạy gần nhất trong SQLite/JSON runtime (ngoài Git) để so sánh bản mới vs bản trước (pass rate tăng/giảm bao nhiêu %) + nút khuyến nghị rollback nếu tụt ngưỡng.

---

## 4. Phạm vi triển khai dự kiến (`In Scope` / `Non-Goals`)

- **In Scope:**
  - `contracts/llm_failover.py` & `services/gateway/requirements.txt` (sửa lỗi thiếu `requests` trong `gateway`).
  - `evaluation/evaluation_runner.py` & `evaluation/run_release_gates.py` (KPI động, tích hợp 7 slices + 12+ modules gồm Đợt 1–3 + JSON schema thống nhất, không ghi đè file report đang track Git khi chạy từ UI).
  - `services/gateway/src/main.py` (thêm endpoint `/api/v1/copilot/evaluation/probe` cho Sandbox Kiểm Thử Nhanh và sửa fallback không trả số liệu giả).
  - `frontend/src/features/evaluation/EvaluationDashboardView.tsx` & `frontend/src/lib/api-client.ts` (bảng 7 lát cắt, Release Gate `GO/NO-GO`, Interactive Adversarial Probe, lịch sử so sánh run).
  - `tests/test_evaluation_dashboard_runner.py` (test offline toàn bộ runner mới + schema gateway).
- **Non-Goals:**
  - Không chạy các benchmark nặng phải tải model HuggingFace lớn (`vietnamese-sbert` / `bge-reranker`) ngay trên request HTTP đồng bộ của UI.

---

## 5. Ràng buộc & Tiêu chí Nghiệm thu (`Definition of Done`)

- [ ] `GET /api/v1/copilot/evaluation/summary` & `POST /api/v1/copilot/evaluation/run` chạy thành công trong container `gateway` (`0` `ModuleNotFoundError`, `modules.length >= 12`).
- [ ] Không còn KPI hardcoded giả (`97.6%`, `95.0%`) trên backend lẫn frontend.
- [ ] UI Tab Kiểm định hiển thị đầy đủ: Banner `GO/NO-GO`, Bảng 7 Data Slices, Bộ lọc đúng category, Chi tiết fail/pass từng test case, và Sandbox thử câu đối kháng trực tiếp.
- [ ] Toàn bộ test offline CI (`pytest`, `tsc --noEmit`, `npm run test:unit`) và test thực tế trên Docker pass.

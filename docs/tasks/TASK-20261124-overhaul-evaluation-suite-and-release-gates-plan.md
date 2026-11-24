# Kế Hoạch Thực Thi (Task 5/6): Đại Tu Toàn Diện Hệ Thống Đánh Giá (`EvaluationRunner`), Bộ Dữ Liệu Chuẩn 16 Intents, Đánh Giá RAG & Release Gates

> **Trình tự thực thi:** **Bước 5 / 6** — Thực hiện sau khi logic sản phẩm ở Backend & Frontend (**Task 1–4**) đã được chuẩn hóa, nhằm đo lường trung thực chất lượng toàn hệ thống.
> **Quy tắc:** Tuân thủ nghiêm ngặt chuẩn `No fabricated metrics or silent greenwashing` trong [AGENTS.md](../../AGENTS.md). Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử tại Mục 8.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261124-overhaul-evaluation-suite-and-release-gates`
- **Tên Task:** `Sửa triệt để lỗi crash ngầm và greenwashing trong bộ Evaluation, mở rộng tập dữ liệu đánh giá phủ đủ 16/16 TARGET_INTENTS trên 7 lát cắt, tích hợp benchmark RAG Retrieval thực tế và kiểm định Oracle sinh nháp End-to-End`
- **Thời gian tạo / cập nhật:** `2026-11-24T23:12:00+07:00`
- **Trạng thái Task (`Task Status`):** `NOT_STARTED`
- **Trạng thái triển khai (`Implementation Status`):** `PLANNED`
- **Trạng thái kiểm thử (`Verification Status`):** `NOT_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `PENDING_APPROVAL (Chờ chủ dự án xác nhận triển khai)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. **Xóa sổ hoàn toàn các lỗi Crash ngầm & Báo cáo xanh giả (Silent Greenwashing):**
     - Sửa lỗi gọi sai tham số `TestOracleEvaluator.evaluate_rubric(..., citations=..., order_data=...)` và đọc sai khóa `composite_score` tại `evaluation/evaluation_runner.py#L322-L328` (hiện đang làm module `test_oracle` crash `TypeError` ở 100% lần chạy nhưng bị nuốt lỗi và vẫn trả `Release Gate: GO`).
     - Sửa lỗi kiểm tra thuộc tính không tồn tại `getattr(cand, "pipeline", None)` tại `evaluation_runner.py#L35` và `behavioral_tests.py#L37` (đổi sang `cand.has_ml_artifacts` và dùng chung 1 thể hiện `IntentPredictor` thay vì nạp lại model 4 lần/lượt chạy).
     - Xóa bỏ khối `except` ngụy tạo `passed_scenarios: 3, pass_rate: 100.0 ("Simulation Fallback")` khi mất kết nối Gateway trong `evaluation/run_full_evaluation.py#L182-L189`.
     - Chuẩn hóa hệ thống phân loại `category` và quy tắc `Release Gate`: bất kỳ module nào có `status in ("FAILED", "ERROR")` hoặc lát cắt dưới ngưỡng bắt buộc đều phải sinh `blocker` và chặn phát hành (`NO-GO`).
  2. **Mở rộng Tập dữ liệu Đánh giá phủ kín 16/16 `TARGET_INTENTS` + `out_of_scope`:**
     - Bổ sung đầy đủ 4 intent chuẩn đã chốt tại `OD-004` nhưng đang bị bỏ trống 100% (`warranty`, `get_discounts`, `create_account`, `recover_password`) vào cả `BENCHMARK_DATASET` (`dataset_loader.py`) lẫn `BehavioralTestSuite` (`run_mft`, `run_inv`, `run_dir`, `run_multi_turn_context`).
     - Mở rộng `BENCHMARK_DATASET` từ 44 mẫu hiện tại lên **>= 120 mẫu đa dạng** (đúng như thiết kế ban đầu), đảm bảo mỗi lát cắt trong 7 Data Slices (`clean`, `typo_unaccented`, `polite`, `short`, `long_complex`, `out_of_scope`, `adversarial`) có ít nhất **12–20 mẫu** để chỉ số Accuracy / Macro-F1 có ý nghĩa thống kê.
     - Xây dựng bộ mẫu tiếng Việt tự nhiên thực tế có gán nhãn chuẩn vào `data/eval/real_vi_handwritten.csv` (hiện đang trống trơn chỉ có dòng header).
  3. **Đánh giá thực chất RAG Retrieval & Sinh nháp End-to-End (thay cho chấm chuỗi tĩnh):**
     - Tích hợp module đánh giá **RAG Retrieval Benchmark** chạy thật trên tập `data/retrieval_eval.json` (đo `Recall@1`, `Recall@3`, `MRR@3` và tỷ lệ chặn bẫy chính sách hết hạn) ngay trong `EvaluationRunner` & `run_release_gates.py`.
     - Nâng cấp module **4-Tier Test Oracle** chạy kiểm định trên đầu ra sinh nháp thực tế của tập kịch bản chuẩn (đơn hàng đơn lẻ, đa đơn hàng, đổi trả, bảo hành, ưu đãi) thay vì chỉ chấm 1 câu string gõ cố định trong code.
     - Ghi nhận rõ ràng trường `execution_mode` (`offline_fallback` vs `live_llm_and_ml`) và tên model thực tế đã chạy trong báo cáo để không bao giờ đánh đồng điểm của bộ regex offline với chất lượng của mô hình AI thật.
- **Kết quả kỳ vọng:**
  - Bộ đánh giá tự động trung thực 100%, bao phủ toàn diện cả 4 trụ cột của hệ thống: **Intent NLU (16+1 nhãn, 7 lát cắt) -> RAG Retrieval (`Recall@k`, `MRR@k`) -> Draft Generation Oracles (4 tầng) -> Safety Envelopes & Governance**.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `evaluation/evaluation_runner.py`
  - `evaluation/oracle_evaluator.py`
  - `evaluation/dataset_loader.py`
  - `evaluation/behavioral_tests.py`
  - `evaluation/run_release_gates.py`
  - `evaluation/run_full_evaluation.py`
  - `evaluation/end_to_end_evaluator.py`
  - `data/eval/real_vi_handwritten.csv`
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không ghi đè tự động vào các file báo cáo lịch sử đang được theo dõi bởi Git (`reports/*.json`, `reports/*.md`) khi chạy từ giao diện web hoặc trong kiểm thử tự động CI.
  - Cấu hình Vitest cho Frontend và cấu hình GitHub Actions CI thuộc **Task 6**.

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-INT-004`, `FR-INT-005`, `FR-RAG-001`, `FR-RAG-002`, `NFR-QUAL-001`, `SC-001`..`SC-007` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả & Kiểm chứng:** [Verification Engineering Baseline v1 §3](../development/verification.md), [SPEC-INT-001](../specs/intent-classification.md), [SPEC-WF-001](../specs/copilot-workflow.md)
- **Chuẩn kỹ thuật bắt buộc:** `Engineering & Generalization Standard (No fabricated metrics or silent greenwashing)` trong [AGENTS.md](../../AGENTS.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Cập nhật toàn bộ khung đánh giá chất lượng, bộ dữ liệu chuẩn và tiêu chí cổng phát hành Release Gate — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Tuyệt đối không thiết kế câu hỏi benchmark trùng khít từng chữ với từ khóa mẫu trong prompt hay fallback để "làm đẹp điểm số" — phải có các biến thể diễn đạt tự nhiên, viết tắt, phương ngữ, câu ghép và câu phủ định.
  - Khi chạy với `DISABLE_EXTERNAL_LLM=true`, thời gian chạy toàn bộ `EvaluationRunner.run_full_suite()` phải hoàn tất nhanh (< 5 giây) và thực hiện **0** kết nối mạng ra ngoài.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án đối với ngưỡng điểm Release Gate mặc định cho các module mới (ví dụ `RAG Recall@3 >= 85%`) trong khi SLA sản phẩm chính thức (`OD-006`) đang để mở.

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Chuẩn hóa Hợp đồng Kết quả & Chốt chặn Lỗi trong `EvaluationRunner`:**
   - Thống nhất danh sách 4 `category` chuẩn giữa `evaluation_runner.py` và `EvaluationDashboardView.tsx`: `"Behavioral Testing"`, `"RAG & Model Slicing"`, `"Safety & Guardrails"`, `"System Quality Assurance"`.
   - Mọi khối `try/except` của từng module nếu bắt được ngoại lệ phải cộng số ca kiểm thử dự kiến vào tổng mẫu số (với `passed = 0`, `pass_rate = 0.0`, `status = "ERROR"`), đồng thời tự động thêm dòng chi tiết lỗi vào `gate_blockers` để `release_gate.decision` chuyển ngay sang `"NO-GO"`.
   - Sửa lời gọi `TestOracleEvaluator.evaluate_rubric()` truyền đúng `customer_query` và đọc `rubric_score_percent`; bổ sung kiểm tra cả `TestOracleEvaluator.verify_dynamic_order_grounding()` và `evaluate_faithfulness()`.
2. **Xây dựng Tập dữ liệu Đánh giá Chuẩn Hóa (>= 120 mẫu, 16+1 nhãn) & `real_vi_handwritten.csv`:**
   - Mở rộng `BENCHMARK_DATASET` bao phủ đều khắp 16 `TARGET_INTENTS` (`track_order`, `cancel_order`, `delivery_time`, `delivery_issue`, `shipping_costs`, `return_policy`, `return_product`, `refund_policy`, `request_refund`, `refund_status`, `payment_issue`, `human_agent`, `warranty`, `get_discounts`, `create_account`, `recover_password`) và `out_of_scope` trên đủ 7 lát cắt.
   - Bổ sung ít nhất 50–80 câu tiếng Việt thực tế (có lỗi gõ phím, viết tắt TMĐT như *ko, dc, mk, đh, ktra, hoàn xu, đổi sz...*) vào `data/eval/real_vi_handwritten.csv` và thêm hàm nạp kiểm tra lát cắt dữ liệu viết tay này trong `dataset_loader.py`.
3. **Tích hợp Đánh giá RAG Retrieval & Sinh Nháp Động vào Runner:**
   - Thêm module `rag_retrieval_quality` trong `EvaluationRunner`: khởi tạo `PolicyRetriever` với phương thức cấu hình hiện hành (`bm25` mặc định) và chạy đánh giá trên `data/retrieval_eval.json` để xuất chỉ số thực `Recall@1`, `Recall@3`, `MRR@3`.
   - Nâng cấp module `test_oracle`: chạy qua một tập >= 8 kịch bản sinh nháp thực tế (gồm tra đơn thường, lọc đa đơn hàng, đổi trả chính sách, bảo hành, và câu bẫy số tiền ảo) để đo tỷ lệ vượt qua 4 tầng Oracle thực chất.
   - Trong `run_full_evaluation.py`: khi `EndToEndEvaluator` không kết nối được Gateway, gán `status = "UNREACHABLE"`, `passed_scenarios = 0`, `pass_rate = 0.0` và ghi cảnh báo rõ ràng trong báo cáo.

---

## 7. Các bước triển khai (Milestones)

- [ ] **M1 (`[PLANNED]`):** Sửa lỗi crash `test_oracle`, sửa `_get_intent_predictor()` dùng `has_ml_artifacts` + cache predictor, chuẩn hóa `category` và quy tắc chặn `ERROR`/`FAILED` -> `NO-GO` trong `evaluation_runner.py` & `run_full_evaluation.py`.
- [ ] **M2 (`[PLANNED]`):** Mở rộng `evaluation/dataset_loader.py` (>= 120 mẫu phủ đủ 16 `TARGET_INTENTS` + `out_of_scope` trên 7 lát cắt), cập nhật `evaluation/behavioral_tests.py` (thêm MFT/INV/DIR/Multi-turn cho 4 intent mới) và điền dữ liệu chuẩn vào `data/eval/real_vi_handwritten.csv`.
- [ ] **M3 (`[PLANNED]`):** Tích hợp module đánh giá RAG Retrieval (`data/retrieval_eval.json` — `Recall@3`, `MRR@3`) và bộ kiểm định 4-Tier Oracle đa kịch bản vào `evaluation_runner.py` & `run_release_gates.py`, kèm gắn nhãn minh bạch `execution_mode` (`offline_fallback` vs `live_llm_ml`).
- [ ] **M4 (`[PLANNED]`):** Chạy kiểm chứng toàn bộ `EvaluationRunner.run_full_suite()` và `run_release_gates.py` (xuất ra thư mục tạm), đảm bảo `0` module bị `ERROR` và số liệu nhất quán 100%.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn dự kiến chạy (`DISABLE_EXTERNAL_LLM=true`):**
  - `python -m pytest tests/test_evaluation_dashboard_runner.py tests/test_mlip_evaluation.py -v`
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `NOT_YET_RUN`
  - `Result:` `NOT_YET_RUN`
  - `Limitations:` `Chưa thực thi (Task đang ở trạng thái PLANNED).`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Thực hiện sau **Task 1–3** (và đồng bộ hiển thị với **Task 4**) để các chỉ số đánh giá phản ánh đúng logic hệ thống sau khi đã dọn sạch lỗi.
- **Điểm nghẽn hiện tại:** Chờ chủ dự án phê duyệt kế hoạch; việc chạy benchmark ở chế độ `live_llm_ml` (gọi API CKEY.VN cho ~120+ mẫu tốn token) sẽ chỉ chạy khi có xác nhận riêng (`R3`), còn chế độ mặc định CI chạy offline an toàn.

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [ ] `EvaluationRunner.run_full_suite()` chạy hoàn tất với **0** module có `status == "ERROR"`; giả lập bất kỳ lỗi ngoại lệ nào ở một module con đều khiến `release_gate.decision` chuyển thành `"NO-GO"`.
- [ ] `run_full_evaluation.py` không còn đoạn giả lập `pass_rate: 100.0` khi mất kết nối Gateway.
- [ ] Tập dữ liệu `BENCHMARK_DATASET` có >= 120 ca kiểm thử bao phủ đủ **16/16 `TARGET_INTENTS` + `out_of_scope`**, không còn lát cắt nào chỉ có 3 mẫu; `data/eval/real_vi_handwritten.csv` có dữ liệu kiểm thử tiếng Việt thực tế hợp lệ.
- [ ] Báo cáo đánh giá xuất ra đầy đủ chỉ số thực của cả **Intent Slicing**, **Behavioral CheckList**, **RAG Retrieval (`Recall@3`, `MRR@3`)**, **4-Tier Draft Oracles**, **Safety Envelopes** và ghi rõ `execution_mode` + model đang đo.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-24T23:12:00+07:00` | Lập kế hoạch Task 5 đại tu toàn diện mảng Evaluation & Release Gates | Kiểm chứng thực tế phát hiện `test_oracle` crash `TypeError` ngầm vẫn báo `GO`, `run_full_evaluation.py` bịa `100%` khi lỗi mạng, thiếu 4/16 intents và thiếu đánh giá RAG trong runner | `Observed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Kiểm toán chi tiết toàn bộ thư mục `evaluation/` và lập kế hoạch đại tu (`PLANNED`).
- **Hành động tiếp theo:** Triển khai sau **Task 4**, sau đó khóa chặt toàn bộ vào pipeline kiểm thử tự động CI ở **Task 6**.
- **Tham chiếu:** [verification.md](../development/verification.md), [requirements.md](../product/requirements.md), [AGENTS.md](../../AGENTS.md).

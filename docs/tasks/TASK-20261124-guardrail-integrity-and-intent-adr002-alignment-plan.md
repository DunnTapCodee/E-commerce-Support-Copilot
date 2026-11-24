# Kế Hoạch Thực Thi (Task 1/6): Vá Lỗ Hổng Chốt Chặn Đa Đơn Hàng, Chuẩn Hóa Intent Fallback Theo ADR-002 & Tổng Quát Hóa Truy Xuất Chính Sách Hết Hạn

> **Trình tự thực thi:** **Bước 1 / 6** trong lộ trình chuẩn hóa kiến trúc & kiểm định toàn diện (thực hiện đầu tiên để khóa chặt các bất biến an toàn trước khi tinh gọn pipeline).
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261124-guardrail-integrity-and-intent-adr002-alignment`
- **Tên Task:** `Khắc phục lỗi bypass guardrail khi khách có nhiều đơn hàng, chuẩn hóa chuỗi fallback Intent theo đúng ADR-002 và loại bỏ hardcode bẫy chính sách cũ trong RAG Retriever`
- **Thời gian tạo / cập nhật:** `2026-11-24T23:46:00+07:00`
- **Trạng thái Task (`Task Status`):** `COMPLETED`
- **Trạng thái triển khai (`Implementation Status`):** `IMPLEMENTED`
- **Trạng thái kiểm thử (`Verification Status`):** `LOCALLY_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `APPROVED (Chủ dự án đã xác nhận triển khai Task 1)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. Triệt tiêu lỗ hổng logic khiến khách hàng có `> 1` đơn hàng (ví dụ `CUST-1001`) tự động nhận `multi_order_context` ở mọi câu hỏi đầu phiên và đi tắt qua các chốt chặn `out_of_scope`, `unknown_query`, `confidence < 0.60` cũng như `has_expired_policy`.
  2. Khôi phục đúng cam kết kiến trúc `ADR-002` (`LLM primary -> ML fallback -> safe human escalation`) trong `IntentPredictor.predict()`, chấm dứt việc lén gọi bộ regex `semantic_rule_fallback` để đẩy điểm tin cậy giả (`0.85–0.96`) khi model ML trả về OOV, đồng thời xử lý cảnh báo lệch phiên bản pickle `scikit-learn 1.6.1` vs `1.9.1`.
  3. Xóa bỏ hoàn toàn đoạn hardcode từ khóa năm cũ (`"2022"`, `"2023"`, `"quý mão"`) và điều kiện cứng `"OLD" in doc.doc_id` trong `PolicyRetriever`, chuyển sang cơ chế truy xuất tổng quát để `Temporal Policy Guard` phát hiện được mọi chính sách hết hạn/bãi bỏ theo metadata thực tế.
- **Kết quả kỳ vọng:**
  - Bộ phân giải ngữ cảnh đơn hàng (`order_context_resolver.py`) và bộ điều phối chính sách phản hồi (`response_dispatcher.py`) giữ nguyên 100% hiệu lực của mọi chốt chặn an toàn cho cả khách 1 đơn lẫn khách nhiều đơn.
  - `IntentPredictor` tuân thủ nghiêm ngặt thứ tự fallback của `ADR-002` và không còn phát sinh cảnh báo `InconsistentVersionWarning` khi chạy kiểm thử.
  - `PolicyRetriever` truy xuất chính xác văn bản hết hạn dựa trên nội dung/metadata thay vì dựa vào chuỗi `"OLD"` trong mã tài liệu.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `services/conversation_service/src/dialogue_state/order_context_resolver.py`
  - `services/conversation_service/src/policies/response_dispatcher.py`
  - `services/intent_service/src/predictor.py` (và cập nhật/đóng gói artifact ML baseline tương thích runtime nếu được duyệt)
  - `services/rag_service/src/retriever.py` & `services/rag_service/src/search_experiments.py` (hỗ trợ index đầy đủ khi `filter_active_only=False` để kiểm tra chính sách hết hạn tổng quát)
  - Các bài kiểm thử hồi quy liên quan trong `tests/test_guardrails.py`, `tests/test_multi_order_disambiguation.py`, `tests/test_architecture_decisions_alignment.py`, `tests/test_data_and_pipeline_quality.py`
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không gộp/tinh gọn `InputClassifier`, `QueryRewriter` hay `CustomerAcknowledgementEngine` (thuộc **Task 2**).
  - Không hợp nhất `/chat` và `/chat_stream` trong `main.py` (thuộc **Task 3**).
  - Không thay đổi giao diện React (thuộc **Task 4**) hay cấu trúc `EvaluationRunner` (thuộc **Task 5**).

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `PG-003`, `BR-002`, `BR-004`, `FR-INT-001`..`FR-INT-005`, `FR-RAG-001`, `SC-003`, `SC-004` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [SPEC-WF-001 (Copilot Workflow)](../specs/copilot-workflow.md), [SPEC-INT-001 (Intent Classification)](../specs/intent-classification.md)
- **ADR & Kiến trúc:** [ADR-002](../decisions/ADR-002-intent-llm-primary-ml-fallback.md), [ADR-003](../decisions/ADR-003-vietnam-time-no-12h-offset.md), [Architecture Overview v1](../architecture/overview.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Thay đổi logic điều phối chốt chặn an toàn liên module và hành vi fallback phân loại ý định — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)). *Lưu ý:* Nếu thực hiện ghi đè file model nhị phân trong `artifacts/` hoặc `ML-model/`, cần xác nhận rõ trước khi ghi.
- **Ràng buộc cứng:**
  - Bảo toàn mọi chỉnh sửa hiện có trên cây thư mục Git (`git status`).
  - Tuyệt đối không dùng regex bắt cứng từng câu mẫu để vượt bài test (tuân thủ chuẩn `Anti-Hardcoding` trong [AGENTS.md](../../AGENTS.md)).
  - Giữ nguyên tính cô lập offline (`DISABLE_EXTERNAL_LLM=true` không phát sinh bất kỳ kết nối mạng nào).
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án trước khi bắt đầu thực thi và trước khi cập nhật file model local (nếu chọn phương án đóng gói lại model tương thích `scikit-learn` hiện hành thay vì giữ pickle `1.6.1`).

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Khóa chặt điều kiện sinh `multi_order_context` và thứ tự ưu tiên trong `ResponsePolicyDispatcher`:**
   - Trong `order_context_resolver.py`: Ở nhánh `3d` (không có mã `ORD-*` tường minh, không khớp bộ lọc trạng thái/thuộc tính/sản phẩm), chỉ tạo `multi_order_context` khi truy vấn thực sự mang tín hiệu hỏi về đơn hàng/giao nhận/thanh toán của cá nhân khách, **không** gắn toàn bộ danh sách đơn hàng vào các câu hỏi chính sách chung, tài khoản, hay câu ngoài phạm vi.
   - Trong `ResponsePolicyDispatcher.dispatch()`: Di chuyển nhánh kiểm tra `has_multi_order_context` xuống **sau** tất cả các cổng an toàn bắt buộc: `out_of_scope` (Case 2b), `intent_unavailable` / `not is_in_scope` / `unknown_query` (Case 3a), `confidence < INTENT_CONFIDENCE_THRESHOLD` (Case 3b), và `has_expired_policy` (Case 4).
2. **Tuân thủ nghiêm ngặt `ADR-002` trong `IntentPredictor`:**
   - Xóa bỏ đoạn ghi đè `if ml_resp.model_name == "legacy_baseline" and ml_resp.confidence <= 0.15: return self.llm_classifier._semantic_fallback(query)` trong luồng online tại `predictor.py#L321-L324`. Khi LLM sập và ML dự đoán độ tin cậy thấp (`0.10 < 0.60`), trả trung thực kết quả ML để tầng điều phối kích hoạt `ESCALATE_HUMAN` đúng thiết kế fail-closed.
   - Huấn luyện/xuất một artifact sklearn nhẹ chuẩn hóa 16 `TARGET_INTENTS` vào `artifacts/models/intent/` (kèm `meta.json` khớp phiên bản `scikit-learn` hiện tại) hoặc chuẩn hóa bộ tải model để loại bỏ cảnh báo `InconsistentVersionWarning` và đảm bảo ML fallback hỗ trợ tiếng Việt thật sự.
3. **Tổng quát hóa phát hiện chính sách hết hạn trong `PolicyRetriever`:**
   - Bỏ danh sách từ khóa năm cũ (`"2022"`, `"2023"`, `"quý mão"`) và bỏ điều kiện `if "OLD" in doc.doc_id:`.
   - Duy trì hai chỉ mục tìm kiếm nhẹ trong `PolicyRetriever` (`active_searcher` cho truy vấn thông thường khi `filter_active_only=True`, và `full_corpus_searcher` bao gồm cả tài liệu `is_active=False` / `superseded`). Khi điểm tương đồng của một văn bản hết hạn/bãi bỏ vượt trội rõ rệt (khách hỏi trực tiếp về chương trình/phiên bản chính sách đã hết hạn bất kỳ, kể cả năm `2025` hay mã `POL-FLASH-*`), trả về văn bản đó để `Temporal Policy Guard` chặn an toàn bằng metadata thời gian thực (`get_vn_today()`).

---

## 7. Các bước triển khai (Milestones)

- [x] **M1 (`[VERIFIED]`):** Chuẩn hóa điều kiện kích hoạt `multi_order_context` (`is_personal_order_portfolio_inquiry` + tránh gắn ngầm đơn lẻ ở nhánh 4 khi khách có `> 1` đơn) trong `order_context_resolver.py` và sắp xếp lại thứ tự chốt chặn trong `response_dispatcher.py` để `has_multi_order_context` nằm sau toàn bộ Case 2b/3/4.
- [x] **M2 (`[VERIFIED]`):** Sửa `services/intent_service/src/predictor.py` loại bỏ nhánh lách `_semantic_fallback` ở chế độ online, bổ sung `NumpyLinearBackend` không phụ thuộc phiên bản pickle `scikit-learn` và đóng gói bộ ML fallback song ngữ (`VI` + `EN`, 16 `TARGET_INTENTS` + `out_of_scope`) tại `artifacts/models/intent/` qua `scripts/build_intent_fallback_artifacts.py`.
- [x] **M3 (`[VERIFIED]`):** Tái cấu trúc `services/rag_service/src/retriever.py` loại bỏ toàn bộ điều kiện hardcode `"OLD"` / `"quý mão"` / năm `2022–2023`, chuyển sang đối sánh từ vựng toàn kho kết hợp kiểm tra hiệu lực metadata động theo `get_vn_today()`.
- [x] **M4 (`[VERIFIED]`):** Bổ sung các ca kiểm thử biên & phủ định (khách nhiều đơn hỏi câu `out_of_scope`/chính sách/tài khoản, hỏi chính sách hết hạn mã mới `POL-FLASH-2025` & `POL-SHIP-LEGACY` không có chữ `OLD`, LLM chết + câu ML điểm thấp phải `ESCALATE_HUMAN`) và xác minh toàn bộ suite liên quan.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn đã thực thi (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`):**
  - `python scripts/build_intent_fallback_artifacts.py`
  - `python -m pytest tests/test_robustness.py tests/test_architecture_decisions_alignment.py tests/test_guardrails.py tests/test_multi_order_disambiguation.py tests/test_data_and_pipeline_quality.py -v`
  - `python -m pytest tests/test_llm_failover_and_offline_isolation.py tests/test_mlip_evaluation.py tests/test_contracts_and_integration.py -v`
  - `python scripts/validate_skills.py`
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `python -m pytest tests/test_robustness.py tests/test_architecture_decisions_alignment.py tests/test_guardrails.py tests/test_multi_order_disambiguation.py tests/test_data_and_pipeline_quality.py -v` -> `Result:` `63 passed in 10.52s` (`0 warnings` — đã triệt tiêu hoàn toàn cảnh báo `InconsistentVersionWarning`).
  - `Command:` `python -m pytest tests/test_llm_failover_and_offline_isolation.py tests/test_mlip_evaluation.py tests/test_contracts_and_integration.py -v` -> `Result:` `30 passed` (cùng 63 test trên đạt tổng cộng `93/93 passed`).
  - `Command:` `python scripts/validate_skills.py` -> `Result:` `SKILLS VALID (3): change-impact-analysis, repo-onboarding, task-resume`.
  - `Limitations:` `Đã kiểm chứng đầy đủ ở mức unit & integration offline (DISABLE_EXTERNAL_LLM=true). Đánh giá benchmark quy mô lớn sẽ tiếp tục được mở rộng tại Task 5 và Task 6.`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Không phụ thuộc task trước (đây là Task nền tảng số 1).
- **Điểm nghẽn hiện tại:** Không còn điểm nghẽn (`None`). Đã giải quyết `OD-002` bằng `NumpyLinearBackend` (`JSON` + `.npz`, `allow_pickle=False`) không ghi đè file `.pkl` cũ và tương thích đồng nhất giữa `scikit-learn 1.6.1` (Docker) và `1.9.1` (Host/CI).
- **Giả định liên quan:** `OD-002`, `OD-005` trong [requirements.md](../product/requirements.md).

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [x] Khách hàng có nhiều đơn (`CUST-1001` / `demo-customer`) khi gửi câu hỏi `out_of_scope`, câu `confidence < 0.60`, hoặc câu dính chính sách hết hạn đều bị chặn đúng quy tắc (`allow_llm=False`), **không** bị `has_multi_order_context` cho lọt qua LLM.
- [x] Khi khách nhiều đơn hỏi đúng nghiệp vụ đơn hàng (lọc trạng thái, hỏi tổng tiền, liệt kê đơn, hủy đơn mơ hồ, hỏi tiến độ đơn vừa đặt), tính năng phân giải đa đơn hàng vẫn hoạt động chính xác 100%.
- [x] Khi LLM chính bị ngắt ở chế độ online và câu hỏi không đạt ngưỡng tin cậy ML (`< 0.60`), hệ thống chuyển nhân viên (`ESCALATE_HUMAN`) chứ không tự ý gọi regex `_semantic_fallback`.
- [x] `PolicyRetriever` không còn chứa chuỗi `"quý mão"`, `"OLD" in doc.doc_id`; phát hiện đúng cả văn bản hết hạn/thay thế tạo mới với mã `POL-*` bất kỳ (`POL-FLASH-2025`, `POL-SHIP-LEGACY`).
- [x] Toàn bộ bài kiểm thử đơn vị & tích hợp liên quan pass 100% (`93/93`) và không phát sinh cảnh báo lệch phiên bản `scikit-learn`.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-24T23:12:00+07:00` | Khởi tạo kế hoạch Task 1 tách biệt phần chốt chặn an toàn & tuân thủ `ADR-002` | Rà soát mã nguồn phát hiện `has_multi_order_context` đứng trước Case 3/4 trong `response_dispatcher.py`, `predictor.py#L321` lách sang regex, và `retriever.py#L119` lọc cứng `"OLD"` | `Observed` |
| `2026-11-24T23:45:00+07:00` | Bổ sung `NumpyLinearBackend` (`vocab.json` + `weights.npz`, `allow_pickle=False`) trong `IntentPredictor` và xuất bộ model song ngữ `VI`/`EN` vào `artifacts/models/intent/` | Tránh xung đột phiên bản `scikit-learn==1.6.1` trong Docker vs `1.9.1` trên máy host, không ghi đè các file `.pkl` cũ trong `ML-model/` và triệt tiêu 100% `InconsistentVersionWarning` | `Confirmed` |
| `2026-11-24T23:46:00+07:00` | Khóa thêm nhánh fallback số 4 trong `order_context_resolver.py` khi `len(customer_orders) > 1` và chưa có `active_order_id` | Ngăn việc khách nhiều đơn hỏi câu chính sách/ngoài phạm vi bị tự động gắn nhầm đơn hàng đầu tiên trong danh sách vào `state.active_order_id` | `Confirmed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Hoàn tất triển khai và xác minh cục bộ toàn bộ các hạng mục `M1` -> `M4` của **Task 1** (`93/93 tests passed`, `0 warnings`).
- **Hành động tiếp theo:** Báo cáo nghiệm thu Task 1 và chờ chủ dự án xác nhận chuyển sang **Task 2** ([TASK-20261124-nlu-pipeline-consolidation-and-anti-hardcoding-plan.md](TASK-20261124-nlu-pipeline-consolidation-and-anti-hardcoding-plan.md)).
- **Tham chiếu:** [REPO_GUIDE.md](../agent/REPO_GUIDE.md), [verification.md](../development/verification.md), [copilot-workflow.md](../specs/copilot-workflow.md), [intent-classification.md](../specs/intent-classification.md).

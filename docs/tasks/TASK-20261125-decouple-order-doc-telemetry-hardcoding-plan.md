# Kế Hoạch Thực Thi: Loại Bỏ Hardcode Đoán Nghĩa & Tách Lớp Fallback Tại Tầng Order, Document & Telemetry

> **Trình tự thực thi:** Thực hiện nối tiếp **Task 2b** (`TASK-20261125-decouple-nlu-offline-fallbacks`) và phối hợp đồng bộ với **Task 3** (`TASK-20261124-unify-chat-execution-memory-and-order-ssot`) để toàn bộ luồng online không còn tự đoán ý định/hành động bằng từ khóa cứng.
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261125-decouple-order-doc-telemetry-hardcoding`
- **Tên Task:** `Loại bỏ hardcode đoán nghĩa/hành động trong order_context_resolver, order_matcher, policy_filter và incident clustering; chuyển luồng online sang dùng Intent/LLM & dữ liệu thực, tách rule fallback offline ra file riêng`
- **Thời gian tạo / cập nhật:** `2026-11-25T13:35:00+07:00`
- **Trạng thái Task (`Task Status`):** `COMPLETED`
- **Trạng thái triển khai (`Implementation Status`):** `IMPLEMENTED`
- **Trạng thái kiểm thử (`Verification Status`):** `LOCALLY_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `APPROVED (Chủ dự án đã xác nhận triển khai)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. **Tại `order_context_resolver.py`:** Chấm dứt việc `resolve_scoped_order_and_guard()` tự đoán ý định bằng từ khóa (`ORDER_STATUS_FILTER_SPECS`, `is_multi_order_list_query`, `is_personal_order_portfolio_inquiry`) ở luồng online; nhận `intent_resp` / trích xuất cấu trúc từ LLM để chỉ kích hoạt phân giải đơn hàng khi intent thực sự thuộc nhóm đơn hàng, đồng thời tách bộ rule lọc trạng thái/danh sách sang `offline_order_fallback.py` chỉ chạy khi LLM tắt/lỗi.
  2. **Tại `order_matcher.py`:**
     - Xóa 4 danh sách từ khóa đoán hành động (`cancel_keywords`, `status_keywords`, `details_keywords`, `customer_list_keywords`) và logic tách `cancel_reason` ngây thơ bằng `split("vì")` / `split("do")` khỏi `extract_entities_advanced` (chỉ giữ phần regex trích xuất mã chuẩn `ORD-*`, SĐT, mã vận đơn `tracking_code` hoặc tách phần đoán action offline sang file fallback).
     - Xóa danh sách từ khóa cứng `general_intents` khỏi `EmbeddingOrderMatcher.match()`.
     - Xử lý triệt để `PromptOrderMatcher` giả (đang chỉ gọi `RuleOrderMatcher` rồi gán nhãn `"pure_prompt"`): hoặc hiện thực gọi LLM structured extraction thật (khi online), hoặc loại bỏ lớp giả lập sai sự thật.
  3. **Tại `services/document_service/src/policy_filter.py`:** Tách/chuẩn hóa `_detect_category()` và `_detect_policy_type()` để khi upload/phân tích tài liệu ở chế độ online ưu tiên trích xuất metadata có cấu trúc bằng LLM (hoặc schema đầu vào), chỉ dùng từ khóa làm fallback offline có nhãn rõ ràng.
  4. **Tại `services/telemetry_service/src/repository.py`:** Thay `_classify_incident_topic()` đang gom cụm bằng 5 nhánh từ khóa cứng (`"bão"`, `"trễ"`, `"vỡ"`, `"momo"`, `"voucher"`) sang gom cụm theo `predicted_intent` + tương đồng văn bản (TF-IDF/cosine clustering hoặc token overlap trên log thực tế) để tự phát hiện cả các nhóm sự cố mới chưa từng đặt từ khóa trước.
- **Kết quả kỳ vọng:**
  - Không còn module xử lý online nào trong `conversation_service`, `document_service`, `telemetry_service` tự ý đoán intent/action/topic bằng danh sách từ khóa cứng.
  - Mọi heuristic dự phòng (khi LLM tắt hoặc thiếu kết quả phân loại) được cô lập trong các module `offline_*_fallback.py` riêng biệt, rõ ràng.
  - `PromptOrderMatcher` không còn giả lập nhãn `"pure_prompt"` trên kết quả rule-based.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `services/conversation_service/src/dialogue_state/order_context_resolver.py` & file fallback mới `services/conversation_service/src/dialogue_state/offline_order_fallback.py`
  - `services/conversation_service/src/input_pipeline/order_matcher.py` (làm sạch `extract_entities_advanced`, `EmbeddingOrderMatcher`, `PromptOrderMatcher`)
  - `services/conversation_service/src/main.py` (truyền kết quả Intent / LLM scope vào `resolve_scoped_order_and_guard` khi phối hợp luồng xử lý)
  - `services/document_service/src/policy_filter.py`
  - `services/telemetry_service/src/repository.py` (`get_incident_clusters`)
  - Cập nhật & bổ sung kiểm thử trong `tests/test_multi_order_disambiguation.py`, `tests/test_conversation_order_pipeline.py`, `tests/test_module3_orders.py`, `tests/test_policy_audit_rollback.py`, `tests/test_order_actions_and_proactive_delay.py`
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không xóa các chốt chặn an ninh/an toàn bắt buộc (`contracts/safety.py`, `contracts/order_actions.py`, `fact_extractor.py`).
  - Không chỉnh sửa giao diện Streamlit legacy (`services/ui_service/src/views/chat_view.py`, thuộc `ADR-001` legacy) hay React UI (`frontend/`, thuộc **Task 4**).
  - Không thay đổi cấu trúc `EvaluationRunner` (thuộc **Task 5**).

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-INT-003`, `FR-DLG-001`, `FR-ORD-001`, `NFR-REL-001` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [SPEC-WF-001 (Copilot Workflow)](../specs/copilot-workflow.md)
- **ADR & Kiến trúc:** [ADR-002](../decisions/ADR-002-intent-llm-primary-ml-fallback.md), [AGENTS.md (Anti-Hardcoding Standard)](../../AGENTS.md), [TASK-20261125-decouple-nlu-offline-fallbacks-plan.md](TASK-20261125-decouple-nlu-offline-fallbacks-plan.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Thay đổi thứ tự/ngữ cảnh truyền vào bộ phân giải đơn hàng liên kết `Intent` $\leftrightarrow$ `OrderResolver` và logic gom cụm Telemetry — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Tuyệt đối không phá vỡ cơ chế bảo vệ IDOR (khóa truy xuất đơn khác chủ sở hữu `CUST-*` trước mọi bước xử lý) trong `order_context_resolver.py`.
  - Giữ nguyên khả năng chạy offline 100% khi `DISABLE_EXTERNAL_LLM=true` thông qua các module fallback tách biệt.
  - Không phát minh số liệu cụm sự cố giả trong `telemetry_service`.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án trước khi bắt đầu triển khai (và xác nhận có hoàn tác thay đổi trước đó trên `order_context_resolver.py` hay giữ nền hiện tại để làm sạch toàn bộ).

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Chuẩn hóa `order_context_resolver.py` theo Intent/LLM (`offline_order_fallback.py`):**
   - Tách `ORDER_STATUS_FILTER_SPECS`, `is_multi_order_list_query`, `is_personal_order_portfolio_inquiry` sang `services/conversation_service/src/dialogue_state/offline_order_fallback.py`.
   - Trong `resolve_scoped_order_and_guard()`:
     - Luôn chạy IDOR guard + bóc tách `ORD-*` tường minh trước.
     - Với truy vấn không có `ORD-*`: khi đã có `intent` (từ `IntentPredictor` / LLM) hoặc kết quả structured từ LLM (trích xuất `status_filter`, `is_portfolio_query`), dùng trực tiếp kết quả đó để quyết định lọc đơn hay bỏ qua (ví dụ các intent `out_of_scope`, `recover_password`, `create_account`, `return_policy` không bao giờ kích hoạt multi-order portfolio). Chỉ gọi `OfflineOrderFallback` khi chạy offline hoặc chưa có `intent`.
2. **Làm sạch `order_matcher.py`:**
   - Rút gọn `extract_entities_advanced()` chỉ làm nhiệm vụ trích xuất thực thể chuẩn (`order_id`, `phone`, `tracking_code`); loại bỏ `cancel_keywords`, `status_keywords`, `details_keywords`, `customer_list_keywords` và `split("vì")`/`split("do")` khỏi hàm trích xuất thực thể.
   - Xóa `general_intents` khỏi `EmbeddingOrderMatcher.match()` (việc lọc câu hỏi ngoài đơn hàng thuộc tầng Intent/Orchestrator, không đặt từ khóa cứng trong matcher).
   - Thay `PromptOrderMatcher` giả bằng cài đặt gọi LLM structured extraction thật (với fallback rõ ràng `method = "rule_fallback"` nếu LLM tắt/lỗi, tuyệt đối không gắn nhãn `"pure_prompt"` khi chưa gọi LLM).
3. **Chuẩn hóa `policy_filter.py` (`document_service`):**
   - Hỗ trợ phân tích `category` và `policy_type` bằng LLM structured output khi online (`not is_external_llm_disabled()`), và tách rõ bộ từ khóa heuristic sang nhánh fallback offline.
4. **Dữ liệu hóa `get_incident_clusters()` (`telemetry_service/src/repository.py`):**
   - Gom cụm dựa trên `(predicted_intent, cụm từ đặc trưng TF-IDF / token overlap)` của các bản ghi `telemetry_logs` thay vì 5 nhánh `if any(k in q ...)` cố định, giúp tự động phát hiện cả các chủ đề sự cố mới phát sinh thực tế.

---

## 7. Các bước triển khai (Milestones)

- [x] **M1 (`[VERIFIED]`):** Đã tách toàn bộ `ORDER_STATUS_FILTER_SPECS`, `is_multi_order_list_query` và `is_personal_order_portfolio_inquiry` sang `services/conversation_service/src/dialogue_state/offline_order_fallback.py`; bổ sung tham số `intent` (`NON_ORDER_INTENTS`) vào `resolve_scoped_order_and_guard()` để bỏ qua heuristic khi đã biết intent phi-đơn-hàng (phần hợp nhất thứ tự gọi trong `conversation_service/src/main.py` tiếp tục đồng bộ tại Task 3).
- [x] **M2 (`[VERIFIED]`):** Đã dọn sạch `order_matcher.py`, tách `cancel_keywords`/`status_keywords`/`details_keywords`/`customer_list_keywords` & `general_intents` sang `services/conversation_service/src/input_pipeline/offline_order_matcher_fallback.py`, và sửa `PromptOrderMatcher` gọi LLM JSON extraction thật (chỉ gắn `"pure_prompt"` khi LLM chạy thành công, offline trả về `"rule_fallback"`).
- [x] **M3 (`[VERIFIED]`):** Đã tách toàn bộ heuristic của `policy_filter.py` sang `services/document_service/src/offline_policy_fallback.py` và thay `_classify_incident_topic()` trong `services/telemetry_service/src/repository.py` bằng thuật toán gom cụm Union-Find trên `(predicted_intent, token_overlap)` không phụ thuộc từ khóa đặt trước.
- [x] **M4 (`[VERIFIED]`):** Đã bổ sung kiểm thử hồi quy, kiểm thử cụm sự cố chưa từng khai báo (`test_unseen_incident_topic_clusters_dynamically_without_hardcoded_keywords`), kiểm thử `PromptOrderMatcher` (`offline` vs `online`), kiểm thử tĩnh không rò rỉ bảng từ khóa, và xác minh toàn bộ 8 file test liên quan.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn đã thực thi (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`):**
  - `python -m pytest tests/test_multi_order_disambiguation.py tests/test_conversation_order_pipeline.py tests/test_module3_orders.py tests/test_policy_filter.py tests/test_policy_audit_rollback.py tests/test_order_actions_and_proactive_delay.py tests/test_guardrails.py tests/test_conversation_service.py -v`
  - Kiểm tra liên kết Markdown toàn bộ `docs/`.
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `python -m pytest tests/test_multi_order_disambiguation.py tests/test_conversation_order_pipeline.py tests/test_module3_orders.py tests/test_policy_filter.py tests/test_policy_audit_rollback.py tests/test_order_actions_and_proactive_delay.py tests/test_guardrails.py tests/test_conversation_service.py -v` -> `Result:` **`97 passed in 9.22s`** (`0 failed`).
  - `Command:` Kiểm tra liên kết trong `docs/` -> `Result:` `DOCS_LINKS_OK: 0 broken links`.
  - `Limitations:` `Đã kiểm chứng đầy đủ unit, offline isolation, mock online PromptOrderMatcher và dynamic incident clustering. Việc truyền intent trực tiếp vào resolve_scoped_order_and_guard khi hợp nhất /chat & /chat_stream sẽ hoàn thiện nốt trong Task 3.`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Thực hiện sau **Task 2b** (`TASK-20261125-decouple-nlu-offline-fallbacks`); phần thay đổi thứ tự gọi trong `conversation_service/src/main.py` tiếp tục đồng bộ gọn với **Task 3**.
- **Điểm nghẽn hiện tại:** Không còn điểm nghẽn (`None`).

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [x] `order_context_resolver.py` sạch hoàn toàn khỏi các bảng từ khóa đoán ý định; toàn bộ heuristic dự phòng nằm trong `offline_order_fallback.py`.
- [x] `order_matcher.py` không còn chứa `cancel_keywords` / `status_keywords` / `details_keywords` / `customer_list_keywords`, `general_intents`, hay `PromptOrderMatcher` giả nhãn `"pure_prompt"`.
- [x] `telemetry_service/src/repository.py` gom cụm sự cố dựa trên `predicted_intent` + tương đồng từ vựng (Union-Find), phát hiện được cụm sự cố mới không cần khai báo từ khóa trước.
- [x] Toàn bộ test liên quan pass 100% ở cả chế độ offline lẫn mock online (`97/97 passed`), không làm suy giảm bảo vệ IDOR hay phân giải đa đơn hàng.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-25T13:05:00+07:00` | Khởi tạo Task loại bỏ hardcode tại `order_context_resolver`, `order_matcher`, `policy_filter` và `telemetry_service/repository.py` | Rà soát trực tiếp phát hiện `order_matcher.py#L115-L148` cài 4 bảng từ khóa & `PromptOrderMatcher` giả, `order_context_resolver.py` chạy đoán từ khóa trước Intent, và `repository.py#L882-L895` dùng 5 nhánh `if any(k in q...)` | `Observed` |
| `2026-11-25T13:33:00+07:00` | Nâng cấp thuật toán gom cụm trong `get_incident_clusters()` sang Union-Find không phụ thuộc thứ tự dòng | Lần chạy đầu gặp lỗi `count 3 != 4` do `ORDER BY rowid DESC` tách đơn lẻ khi một truy vấn bắc cầu xuất hiện muộn; Union-Find khắc phục triệt để và đạt `97/97 passed` | `Confirmed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Triển khai và kiểm chứng cục bộ toàn bộ `M1` -> `M4` của Task này (`97/97 passed`, `DOCS_LINKS_OK`).
- **Hành động tiếp theo:** Chuyển sang **Task 3** ([TASK-20261124-unify-chat-execution-memory-and-order-ssot-plan.md](TASK-20261124-unify-chat-execution-memory-and-order-ssot-plan.md)) để hợp nhất `/chat` & `/chat_stream`, `MemoryWorker` và `OrderTools`.
- **Tham chiếu:** [REPO_GUIDE.md](../agent/REPO_GUIDE.md), [TASK_PROTOCOL.md](../agent/TASK_PROTOCOL.md), [AGENTS.md](../../AGENTS.md).

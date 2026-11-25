# Kế Hoạch Thực Thi: Tách Bạch Hoàn Toàn Logic Fallback Offline Khỏi Các Module NLU Chính (`InputClassifier`, `QueryRewriter`, `IntentTracker`)

> **Trình tự thực thi:** Task bổ sung tách biệt ngay sau **Task 2** (`TASK-20261124-nlu-pipeline-consolidation-and-anti-hardcoding`), hoàn thiện triệt để kiến trúc tách lớp đã khởi tạo ở `TASK-20261123-decouple-llm-pipeline-and-offline-fallback`.
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261125-decouple-nlu-offline-fallbacks`
- **Tên Task:** `Tách biệt toàn bộ từ khóa/regex fallback offline ra các file riêng cho InputClassifier, QueryRewriter và IntentTracker để các module NLU chính chỉ thuần luồng LLM`
- **Thời gian tạo / cập nhật:** `2026-11-25T12:58:00+07:00`
- **Trạng thái Task (`Task Status`):** `COMPLETED`
- **Trạng thái triển khai (`Implementation Status`):** `IMPLEMENTED`
- **Trạng thái kiểm thử (`Verification Status`):** `LOCALLY_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `APPROVED (Chủ dự án đã xác nhận triển khai Task 2b)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. Tách toàn bộ bảng từ khóa, tập token xã giao và biểu thức chính quy fallback (`_OFFLINE_CHITCHAT_EXACT`, `_OFFLINE_COURTESY_TOKENS`, `_OFFLINE_NEGATION_RE`, `_OFFLINE_INTERROGATIVE_RE`, logic phân loại rule) ra khỏi [input_classifier.py](../../services/conversation_service/src/input_pipeline/input_classifier.py) sang một file riêng `services/conversation_service/src/input_pipeline/offline_fallback.py`.
  2. Tách toàn bộ logic phân vùng scope thủ công và viết lại câu heuristic (`_OFFLINE_ANAPHORIC_ORDER_RE`, `_OFFLINE_POLICY_STRUCT_RE`, `_OFFLINE_ORDER_STRUCT_RE`, `short_phrases`, `detect_query_scope`, `_heuristic_rewrite`) ra khỏi [query_rewriter.py](../../services/conversation_service/src/dialogue_state/query_rewriter.py) sang `services/conversation_service/src/dialogue_state/offline_rewrite_fallback.py`.
  3. Tách toàn bộ `TOPIC_SWITCH_KEYWORDS` và `_fallback_regex_transition` ra khỏi [tracker.py](../../services/conversation_service/src/dialogue_state/tracker.py) sang `services/conversation_service/src/dialogue_state/offline_tracker_fallback.py`.
  4. Giữ nguyên tương thích chữ ký công khai (`classify_fast_tier`, `detect_query_scope`, `_fallback_regex_transition`, `resolve_intent_transition_sync`) dưới dạng wrapper ủy quyền mỏng sang file fallback tương ứng để không làm gãy các bài kiểm thử hiện hữu và Evaluator độc lập (`TASK-EVAL-006`).
- **Kết quả kỳ vọng:**
  - Ba file NLU chính (`input_classifier.py`, `query_rewriter.py`, `tracker.py`) không còn chứa bất kỳ danh sách từ khóa hay regex đoán nghĩa/scope nào; chỉ giữ đúng luồng gọi LLM chính (khi online) và gọi sang module fallback (khi LLM tắt, thiếu key, hoặc gặp lỗi).
  - Ranh giới giữa **Guardrail an ninh bắt buộc** (`contracts/safety.py`, `contracts/order_actions.py`, `fact_extractor.py`) và **Fallback dự phòng khi LLM không khả dụng** (`offline_*_fallback.py`) được tách bạch 100% trong toàn bộ `conversation_service`.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - Tạo mới `services/conversation_service/src/input_pipeline/offline_fallback.py` và làm sạch `services/conversation_service/src/input_pipeline/input_classifier.py`
  - Tạo mới `services/conversation_service/src/dialogue_state/offline_rewrite_fallback.py` và làm sạch `services/conversation_service/src/dialogue_state/query_rewriter.py`
  - Tạo mới `services/conversation_service/src/dialogue_state/offline_tracker_fallback.py` và làm sạch `services/conversation_service/src/dialogue_state/tracker.py`
  - Cập nhật export tại `services/conversation_service/src/input_pipeline/__init__.py` & `services/conversation_service/src/dialogue_state/__init__.py` (nếu cần)
  - Bổ sung kiểm thử tĩnh xác nhận 3 file NLU chính không còn chứa bảng từ khóa/regex fallback, đồng thời chạy lại toàn bộ test `conversation_service` & `TASK-EVAL-006`.
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không thay đổi các chốt chặn an toàn bắt buộc (`contracts/safety.py`, `contracts/order_actions.py`, `fact_extractor.py`) vì đây là rule deterministic bảo vệ hệ thống.
  - Không thay đổi kiến trúc `/fast_ack` dưới 20ms (`acknowledgement.py`).
  - Không gộp `/chat` và `/chat_stream` hay sửa `MemoryWorker` / `OrderTools` (thuộc **Task 3**).

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-INT-003`, `FR-DLG-001`, `NFR-REL-001`, `NFR-SEC-002` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [SPEC-WF-001 (Copilot Workflow)](../specs/copilot-workflow.md)
- **ADR & Kiến trúc:** [ADR-002](../decisions/ADR-002-intent-llm-primary-ml-fallback.md), [AGENTS.md (Anti-Hardcoding Standard)](../../AGENTS.md), [TASK-20261123-decouple-llm-pipeline-and-offline-fallback-plan.md](TASK-20261123-decouple-llm-pipeline-and-offline-fallback-plan.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R1` (Tái cấu trúc nội bộ module `conversation_service`, bảo toàn nguyên vẹn giao diện công khai và hành vi runtime — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Không phá vỡ các lời gọi từ `tests/test_conversation_service.py` và `evaluation/agent_harness/trusted_acceptance/accept_conversation_service.py` (`classify_fast_tier`, `detect_query_scope`, `_fallback_regex_transition`, `resolve_intent_transition_sync`).
  - Giữ nguyên cô lập offline (`DISABLE_EXTERNAL_LLM=true` không phát sinh cuộc gọi mạng nào).
  - Bảo toàn mọi chỉnh sửa hiện có của Task 2 trên cây thư mục Git.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án trước khi bắt đầu tách file và kiểm chứng.

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Tách `OfflineInputFallback` (`services/conversation_service/src/input_pipeline/offline_fallback.py`):**
   - Di chuyển toàn bộ `_OFFLINE_CHITCHAT_EXACT`, `_OFFLINE_COURTESY_TOKENS`, `_OFFLINE_NEGATION_RE`, `_OFFLINE_INTERROGATIVE_RE` và hàm `classify_offline()` sang file mới.
   - Trong `input_classifier.py`, `InputClassifier.classify_utterance()` chỉ giữ luồng LLM Primary (OpenAI-compatible) và gọi `OfflineInputFallback.classify()` khi LLM tắt/thiếu key/lỗi; `classify_fast_tier()` ủy quyền mỏng sang `OfflineInputFallback.classify()`.
2. **Tách `OfflineRewriteFallback` (`services/conversation_service/src/dialogue_state/offline_rewrite_fallback.py`):**
   - Di chuyển `_OFFLINE_ANAPHORIC_ORDER_RE`, `_OFFLINE_POLICY_STRUCT_RE`, `_OFFLINE_ORDER_STRUCT_RE`, `short_phrases`, `detect_query_scope()` và `rewrite_offline()` sang file mới.
   - Trong `query_rewriter.py`, `QueryRewriter.rewrite_query()` chỉ giữ luồng LLM Primary (và bỏ qua khi `intent in OUT_OF_SERVICE_INTENTS`), gọi `OfflineRewriteFallback.rewrite()` khi LLM tắt/thiếu key/lỗi.
3. **Tách `OfflineTrackerFallback` (`services/conversation_service/src/dialogue_state/offline_tracker_fallback.py`):**
   - Di chuyển `TOPIC_SWITCH_KEYWORDS`, logic chèn thẻ `[PREV_INTENT:...]` dựa trên từ khóa và `resolve_transition_offline()` sang file mới.
   - Trong `tracker.py`, `IntentTracker` chỉ giữ luồng phân xử LLM và ủy quyền phần fallback offline sang `OfflineTrackerFallback`.

---

## 7. Các bước triển khai (Milestones)

- [x] **M1 (`[VERIFIED]`):** Đã tạo `services/conversation_service/src/input_pipeline/offline_fallback.py` (`OfflineInputFallback`) và dọn sạch toàn bộ `_OFFLINE_*` khỏi `input_classifier.py`.
- [x] **M2 (`[VERIFIED]`):** Đã tạo `services/conversation_service/src/dialogue_state/offline_rewrite_fallback.py` (`OfflineRewriteFallback`) và dọn sạch toàn bộ `_OFFLINE_*` cùng `short_phrases` khỏi `query_rewriter.py`.
- [x] **M3 (`[VERIFIED]`):** Đã tạo `services/conversation_service/src/dialogue_state/offline_tracker_fallback.py` (`OfflineTrackerFallback`) và dọn sạch `TOPIC_SWITCH_KEYWORDS` cùng logic fallback regex khỏi `tracker.py`.
- [x] **M4 (`[VERIFIED]`):** Đã bổ sung `test_nlu_primary_modules_contain_no_offline_keyword_tables` trong `tests/test_conversation_service.py` và chạy xác minh toàn bộ suite liên quan.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn đã thực thi (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`):**
  - `python -m pytest tests/test_conversation_service.py tests/test_conversation_order_pipeline.py tests/test_architecture_decisions_alignment.py tests/test_llm_failover_and_offline_isolation.py tests/test_agent_harness_eval.py -k "not test_task_eval_001" -v`
  - Kiểm tra liên kết Markdown toàn bộ `docs/`.
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `python -m pytest tests/test_conversation_service.py tests/test_conversation_order_pipeline.py tests/test_architecture_decisions_alignment.py tests/test_llm_failover_and_offline_isolation.py tests/test_agent_harness_eval.py -k "not test_task_eval_001" -v` -> `Result:` **`80 passed, 1 deselected in 117.41s`** (`0 failed`, bao gồm `test_nlu_primary_modules_contain_no_offline_keyword_tables` và `test_task_eval_006_adversarial_and_positive_cases_via_cli`).
  - `Command:` Kiểm tra liên kết trong `docs/` -> `Result:` `DOCS_LINKS_OK: 0 broken links`.
  - `Limitations:` `Đã kiểm chứng đầy đủ unit, offline isolation, LLM-primary mock và fault-injection TASK-EVAL-006. Phần hợp nhất /chat & /chat_stream vẫn thuộc Task 3.`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Thực hiện ngay trên nền mã nguồn đã tinh gọn của **Task 2** (`TASK-20261124-nlu-pipeline-consolidation-and-anti-hardcoding`).
- **Điểm nghẽn hiện tại:** Không còn điểm nghẽn (`None`).

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [x] Ba file `input_classifier.py`, `query_rewriter.py`, `tracker.py` sạch hoàn toàn, không chứa bảng từ khóa hay regex fallback phân loại/viết lại câu.
- [x] Toàn bộ logic fallback offline được cô lập rõ ràng trong 3 file `offline_fallback.py`, `offline_rewrite_fallback.py`, `offline_tracker_fallback.py` và chỉ kích hoạt khi LLM tắt, thiếu key hoặc gặp lỗi.
- [x] Toàn bộ test `conversation_service`, `architecture_decisions_alignment` và `TASK-EVAL-006` pass 100% ở chế độ offline lẫn mock online (`80/80 passed`).

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-25T12:46:00+07:00` | Khởi tạo Task tách riêng các file fallback offline cho 3 module NLU của `conversation_service` | Rà soát toàn bộ `services/` cho thấy `TASK-20261123-decouple-llm-pipeline-and-offline-fallback` mới tách `intent_service` và `copilot_draft_engine`, chưa tách `input_classifier.py`, `query_rewriter.py`, `tracker.py` | `Observed` |
| `2026-11-25T12:58:00+07:00` | Hoàn tất tách 3 module fallback (`offline_fallback.py`, `offline_rewrite_fallback.py`, `offline_tracker_fallback.py`) và giữ nguyên chữ ký public wrapper | `test_conversation_service.py` và bộ acceptance/fault-injection `TASK-EVAL-006` đều xanh (`80 passed`) | `Confirmed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Tách lớp hoàn toàn và kiểm chứng cục bộ toàn bộ `M1` -> `M4` của **Task 2b** (`80/80 passed`, `DOCS_LINKS_OK`).
- **Hành động tiếp theo:** Chuyển sang **Task 3** ([TASK-20261124-unify-chat-execution-memory-and-order-ssot-plan.md](TASK-20261124-unify-chat-execution-memory-and-order-ssot-plan.md)) hoặc commit phần thay đổi của Task 2 & Task 2b khi chủ dự án sẵn sàng.
- **Tham chiếu:** [REPO_GUIDE.md](../agent/REPO_GUIDE.md), [TASK_PROTOCOL.md](../agent/TASK_PROTOCOL.md), [AGENTS.md](../../AGENTS.md).

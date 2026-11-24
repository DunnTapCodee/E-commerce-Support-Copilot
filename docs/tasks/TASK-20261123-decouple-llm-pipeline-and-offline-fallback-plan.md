# Kế Hoạch Thực Thi: Tách Bạch Luồng LLM Chính Khỏi Tầng Fallback & Dọn Sạch Hardcode Kiến Trúc

> **Nguồn yêu cầu:** Rà soát thực tế sau khi tích hợp `vantoanbk57/deepseek-v4.1-flash` — mã nguồn hiện trộn lẫn nhiều rule/template hardcode vào chung luồng xử lý chính của LLM, gây khó bảo trì và dễ chặn nhầm phản hồi hợp lệ.
> **Nguyên tắc:** Tuân thủ `Engineering & Generalization Standard (Anti-Hardcoding)` trong `AGENTS.md`. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-decouple-llm-pipeline-and-offline-fallback`
- **Tên Task:** `Tách bạch hoàn toàn Primary Online Pipeline (LLM + Data-Driven Context + Hard Safety Gates) khỏi tầng Offline/Unavailable Fallback và gom cấu hình model về một nguồn`
- **Thời gian tạo / cập nhật:** `2026-11-23T23:15:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `VERIFIED (Offline CI + Live Docker vantoanbk57/deepseek-v4.1-flash)`
- **Trạng thái phê duyệt:** `APPROVED`

---

## 2. Hiện trạng & Vấn đề quan sát được (`Observed`)

1. **Luồng chính (`Online LLM`) bị trộn lẫn với các nhánh hardcode/template tĩnh:**
   - `services/conversation_service/src/policies/copilot_draft_engine.py`:
     - Trước khi gọi LLM (`generate_draft`), có các nhánh short-circuit cứng theo từ khóa (`q_clean in {"oce", "ok", ...}`, `["ronaldo", "messi", "thời tiết", ...]`, và macro `[POL-REFUND-001]` cứng cho `request_refund`/`payment_issue`).
     - Chứa luôn `_build_semantic_fallback_draft()` (~150 dòng template tĩnh) ngay trong cùng class sinh nháp LLM.
   - `services/conversation_service/src/policies/response_dispatcher.py`:
     - Lặp lại danh sách từ khóa off-topic (`["ronaldo", "messi", ...]`) và câu trả lời voucher hardcode ở Case 3.
   - `services/conversation_service/src/main.py`:
     - `_resolve_scoped_order_and_guard()` hiện dài >250 dòng và trộn lẫn cả query DB lẫn các từ khóa lọc trạng thái/danh sách ngay trong entrypoint `main.py`.
2. **Intent Semantic Fallback & Keyword Matcher rải rác:**
   - `services/intent_service/src/llm_classifier.py` (`_semantic_fallback`) chứa ~90 dòng regex cứng cho các câu mẫu; nên tách thành module `offline_fallback.py` riêng thay vì nằm trong `LLMIntentClassifier`.
   - `services/conversation_service/src/input_pipeline/order_matcher.py` chứa danh sách từ khóa `cancel_keywords`, `status_keywords`, `details_keywords`, `customer_list_keywords`.
3. **Cấu hình `DEFAULT_OPENAI_MODEL` bị lặp lại ở nhiều nơi:**
   - Giá trị mặc định `vantoanbk57/deepseek-v4.1-flash` đang khai báo rời rạc tại `contracts/release_config.py`, `conversation_service/src/config.py`, `copilot_draft_engine.py`, `document_service/src/config.py`, `intent_service/src/llm_classifier.py`, `predictor.py`, và `rag_service/src/generator.py`.
4. **Grounding / Safety Envelope chặn nhầm câu trả lời đa đơn của LLM (`Observed` ở test live `vantoanbk57/deepseek-v4.1-flash`):**
   - Khi `vantoanbk57/deepseek-v4.1-flash` trả lời danh sách nhiều đơn hợp lệ (VD: *"mình có mấy đơn hàng đã giao nhỉ"*, *"các đơn hàng nào thanh toán bằng zalo pay"*), bước `evaluate_runtime_safety_envelope` / `evaluate_response_faithfulness` trong `contracts/safety.py` đang chấm thấp/chặn nhầm (`ESCALATE_HUMAN`) khi đối chiếu câu trả lời tổng hợp đơn hàng với tài liệu RAG trích xuất.

---

## 3. Kiến trúc mục tiêu & Kế hoạch triển khai

### 3.1. Tách bạch 2 tầng rõ ràng (`Primary Online` vs. `Offline Fallback`)

1. **Tầng 1 — Primary Online Pipeline (khi LLM khả dụng):**
   - **Order Context Resolver (`services/conversation_service/src/dialogue_state/order_context_resolver.py`):**
     - Tách toàn bộ `_resolve_scoped_order_and_guard`, `_compute_portfolio_stats`, `_filter_orders_by_dynamic_attributes` khỏi `main.py`.
     - Chỉ làm nhiệm vụ **data-driven**: truy vấn đơn theo `customer_id`, đối chiếu `order_id`/tracking/item, tính `portfolio_stats` thực tế và truyền full context cho LLM (không chen regex đoán câu hỏi ngoài schema DB).
   - **Copilot Draft Engine (`copilot_draft_engine.py`):**
     - Chỉ làm đúng việc ghép 6 lớp context (`build_full_context_prompt`) + gọi LLM (`vantoanbk57/deepseek-v4.1-flash`) / stream.
     - Bỏ các `if/elif` đoán cụm từ chào hỏi/off-topic trước khi gọi LLM (LLM tự xử lý theo rule trong System Prompt).
   - **Response Policy Dispatcher (`response_dispatcher.py`):**
     - Chỉ giữ các **Deterministic Hard Safety Gates** (Prompt Injection, Cross-Customer IDOR, Manipulation/Voucher/Warehouse/Brand Bait, Financial Gate, Temporal Policy Expired Guard, Unavailable/Low-Confidence Escalation), bỏ danh sách từ khóa off-topic cứng và câu trả lời voucher hardcoded.
   - **Safety Grounding cho Multi-Order (`contracts/safety.py`):**
     - Khi `order_data` / `multi_order_context` có danh sách `candidates` và `computed_summary`, chuẩn hóa cơ chế kiểm tra faithfulness & numeric grounding để không chặn nhầm câu trả lời liệt kê/tổng hợp đúng từ dữ liệu DB, trong khi vẫn chặn 100% số liệu ảo hoặc cam kết tài chính trái phép.

2. **Tầng 2 — Offline / Unavailable Fallback (tách module riêng):**
   - Tạo **`services/conversation_service/src/policies/offline_fallback.py`**:
     - Chứa toàn bộ `OfflineDraftFallback` (chuyển `_build_semantic_fallback_draft` và các macro an toàn từ `copilot_draft_engine.py` sang đây).
     - Chỉ được gọi khi LLM trả về `None` (timeout/lỗi mạng) hoặc `DISABLE_EXTERNAL_LLM=true`.
   - Tạo **`services/intent_service/src/offline_fallback.py`**:
     - Chứa bộ phân loại dự phòng offline (tách `_semantic_fallback` ra khỏi `LLMIntentClassifier`), giữ nguyên hành vi fail-closed `unavailable_fallback` khi ở chế độ không có fallback.

3. **Gom cấu hình model mặc định về 1 nguồn (`contracts/llm_failover.py`):**
   - Khai báo `DEFAULT_OPENAI_MODEL = "vantoanbk57/deepseek-v4.1-flash"` (và `get_default_openai_model()`) tại `contracts/llm_failover.py`; tất cả các service (`conversation_service`, `intent_service`, `document_service`, `rag_service`, `release_config.py`) import từ đây.

---

## 4. Phạm vi triển khai (`In Scope` / `Non-Goals`)

- **In Scope:**
  - `contracts/llm_failover.py` & `contracts/release_config.py` (Single source of truth cho `DEFAULT_OPENAI_MODEL`).
  - `contracts/safety.py` (Sửa grounding multi-order để LLM không bị chặn nhầm khi trả lời tổng hợp đơn).
  - `services/conversation_service/src/dialogue_state/order_context_resolver.py` (mới, tách từ `main.py`).
  - `services/conversation_service/src/policies/offline_fallback.py` (mới, tách từ `copilot_draft_engine.py`).
  - `services/conversation_service/src/policies/copilot_draft_engine.py`, `response_dispatcher.py`, `main.py`.
  - `services/intent_service/src/offline_fallback.py` (mới, tách từ `llm_classifier.py`) & `llm_classifier.py`.
  - Giữ tương thích toàn bộ test offline hiện có + bổ sung test kiểm tra tách bạch Online vs. Offline Fallback.
- **Non-Goals:**
  - Không thay đổi schema API của Gateway/Frontend hoặc hành vi Hard Safety Gates (IDOR, Prompt Injection, Financial/Voucher/Warehouse, Temporal Policy).
  - Không thay đổi dữ liệu đơn hàng `data/mock_orders.json`.

---

## 5. Tiêu chí Nghiệm thu (`Definition of Done`)

- [ ] `DEFAULT_OPENAI_MODEL` chỉ khai báo duy nhất tại 1 nơi trong `contracts/llm_failover.py`.
- [ ] `CopilotDraftEngine` và `LLMIntentClassifier` không còn nhúng khối logic fallback regex/template tĩnh trực tiếp bên trong; tầng fallback nằm tách biệt ở `offline_fallback.py`.
- [ ] `services/conversation_service/src/main.py` gọn sạch, ủy quyền phần phân giải đơn hàng cho `order_context_resolver.py`.
- [ ] Khi chạy live với `vantoanbk57/deepseek-v4.1-flash` (`CUST-1001`), các câu *"mình có mấy đơn hàng đã giao nhỉ"*, *"tổng mình đã thanh toán bao nhiêu tiền rồi"*, *"ko tính đc à"*, *"các đơn hàng nào thanh toán bằng zalo pay"* đều đi qua LLM thành công (không bị `evaluate_runtime_safety_envelope` chặn nhầm), trả lời đúng số liệu và không hardcode cụm từ.
- [ ] Toàn bộ CI offline suite (`STATIC_GUARD_CLEAN`, `validate_skills.py`, `validate-manifest`, `smoke-test --quiet`, `pytest`, `tsc --noEmit`, `npm run test:unit`) pass 100%.

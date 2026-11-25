# Kế Hoạch Thực Thi (Task 2/6): Tinh Gọn Pipeline NLU, Khử 5 Tầng Regex Chồng Chéo, Tối Ưu Lời Gọi LLM & Xóa Bỏ Hardcode/Mã Thừa

> **Trình tự thực thi:** **Bước 2 / 6** — Thực hiện ngay sau khi hoàn tất **Task 1** (`TASK-20261124-guardrail-integrity-and-intent-adr002-alignment`).
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261124-nlu-pipeline-consolidation-and-anti-hardcoding`
- **Tên Task:** `Sửa lỗi dead-code trong InputClassifier, hợp nhất nhận diện chủ đề câu đệm, sửa lỗi ép mã đơn trong QueryRewriter, giảm số lượt gọi LLM dư thừa và dọn sạch hardcode/dead-code Gemini`
- **Thời gian tạo / cập nhật:** `2026-11-25T00:19:00+07:00`
- **Trạng thái Task (`Task Status`):** `COMPLETED`
- **Trạng thái triển khai (`Implementation Status`):** `IMPLEMENTED`
- **Trạng thái kiểm thử (`Verification Status`):** `LOCALLY_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `APPROVED (Chủ dự án đã duyệt triển khai Task 2 và xác nhận xóa các hàm _call_gemini() chết)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. Khắc phục lỗi logic tại `InputClassifier` (`input_classifier.py#L44-L95`), nơi `_QUESTION_PATTERNS` quá rộng và điều kiện `len(words) >= 4` đang ép 99% câu nói thành `"new_question"`, biến Tier 2 LLM thành mã chết (dead-code) và làm hỏng hoàn toàn khả năng nhận diện câu bổ sung thông tin (`fact_supplement`, ví dụ `"Mã đơn là ORD-1003 nhé"`, `"Màu đen size L"`).
  2. Chấm dứt tình trạng 5 nơi cùng viết lại bộ regex phân loại chủ đề rời rạc; xóa các nhãn intent tự chế ngoài quy chuẩn (`price_inquiry`, `general_inquiry`), xóa danh sách từ khóa đối phó test (`ronaldo`, `messi`, `giá xăng`, `phương trình`), và sửa các câu xưng hô sai chuẩn (`"Bạn vui lòng cho shop xin..."` -> `"em - anh/chị"`).
  3. Sửa `QueryRewriter.detect_query_scope()` không tự tiện ép các câu hỏi tài khoản/mật khẩu/chung vào `SCOPE_ORDER_SPECIFIC` (gây chèn nhầm mã đơn làm nhiễu truy vấn BM25 RAG), đồng thời cắt bỏ lượt gọi LLM thứ 3 bị thừa trong `IntentTracker.resolve_intent_transition` khi `LLMIntentClassifier` đã xử lý ngữ cảnh.
  4. Làm sạch `OfflineDraftFallback` để tổng hợp trực tiếp từ danh sách `citations` thực tế thay vì bịa cứng `"30 ngày"` hay chèn mã ảo `[POL-INFO]`, và xóa hoàn toàn các hàm `_call_gemini()` chết cùng docstrings lỗi thời (`Gemini 2.5 Flash`, `openai-gpt-oss-20b`, `gemini-3.8-flash`).
- **Kết quả kỳ vọng:**
  - Pipeline tiền xử lý hội thoại gọn nhẹ, mạch lạc, đúng ngữ nghĩa từng loại đầu vào (`chitchat`, `fact_supplement`, `negation_reversal`, `new_question`), giảm độ trễ và chi phí token mỗi lượt chat.
  - Toàn bộ phản hồi đệm và bản nháp dự phòng offline tuân thủ 100% quy tắc xưng hô `"em - anh/chị"` và chỉ trích dẫn mã `[POL-*]` có thật từ tài liệu truy xuất.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `services/conversation_service/src/input_pipeline/input_classifier.py`
  - `services/conversation_service/src/policies/acknowledgement.py` & logic `/fast_ack` trong `services/conversation_service/src/main.py`
  - `services/conversation_service/src/dialogue_state/query_rewriter.py`
  - `services/conversation_service/src/dialogue_state/tracker.py`
  - `services/conversation_service/src/policies/offline_fallback.py`
  - Dọn dẹp dead-code Gemini & chuẩn hóa docstrings tại: `services/intent_service/src/llm_classifier.py`, `services/rag_service/src/generator.py`, `services/conversation_service/src/policies/copilot_draft_engine.py`, `services/conversation_service/src/config.py`
  - Kiểm thử đơn vị cho `InputClassifier`, `QueryRewriter`, `CustomerAcknowledgementEngine`, `OfflineDraftFallback`
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không sửa thứ tự chốt chặn của `ResponsePolicyDispatcher` hay `IntentPredictor` (đã xử lý ở **Task 1**).
  - Không gộp `/chat` và `/chat_stream` hay sửa `MemoryWorker` / `OrderTools` (thuộc **Task 3**).
  - Không sửa code giao diện React `frontend/` (thuộc **Task 4**).

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-INT-001`, `FR-INT-003`, `FR-INT-005`, `FR-DLG-001`, `FR-RAG-002`, `FR-UI-003`, `NFR-COST-001`, `NFR-PERF-001` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [SPEC-WF-001](../specs/copilot-workflow.md), [SPEC-INT-001](../specs/intent-classification.md)
- **ADR & Kiến trúc:** [ADR-002](../decisions/ADR-002-intent-llm-primary-ml-fallback.md), [AGENTS.md (Anti-Hardcoding Standard)](../../AGENTS.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Tinh chỉnh luồng phân loại câu nói, viết lại truy vấn và dọn dẹp phương thức không dùng ở nhiều service — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Giữ tương thích chữ ký hàm công khai đang được gọi bởi các bài test hiện hữu (hoặc cập nhật đồng bộ nơi gọi nội bộ mà không phá vỡ API HTTP).
  - Đảm bảo kiểm tra `test_openai_compatible_does_not_silently_fallback_to_gemini_in_rag_or_draft` trong `tests/test_architecture_decisions_alignment.py` tiếp tục hợp lệ hoặc được cập nhật phản ánh việc gỡ bỏ hoàn toàn nhánh Gemini chết (nếu được duyệt).
  - Không hardcode danh sách câu mẫu trong `InputClassifier` hay `QueryRewriter`.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án về việc xóa hẳn các hàm `_call_gemini()` không còn sử dụng (theo `FR-INT-003` chỉ dùng OpenAI-compatible CKEY.VN) hay giữ lại dưới dạng adapter riêng.

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Thiết kế lại `InputClassifier` (`input_classifier.py`):**
   - Tách rõ luật Tier 1 chỉ bắt các trường hợp **chắc chắn 100% không mơ hồ**:
     - `chitchat`: Câu chỉ chứa từ xã giao thuần túy, không có động từ/danh từ nghiệp vụ và không có thực thể đơn hàng.
     - `negation_reversal`: Khớp cấu trúc phủ định chuyển ý rõ ràng (`thôi không... nữa`, `đổi ý...`, `khoan đã...`).
     - `fact_supplement`: Câu cung cấp thực thể (`order_id`, `phone`, `carrier`, địa chỉ/màu/size ngắn) **không chứa từ để hỏi** (`sao`, `khi nào`, `bao lâu`, `bao nhiêu`, `không`, `chưa`, `?`) khi phiên đang có `active_intent`.
     - `new_question`: Chỉ bắt nhanh ở Tier 1 khi có từ nghi vấn/yêu cầu hành động rõ ràng; xóa dòng `if len(words) >= 4: return "new_question"` để các câu lấp lửng thực sự được phân xử bởi ngữ cảnh / Tier 2 LLM (với `max_tokens=150` thay vì `1000`).
2. **Chuẩn hóa `CustomerAcknowledgementEngine` & `/fast_ack`:**
   - Tái sử dụng bộ phân loại nhanh chuẩn 16 `TARGET_INTENTS` dùng chung thay vì viết lặp regex ở cả `main.py` lẫn `acknowledgement.py`; xóa các từ khóa `ronaldo`, `messi`, `giá xăng`; định tuyến mẫu câu chờ trực tiếp từ tên `intent` + `input_type` + `facts`; sửa toàn bộ xưng hô sang `"em - anh/chị"`.
3. **Sửa `QueryRewriter` & Tối ưu lượt gọi LLM trong `IntentTracker`:**
   - Trong `QueryRewriter.detect_query_scope()`: Thêm `SCOPE_GENERAL_NON_ORDER` (hoặc mở rộng `SCOPE_POLICY_GENERAL`) cho các câu hỏi về tài khoản, mật khẩu, bảo hành chung, hướng dẫn sử dụng không nhắc tới đơn hàng cá nhân — chỉ chọn `SCOPE_ORDER_SPECIFIC` khi câu nói có thực thể đơn hàng, đại từ chỉ định (`nó`, `đơn này`, `kiện hàng`, `bao giờ giao`, `hủy`) hoặc phiên đang theo dõi đơn cụ thể. Giảm `max_tokens` từ `1500` xuống `200`, và bỏ qua gọi LLM rewrite khi câu hỏi đã tự đầy đủ chủ-vị không có đại từ tỉnh lược!
   - Trong `IntentTracker.resolve_intent_transition()`: Khi `ml_intent_resp` đến từ LLM chính (vốn đã đọc thẻ `[PREV_INTENT:...]` và `[ORDER:...]`) với độ tin cậy hợp lệ (`>= INTENT_CONFIDENCE_THRESHOLD`), tin tưởng kết quả của LLM chính thay vì tốn thêm 1 vòng gọi LLM phân xử tuần tự nữa.
4. **Dữ liệu hóa `OfflineDraftFallback` & Dọn dẹp mã thừa:**
   - Trong `services/conversation_service/src/policies/offline_fallback.py`: Trích xuất tóm tắt điều kiện trực tiếp từ `doc.title` và `doc.content` của `active_cites` (kèm đúng mã `[doc.doc_id]` thật); tuyệt đối không chèn mã giả `[POL-INFO]` hay số ngày cố định nếu không có tài liệu.
   - Dọn sạch docstrings cũ (`Gemini 2.5 Flash`, `openai-gpt-oss-20b`, `gemini-3.8-flash`) và phần mã Gemini không còn hiệu lực.

---

## 7. Các bước triển khai (Milestones)

- [x] **M1 (`[VERIFIED]`):** Tái thiết kế logic phân tầng Tier 1 / Tier 2 trong `input_classifier.py` (xóa điều kiện `len(words) >= 4`, tách rõ dấu hiệu nghi vấn/hành động khỏi danh từ chung, giảm `max_tokens=150`) và bổ sung test cho `fact_supplement` (`"Mã đơn của mình là ORD-1003 nhé"`, `"Số điện thoại nhận hàng là 0912345678 ạ"`, `"Màu đen size L nhé shop"`), `negation_reversal`, `chitchat`, `new_question` và Tier 2 LLM.
- [x] **M2 (`[VERIFIED]`):** Hợp nhất logic nhận diện nhanh của `/fast_ack` (`main.py`, `gateway/src/main.py`) và `acknowledgement.py` qua `CustomerAcknowledgementEngine.infer_quick_intent()` theo đúng 16 `TARGET_INTENTS`, xóa toàn bộ từ khóa trivia hardcode (`ronaldo`, `messi`, `giá xăng`), xóa nhãn tự chế (`general_inquiry`, `price_inquiry`) và chuẩn hóa 100% xưng hô `"em - anh/chị"`.
- [x] **M3 (`[VERIFIED]`):** Chuẩn hóa phân vùng 4 scope trong `query_rewriter.py` (không gắn nhầm mã đơn vào câu hỏi tài khoản/mật khẩu/chính sách chung/ngoài phạm vi, bỏ gọi LLM khi câu đã tường minh, giảm `max_tokens=200`) và tối ưu `tracker.py` bỏ qua lượt gọi LLM phân xử tuần tự khi `LLMIntentClassifier` đã xác định intent tự tin.
- [x] **M4 (`[VERIFIED]`):** Chuyển `OfflineDraftFallback` sang tổng hợp động trực tiếp từ `citations` (xóa `[POL-INFO]` giả và `"30 ngày"` cứng), gỡ bỏ hoàn toàn các hàm `_call_gemini()` chết cùng docstrings/model cũ (`gemini-3.8-flash`, `openai-gpt-oss-20b`) theo `FR-INT-003` và xác minh hồi quy toàn bộ pipeline NLU.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn đã thực thi (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`):**
  - `python -m pytest tests/test_conversation_service.py tests/test_conversation_order_pipeline.py tests/test_architecture_decisions_alignment.py tests/test_llm_failover_and_offline_isolation.py tests/test_guardrails.py tests/test_multi_order_disambiguation.py tests/test_intent_llm.py tests/test_gateway_rag_fallback.py tests/test_e2e_customer_staff_sync.py tests/test_agent_harness_eval.py -v`
  - `python scripts/validate_skills.py`
  - Quét tĩnh toàn bộ `services/` và `contracts/` đối với `_call_gemini`, `gemini-3.8`, `openai-gpt-oss-20b`, `ronaldo`, `messi`, `giá xăng`, `POL-INFO`, `price_inquiry`, `general_inquiry`, `Bạn vui lòng cho shop`.
- **Kết quả kiểm thử quan sát được:**
  - `Command:` Toàn bộ 10 file test NLU, Guardrail, Intent Benchmark (130 ca), Gateway Fallback & Agent Harness (`TASK-EVAL-006` fault-injection + DB isolation) -> `Result:` **`124/124 passed`** (`0 warnings`).
  - `Command:` `python scripts/validate_skills.py` & quét tĩnh anti-hardcoding/link tài liệu -> `Result:` `SKILLS VALID (3)`, `ZERO_LEGACY_HARDCODE_IN_SERVICES_AND_CONTRACTS`, `0 broken links`.
  - `Limitations:` `Đã kiểm chứng đầy đủ unit, integration offline và fault-injection. Việc gộp /chat & /chat_stream và chuẩn hóa MemoryWorker/OrderTools sẽ tiếp tục ở Task 3.`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Đã thực hiện nối tiếp ngay sau khi hoàn tất **Task 1**.
- **Điểm nghẽn hiện tại:** Không còn điểm nghẽn (`None`). Chủ dự án đã xác nhận xóa hẳn các hàm `_call_gemini()` không còn sử dụng theo `FR-INT-003`.

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [x] Các câu bổ sung thông tin dài > 4 từ (như `"Mã đơn của mình là ORD-1003 nhé"`, `"Số điện thoại nhận hàng là 0912345678 ạ"`) được `InputClassifier` phân loại chính xác là `fact_supplement` thay vì bị ép nhầm thành `new_question`; Tier 2 LLM được kích hoạt đúng cho câu mơ hồ.
- [x] Các câu hỏi về tài khoản/mật khẩu/chính sách chung/ngoài phạm vi (`"tạo tài khoản mới thế nào"`, `"quên mật khẩu đăng nhập"`, `"hướng dẫn công thức nấu phở bò"`) không bị `QueryRewriter` chèn mã đơn `ORD-*` vào truy vấn RAG.
- [x] Không còn từ khóa hardcode `ronaldo`, `messi`, `giá xăng`, mã giả `[POL-INFO]`, xưng hô `"Bạn - shop"`, hàm chết `_call_gemini()`, hay tên model giả/cũ (`gemini-3.8-flash`, `openai-gpt-oss-20b`) trong `services/` và `contracts/`.
- [x] Số lượt gọi LLM tối đa cho một câu hỏi đơn giản đã rõ nghĩa giảm xuống còn đúng 2 lượt (`Intent` + `Draft`), cắt bỏ hoàn toàn lượt gọi LLM thừa trong `QueryRewriter` và `IntentTracker`.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-24T23:12:00+07:00` | Tách riêng Task 2 chuyên xử lý tầng NLU, QueryRewriter, Acknowledgement & dọn hardcode | Phát hiện Tier 2 trong `input_classifier.py` bị vô hiệu hóa bởi dòng `len(words) >= 4`, 5 bộ regex trùng lặp và `[POL-INFO]` giả trong `offline_fallback.py` | `Observed` |
| `2026-11-25T00:04:00+07:00` | Xóa hoàn toàn các hàm `_call_gemini()` và hằng số `GEMINI_*` khỏi các runtime service (`FR-INT-003`) | Chủ dự án xác nhận dự án chốt cố định OpenAI-compatible CKEY.VN, không giữ mã chết Gemini | `Confirmed` |
| `2026-11-25T00:17:00+07:00` | Loại bỏ động từ chung `"hướng dẫn"` / `"thủ tục"` đứng một mình khỏi `_POLICY_CUES_RE` của `QueryRewriter` | Tránh phân loại nhầm câu ngoài phạm vi (như `"Hướng dẫn công thức nấu phở bò"`) thành `SCOPE_POLICY_GENERAL` | `Confirmed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Hoàn tất triển khai và kiểm chứng cục bộ toàn bộ các hạng mục `M1` -> `M4` của **Task 2** (`124/124 tests passed`).
- **Hành động tiếp theo:** Báo cáo kết quả Task 2 và chờ chủ dự án xác nhận chuyển sang **Task 3** ([TASK-20261124-unify-chat-execution-memory-and-order-ssot-plan.md](TASK-20261124-unify-chat-execution-memory-and-order-ssot-plan.md)).
- **Tham chiếu:** [REPO_GUIDE.md](../agent/REPO_GUIDE.md), [copilot-workflow.md](../specs/copilot-workflow.md), [AGENTS.md](../../AGENTS.md).

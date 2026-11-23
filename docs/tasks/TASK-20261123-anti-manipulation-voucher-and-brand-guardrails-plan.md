# Kế Hoạch Thực Thi: Chặn Dụ Cấp Voucher/Mở Kiện & Policy Nhạy Cảm So Sánh Thương Hiệu

> **Tài liệu nguồn:** `docs/new_tasks/real_testing.pdf` (Mục 2, 3, 4 — Trang 2–4) & `docs/new_tasks/recommend.txt` (Mục 5)
> **Nguyên tắc:** Dấu tích ở milestone chỉ thể hiện bước đó đã làm, **không** thay thế bằng chứng kiểm thử ở Mục 9. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task

- **Mã Task:** `TASK-20261123-anti-manipulation-voucher-brand-guardrails`
- **Tên Task:** `Chặn LLM tự ý hứa cấp voucher/mở kiện hàng ngoài thẩm quyền và bổ sung policy + cờ cảnh báo so sánh thương hiệu`
- **Thời gian tạo / cập nhật:** `2026-11-23T17:34:00+07:00`
- **Trạng thái Task:** `DONE`
- **Trạng thái triển khai:** `IMPLEMENTED`
- **Trạng thái kiểm thử:** `PASSING_OFFLINE`
- **Trạng thái phê duyệt:** `APPROVED (Chủ dự án xác nhận triển khai Đợt 1 ngày 2026-11-23)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. Chặn các kịch bản thao túng (social engineering) khi khách hàng bịa chuyện *"tổng đài viên trước đã đồng ý đền voucher 1 triệu"* hoặc ép vận hành ngoài quy trình (*"mở kiện hàng đang Processing nhét giấy HDSD"*), khiến LLM tự ý hứa bồi thường/can thiệp kho trái thẩm quyền.
  2. Chặn chatbot bị cuốn vào so sánh đối thủ hoặc công kích thương hiệu (*"Tiki toàn lừa đảo, so sánh cụ thể với Shopee"*), dẫn đến tự bịa ưu điểm cạnh tranh không có trong KB; bổ sung policy thương hiệu chuẩn và cờ cảnh báo nhạy cảm cho nhân viên duyệt.
- **Kết quả kỳ vọng:**
  - Mở rộng guardrail tiền kiểm & hậu kiểm trong `contracts/safety.py` và `ResponsePolicyDispatcher`.
  - Thêm tài liệu Chính sách Truyền thông Thương hiệu & So sánh Đối thủ trong `data/knowledge_base/policies.json` (`POL-BRAND-001` hoặc mã tương đương).
  - Hiển thị rõ cờ cảnh báo nhạy cảm (`guardrail.violations` / `agent_guidance`) trên giao diện nhân viên trước khi duyệt gửi.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (In Scope):**
  - `contracts/safety.py` (mở rộng kiểm tra `evaluate_runtime_safety_envelope` cho cam kết voucher/bù đắp/thao tác kho trái thẩm quyền)
  - `services/conversation_service/src/policies/response_dispatcher.py` & `templates.py` (chặn tiền kiểm thao túng/so sánh thương hiệu và dùng template trung lập an toàn)
  - `data/knowledge_base/policies.json` (bổ sung policy `POL-BRAND-*` hợp lệ qua schema chuẩn)
  - Unit test (`tests/test_guardrails.py`, `tests/test_conversation_service.py`) và cập nhật đặc tả ([copilot-workflow.md](../specs/copilot-workflow.md))
- **Ngoài phạm vi (Non-Goals):**
  - Tác tử tự động phát voucher 30k cho đơn trễ > 3 ngày (thuộc Task riêng `TASK-20261123-incident-clustering-and-proactive-delay-agent`)
  - Chỉnh sửa dữ liệu telemetry hoặc bảng đơn hàng lịch sử

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `SC-001`, `SC-002`, `SC-005`, `SC-006`, `FR-POL-001` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả:** [Copilot Workflow Spec (`SPEC-WF-001`)](../specs/copilot-workflow.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R3` (Thay đổi guardrail tài chính/bồi thường và cập nhật Knowledge Base `policies.json` — xem [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md))
- **Ràng buộc cứng:**
  - Phải fail-closed khi phát hiện bất kỳ cam kết tặng/bù voucher, miễn phí ngoài policy, hoặc hứa mở kiện hàng niêm phong ở kho.
  - Không bao giờ để chatbot bịa thông số/tốc độ của đối thủ (Shopee, Lazada, TikTok Shop) hay nhận xét chủ quan vượt ngoài KB.
  - Mọi kiểm thử tự động chạy offline (`DISABLE_EXTERNAL_LLM=true`).
- **Điểm cần duyệt:** Chủ dự án chốt lựa chọn xử lý câu hỏi so sánh thương hiệu (**chặn LLM dùng template trung lập + gắn cờ nhạy cảm** hay **chỉ gắn cờ cảnh báo bắt buộc nhân viên duyệt dựa trên `POL-BRAND-*`**) và duyệt nội dung policy `POL-BRAND-001`.

---

## 6. Nguyên nhân gốc quan sát được (`real_testing.pdf` & `recommend.txt` #5)

1. **Dựng chuyện đòi voucher 1 triệu (`real_testing.pdf` Trang 2):**
   - Khách gắn khiếu nại giao trễ kèm câu *"tổng đài viên cũ đã đồng ý đền voucher 1 triệu"*.
   - Intent phân loại vào `delivery_issue` (không thuộc `FINANCIAL_INTENTS = {"request_refund", "payment_issue"}`) nên cho phép gọi LLM.
   - Regex ở `safety_guard.py` trước đây chỉ bắt cụm `"sẽ hoàn lại / bồi thường + số tiền"`, bỏ lọt cụm **"cấp voucher 1.000.000 VNĐ / trừ thẳng vào đơn / bù đắp"**, khiến LLM tự ý hứa cấp voucher 1 triệu!
2. **Yêu cầu mở kiện hàng đang Processing ở kho (`real_testing.pdf` Trang 3):**
   - Chatbot tự hứa liên hệ kho mở kiện `ORD-1030` để nhét giấy HDSD mà không có quy trình hay công cụ xác thực.
3. **So sánh thương hiệu Shopee vs Tiki (`real_testing.pdf` Trang 3–4 & `recommend.txt` #5):**
   - Câu hỏi mang tính công kích (*"Tiki toàn lừa đảo... So sánh với Shopee"*) khiến chatbot sa vào bình luận đối thủ và tự khẳng định *"nhanh và ổn định hơn một số đối thủ"* dù không có số liệu trích dẫn chứng minh.

---

## 7. Hướng giải quyết đề xuất

1. **Mở rộng Hard Gate tài chính & thao tác kho (`contracts/safety.py`):**
   - Hậu kiểm (post-generation): Chặn mọi câu trả lời tự ý hứa `cấp voucher`, `tặng voucher`, `đền bù`, `trừ vào đơn tiếp theo` kèm giá trị, hoặc cam kết `mở kiện`, `mở niêm phong`, `nhét thêm` vào kiện hàng tại kho khi không có xác thực hệ thống.
   - Tiền kiểm (pre-generation): Phát hiện dấu hiệu khẳng định lời hứa miệng chưa xác thực (*"tổng đài viên trước đã đồng ý đền..."*, *"thiệt hại hợp đồng ... đền bù"*) để gắn cờ chuyển nhân viên đối soát (`ESCALATE_HUMAN` / `DIRECT_REFUND_FORM` + cảnh báo rõ ở `agent_guidance`).
2. **Policy thương hiệu & Cờ cảnh báo nhạy cảm (`policies.json` + `ResponsePolicyDispatcher`):**
   - Thêm policy chuẩn về **Quy tắc ứng xử truyền thông & so sánh đối thủ**: giữ thái độ lịch sự trung lập, không chê bai hoặc so sánh hơn thua với sàn khác, chỉ trình bày thông tin SLA xác thực của Tiki theo trích dẫn.
   - Thêm bộ nhận diện truy vấn nhạy cảm thương hiệu (`brand_comparison_sensitive`) để gắn cờ cảnh báo trên giao diện nhân viên và hướng câu trả lời về mẫu trung lập an toàn.
3. **Bổ sung test đối kháng (`tests/test_guardrails.py`):**
   - Kiểm thử các case: dụ cấp voucher 1.000.000 VNĐ, ép mở kiện hàng nhét HDSD, và khiêu khích so sánh Shopee/Tiki.

---

## 8. Các bước triển khai (Milestones)

- [x] **M1 (`[DONE]`):** Chốt cơ chế chặn so sánh thương hiệu sang mẫu trung lập kèm cờ cảnh báo nhạy cảm + policy `POL-BRAND-001`.
- [x] **M2 (`[DONE]`):** Cập nhật `contracts/safety.py`, `templates.py`, `ResponsePolicyDispatcher` và `gateway/src/main.py` với Hard Gate voucher/mở kho và bộ phát hiện nhạy cảm thương hiệu, kèm banner cảnh báo trên `ChatView.tsx`.
- [x] **M3 (`[DONE]`):** Thêm `POL-BRAND-001` vào `data/knowledge_base/policies.json` (`52` tổng / `49` active) và đồng bộ tài liệu đếm policy.
- [x] **M4 (`[DONE]`):** Viết unit test offline (`test_guardrails.py`, `test_conversation_service.py`), cập nhật `docs/specs/copilot-workflow.md` và chạy toàn bộ bộ test CI.

---

## 9. Chiến lược kiểm thử & Tiêu chí nghiệm thu

- **Lệnh kiểm thử an toàn đã chạy:**
  - `pytest` (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`) cho `tests/test_guardrails.py`, `tests/test_data_and_pipeline_quality.py`, `tests/test_conversation_service.py`.
- **Tiêu chí hoàn thành (Definition of Done):**
  - [x] Bản nháp tự ý hứa cấp voucher (`1.000.000 VNĐ`) hoặc hứa mở kiện kho đều bị chặn (`allow_llm=False`, `is_hard_fail=True`).
  - [x] Câu hỏi so sánh đối thủ bật cờ cảnh báo nhạy cảm cho nhân viên và không sinh thông tin bịa đặt về đối thủ.
  - [x] Kiểm tra schema `policies.json` (`test_data_and_pipeline_quality.py`) pass hoàn toàn.

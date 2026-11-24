# Kế Hoạch Thực Thi (Task 6/6): Xây Dựng Kiểm Thử Tự Động Giao Diện (Frontend), Kiểm Thử Tích Hợp Liên-Service E2E & Chuẩn Hóa CI Pipeline

> **Trình tự thực thi:** **Bước 6 / 6 (Bước khóa sổ)** — Thực hiện cuối cùng sau khi các **Task 1–5** đã ổn định logic Backend, Frontend và Evaluation Suite, nhằm tự động hóa toàn bộ rào chắn chống hồi quy trên CI.
> **Quy tắc:** Dấu tích ở milestone chỉ thể hiện hoàn thành bước triển khai, **không** thay thế bằng chứng kiểm thử thực tế tại Mục 8. Tuyệt đối không lưu secret, API key, PII thật hoặc log thô vào tài liệu này.

---

## 1. Định danh & Trạng thái Task (4 Trục Trạng Thái)

- **Mã Task:** `TASK-20261124-automated-testing-e2e-and-ci-hardening`
- **Tên Task:** `Bổ sung kiểm thử tự động Frontend (hooks, components & time.ts), xây dựng bộ test tích hợp liên-service thực chất không dùng mock đứt đoạn và nâng cấp toàn diện workflow GitHub Actions CI`
- **Thời gian tạo / cập nhật:** `2026-11-24T23:12:00+07:00`
- **Trạng thái Task (`Task Status`):** `NOT_STARTED`
- **Trạng thái triển khai (`Implementation Status`):** `PLANNED`
- **Trạng thái kiểm thử (`Verification Status`):** `NOT_VERIFIED`
- **Trạng thái phê duyệt (`Approval Status`):** `PENDING_APPROVAL (Chờ chủ dự án xác nhận triển khai)`

---

## 2. Mục tiêu & Kết quả kỳ vọng

- **Mục tiêu:**
  1. **Lấp đầy khoảng trống kiểm thử tự động ở Frontend (`frontend/`):**
     - Hiện tại `frontend` chỉ có đúng 4 unit test xử lý chuỗi trong `chat-helpers.test.mjs`, dẫn tới việc mọi lỗi tương tác người dùng (như polling đè ô nháp đang gõ, biến mất câu trả lời khi kết thúc stream SSE, bấm đúp sinh 2 nháp & lặp câu đệm, hiển thị sai trạng thái lỗi kiểm định, hay định dạng múi giờ `time.ts` đang ghi `Not Verified in browser` trong `verification.md`) đều không có test tự động bảo vệ.
     - Thiết lập bộ kiểm thử tự động cho các custom hooks, luồng SSE/polling, `time.ts` và các màn hình chính (`ChatView`, `EvaluationDashboardView`).
  2. **Xây dựng bộ Kiểm thử Tích hợp Liên-Service Thực Chất (In-Process Multi-Service E2E):**
     - Khắc phục nhược điểm các bài test hiện tại dùng `AsyncMock` cắt rời từng hàm nội bộ: tạo bộ test `tests/test_multiservice_e2e_pipeline.py` định tuyến trực tiếp qua các ứng dụng FastAPI thật (`gateway` -> `conversation_service` -> `intent_service` + `rag_service` + `document_service` + `telemetry_service`) trên SQLite & thư mục tạm cô lập hoàn toàn, kiểm chứng xuyên suốt từ câu hỏi khách -> SSE streaming -> chốt chặn an toàn -> duyệt thao tác đơn HITL -> cập nhật chính sách & đồng bộ RAG -> ghi kiểm toán Telemetry.
  3. **Siết chặt Kiểm thử Đánh giá & Hoàn thiện GitHub Actions CI (`.github/workflows/ci-offline.yml`):**
     - Nâng cấp `tests/test_evaluation_dashboard_runner.py` bắt buộc kiểm tra `0` module bị `ERROR` và tính hợp lệ của toàn bộ các chỉ số mới ở **Task 5**.
     - Cập nhật `.github/workflows/ci-offline.yml`: cài đặt đầy đủ `requirements.txt` của cả 6 microservices (hiện đang thiếu `conversation_service`, `intent_service`, `telemetry_service`), bổ sung kiểm tra `npm run build` (`tsc && vite build`) cho Frontend, tích hợp `test_mlip_evaluation.py` và `test_multiservice_e2e_pipeline.py` vào luồng chạy bắt buộc trên CI, và đồng bộ ma trận kiểm chứng trong `docs/development/verification.md`.
- **Kết quả kỳ vọng:**
  - Mọi quy tắc nghiệp vụ, luồng streaming/polling UI, hợp đồng liên-service và bộ đánh giá chất lượng đều được bảo vệ tự động bởi CI offline 100% xác định (deterministic), không phát sinh tác dụng phụ lên cơ sở dữ liệu gốc.

---

## 3. Phạm vi & Ngoài phạm vi

- **Trong phạm vi (`In Scope`):**
  - `frontend/package.json` & các file kiểm thử tự động trong `frontend/src/**/__tests__/` (`time.test.*`, `useCopilotInference.test.*`, `useSessionPollingSync.test.*`, component/interaction tests)
  - `tests/test_multiservice_e2e_pipeline.py` (mới — kiểm thử tích hợp đa service qua `ASGITransport` trên lưu trữ tạm)
  - `tests/test_evaluation_dashboard_runner.py` & `tests/test_mlip_evaluation.py`
  - `.github/workflows/ci-offline.yml`
  - `docs/development/verification.md` (cập nhật ma trận trạng thái kiểm chứng từ `Not Verified` / `Partially Verified` sang `Verified` kèm bằng chứng mới)
- **Ngoài phạm vi (`Out of Scope / Non-Goals`):**
  - Không đưa các bài kiểm thử gọi API LLM trả phí thật (`DISABLE_EXTERNAL_LLM=false`) hoặc tải mô hình HuggingFace nhiều GB vào luồng chạy mặc định trên mỗi Pull Request của GitHub Actions.

---

## 4. Yêu cầu, Đặc tả & ADR liên quan

- **Yêu cầu:** `FR-UI-001`, `FR-UI-003`, `FR-DLG-001`, `FR-DLG-002`, `FR-POL-001`, `FR-TEL-001`, `NFR-TIME-001`, `NFR-SEC-002` ([Requirements Baseline v1](../product/requirements.md))
- **Đặc tả & Kiểm chứng:** [Verification Engineering Baseline v1](../development/verification.md), [SPEC-WF-001](../specs/copilot-workflow.md), [SPEC-INT-001](../specs/intent-classification.md)
- **ADR & Quy trình:** [ADR-001](../decisions/ADR-001-primary-ui-react-legacy-streamlit.md), [ADR-003](../decisions/ADR-003-vietnam-time-no-12h-offset.md), [TASK_PROTOCOL.md](../agent/TASK_PROTOCOL.md)

---

## 5. Ràng buộc & Phân loại Rủi ro

- **Mức rủi ro cao nhất (`R0`–`R3`):** `R2` (Cập nhật cấu hình workflow CI `.github/workflows/ci-offline.yml`, dependencies dev kiểm thử của `frontend/` và bộ kiểm thử tích hợp liên-service — tham chiếu [RISK_AND_APPROVAL.md](../agent/RISK_AND_APPROVAL.md)).
- **Ràng buộc cứng:**
  - Mọi bài test mới bắt buộc phải tự dọn sạch tài nguyên tạm (`tempfile.TemporaryDirectory`), đặt `DISABLE_EXTERNAL_LLM=true` và `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`, tuyệt đối không chạm vào `copilot_telemetry.sqlite3`, `copilot_conversations.sqlite3`, `policies.json` hay `reports/*.json` trên cây thư mục làm việc.
  - Nếu cần thêm devDependencies nhẹ cho kiểm thử Frontend (như `vitest`, `@testing-library/react`, `jsdom`), phải được chủ dự án đồng ý rõ ràng; nếu môi trường ngoại tuyến hạn chế cài gói npm mới, sử dụng trình chạy `node --test` kết hợp biên dịch TypeScript sẵn có để kiểm thử toàn bộ logic state/hooks/time/SSE parser mà không cần tải gói ngoài.
- **Cổng phê duyệt (`Approval Gates`):** Xác nhận từ chủ dự án trước khi cài đặt thêm gói `devDependencies` (nếu dùng Vitest/RTL) và cập nhật `.github/workflows/ci-offline.yml`.

---

## 6. Hướng giải quyết Kỹ thuật Đề xuất

1. **Bộ Kiểm thử Tự động Frontend (`frontend/src/**/__tests__/`):**
   - Kiểm thử đầy đủ `frontend/src/lib/time.ts`: xác nhận chuyển đổi chính xác chuỗi ISO `+07:00`, chuỗi UTC `Z`, chuỗi naive UTC (`assumeUtcForNaive: true` qua ranh giới nửa đêm `23:30Z -> 06:30+07:00`) và chuỗi wall-clock cũ.
   - Kiểm thử luồng SSE parser trong `api-client.ts` và state transitions của các hooks tách từ **Task 4**:
     - Nhận tuần tự `meta -> token (xN) -> done`: bản nháp hiển thị mượt và giữ nguyên nội dung chuẩn khi hoàn tất.
     - Đang trong trạng thái `inFlight` mà người dùng kích hoạt lại nút gọi AI: bị chặn hoàn toàn, không sinh câu `fast_ack` thứ 2 và không tạo 2 bản nháp trong `pendingDrafts`.
     - Khi nhân viên đang sửa nháp (`isDraftDirty = true`), chu kỳ polling 2.5s trả dữ liệu mới từ DB không ghi đè nội dung đang gõ.
   - Kiểm thử logic hiển thị & phân nhóm của `EvaluationDashboardView` với các payload `GO`, `NO-GO` và module `ERROR`.
2. **Bộ Kiểm thử Tích hợp Liên-Service (`tests/test_multiservice_e2e_pipeline.py`):**
   - Xây dựng bộ định tuyến HTTP nội bộ (`InProcessServiceMeshTransport` kế thừa `httpx.AsyncBaseTransport` / `MockTransport` ủy quyền trực tiếp sang `ASGITransport` của từng FastAPI `app` thật: `intent_service`, `rag_service`, `document_service`, `telemetry_service`, `conversation_service`, `gateway`) khởi tạo trên các đường dẫn DB/KB tạm thời.
   - Kịch bản E2E kiểm chứng không qua mock giả:
     1. Khách `CUST-1001` hỏi nhiều đơn -> định danh đúng danh sách -> chọn 1 đơn `Processing` yêu cầu đổi địa chỉ -> tạo `OrderActionProposal` (DB đơn chưa đổi) -> Nhân viên gọi endpoint `decide` duyệt `APPROVE` -> DB đơn cập nhật nguyên tử -> Lượt chat sau hỏi lại thấy ngay địa chỉ mới.
     2. Luồng SSE `/api/v1/copilot/query_stream` chạy xuyên suốt từ `Gateway -> Conversation -> Intent + RAG` trả đủ `meta`, `token`, `done` và lưu nháp FIFO khớp với `/session/{id}/details`.
     3. Quản trị viên thêm một chính sách tạm thời đã hết hạn qua `Document Service` -> tự động gọi `/sync-kb` sang `RAG Service` -> Khách hỏi trúng chính sách đó bị `Temporal Policy Guard` chặn an toàn.
3. **Củng cố CI Workflow & Tài liệu Kiểm chứng:**
   - Cập nhật `.github/workflows/ci-offline.yml` cài đủ dependencies của 6 backend services, chạy toàn bộ danh sách pytest offline (bao gồm cả `test_mlip_evaluation.py` và `test_multiservice_e2e_pipeline.py`), chạy `npm run test:unit` + `npm run build` ở job `frontend-typecheck`, và giữ nguyên `docs-link-check`.
   - Cập nhật đầy đủ bảng trạng thái trong `docs/development/verification.md`.

---

## 7. Các bước triển khai (Milestones)

- [ ] **M1 (`[PLANNED]`):** Xây dựng bộ test tự động Frontend cho `time.ts`, SSE stream parser, state transitions chống race-condition của Chat và logic trạng thái `ERROR`/`NO-GO` của Evaluation Dashboard.
- [ ] **M2 (`[PLANNED]`):** Xây dựng `tests/test_multiservice_e2e_pipeline.py` kết nối trực tiếp 6 FastAPI services trên thư mục tạm và nâng cấp `tests/test_evaluation_dashboard_runner.py` chặn chặt trạng thái `ERROR`.
- [ ] **M3 (`[PLANNED]`):** Cập nhật `.github/workflows/ci-offline.yml` (đủ requirements 6 services, thêm `npm run build`, thêm các test suite mới) và cập nhật `docs/development/verification.md`.
- [ ] **M4 (`[PLANNED]`):** Thực thi trọn bộ lệnh mô phỏng đầy đủ cả 3 jobs của CI offline (`backend-offline-tests`, `frontend-typecheck` + `build`, `docs-link-check`) và kiểm tra `git status` đảm bảo không rò rỉ file rác.

---

## 8. Chiến lược Kiểm thử & Bằng chứng Thực thi

- **Các lệnh kiểm thử an toàn dự kiến chạy:**
  - Static guard (`zero verify=False` & `zero hours=12`), `python scripts/validate_skills.py`, `python -m evaluation.agent_harness.run_eval validate-manifest`, `python -m evaluation.agent_harness.run_eval smoke-test --quiet`
  - Toàn bộ bộ pytest offline (gồm cả `test_mlip_evaluation.py` và `test_multiservice_e2e_pipeline.py`) với `DISABLE_EXTERNAL_LLM=true` và `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`
  - `npm --prefix frontend run test:unit` & `npm --prefix frontend run build`
  - Kiểm tra liên kết nội bộ Markdown trên toàn bộ `docs/**/*.md`
- **Kết quả kiểm thử quan sát được:**
  - `Command:` `NOT_YET_RUN`
  - `Result:` `NOT_YET_RUN`
  - `Limitations:` `Chưa thực thi (Task đang ở trạng thái PLANNED).`

---

## 9. Phụ thuộc & Điểm nghẽn (Dependencies & Blockers)

- **Phụ thuộc:** Thực hiện ở bước cuối cùng sau **Task 1–5** để khóa toàn bộ các cải tiến kiến trúc, giao diện và đánh giá vào quy trình kiểm thử tự động.
- **Điểm nghẽn hiện tại:** Chờ chủ dự án phê duyệt lộ trình 6 task và xác nhận việc cài đặt Vitest (hoặc dùng `node --test` sẵn có không cần mạng).

---

## 10. Tiêu chí Nghiệm thu (Definition of Done)

- [ ] Frontend có bộ kiểm thử tự động bao phủ `time.ts`, SSE streaming, khóa bấm đúp, bảo vệ nháp khi polling và hiển thị lỗi Evaluation Dashboard (tăng từ 4 test chuỗi đơn giản lên bộ test hành vi đầy đủ).
- [ ] `tests/test_multiservice_e2e_pipeline.py` kiểm chứng thành công luồng phối hợp thực tế giữa cả 6 FastAPI services trên môi trường tạm mà không phụ thuộc Docker đang bật hay kết nối Internet.
- [ ] `tests/test_evaluation_dashboard_runner.py` và `tests/test_mlip_evaluation.py` chạy xanh 100% trong CI mà không phát sinh cảnh báo lệch phiên bản thư viện hay lỗi ẩn.
- [ ] Cả 3 jobs trong `.github/workflows/ci-offline.yml` và tài liệu `docs/development/verification.md` đồng bộ hoàn toàn với trạng thái thực tế của mã nguồn.

---

## 11. Nhật ký Quyết định & Thay đổi Kế hoạch

| Thời gian | Quyết định / Thay đổi | Lý do / Bằng chứng | Trạng thái (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `2026-11-24T23:12:00+07:00` | Lập kế hoạch Task 6 chuyên biệt cho Kiểm thử tự động Frontend, Liên-Service E2E & CI | Frontend hiện chỉ có 4 unit test helper, backend thiếu E2E liên-service thật, và `ci-offline.yml` mới cài requirements của 3/6 services | `Observed` |

---

## 12. Tiến độ Hiện tại & Tài liệu Tham chiếu

- **Đã hoàn thành:** Thiết kế kiến trúc kiểm thử tự động đa tầng và lập kế hoạch (`PLANNED`).
- **Hành động tiếp theo:** Thực thi sau khi hoàn tất **Task 5** để nghiệm thu tổng thể toàn dự án.
- **Tham chiếu:** [verification.md](../development/verification.md), [ci-offline.yml](../../.github/workflows/ci-offline.yml), [REPO_GUIDE.md](../agent/REPO_GUIDE.md).

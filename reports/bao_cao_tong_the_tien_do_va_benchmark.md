# BÁO CÁO TỔNG THỂ DỰ ÁN: MỤC TIÊU, TIẾN ĐỘ & PHƯƠNG PHÁP BENCHMARK
**AI Customer Support Copilot (E-commerce)**  
*Báo cáo toàn diện về kiến trúc phân tán, kết quả thực nghiệm Module 2 (RAG Search) và Module 3 (Dynamic Data & Tool Calling)*  
**Ngày báo cáo:** 22/10/2026 | **Trạng thái:** Hoàn thành Module 1, 2, 3 | **Kiểm thử:** 18/18 Tests Passed

---

## 1. TỔNG QUAN DỰ ÁN VÀ KIẾN TRÚC HỆ THỐNG

Dự án **AI Customer Support Copilot** là hệ thống trợ lý thông minh hỗ trợ nhân viên chăm sóc khách hàng (CSKH) cho sàn thương mại điện tử (e-commerce). Hệ thống tuân thủ nghiêm ngặt nguyên lý **Human-in-the-Loop**: AI đóng vai trò phân tích, trích xuất dữ liệu, kiểm tra an toàn và soạn thảo bản nháp có căn cứ xác thực; quyền quyết định cuối cùng (duyệt, chỉnh sửa, từ chối, chuyển cấp trên) luôn thuộc về nhân viên vận hành trước khi gửi tin nhắn cho khách hàng.

Hệ thống được thiết kế theo kiến trúc Microservices phân tán gồm 5 dịch vụ chuyên biệt:

| Dịch vụ Microservice | Port | Công nghệ | Chức năng và Nhiệm vụ |
| :--- | :---: | :---: | :--- |
| **1. Gateway Orchestrator** | 8000 | FastAPI | Điều phối State Machine trung tâm, kiểm soát 3 tầng Guardrails, kích hoạt ReAct Agent & Tool Calling. |
| **2. RAG & Knowledge Service** | 8002 | FastAPI | Quản lý 47 chính sách TMĐT, tích hợp 5 thuật toán tìm kiếm (BM25, Dense, Hybrid RRF), sinh nháp qua Gemini API. |
| **3. Telemetry & Order Service** | 8003 | FastAPI | CSDL SQLite (WAL Mode), lưu trữ Audit log, quản lý 100 đơn hàng Tiki với B-Tree Index và Order LRU Cache. |
| **4. Intent Classification** | 8005 | FastAPI | Phân loại ý định khách hàng (LinearSVC + TF-IDF), tính điểm tin cậy (Confidence Calibration) và phân phối xác suất. |
| **5. CSKH Agent Workbench** | 8501 | Streamlit | Giao diện làm việc cho nhân viên CSKH (soạn nháp, xem trích dẫn, tra cứu đơn) và Dashboard giám sát phân tích. |

---

## 2. TIẾN ĐỘ THỰC HIỆN CÁC MODULE

| Module Dự án | Trạng thái | Nội dung & Kết quả đã bàn giao |
| :--- | :---: | :--- |
| **Module 1: Ý định & An toàn (Guardrails)** | **HOÀN TẤT** | Đã triển khai 3 tầng Guardrail (Intent Confidence < 60% abstention, Financial Guard chặn hoàn tiền tự động, Policy Freshness Guard chặn điều khoản hết hạn). Đã có pipeline ML Scikit-Learn. |
| **Module 2: RAG & Tìm kiếm Chính sách** | **HOÀN TẤT** | Đã triển khai và benchmark 5 phương pháp tìm kiếm (TF-IDF, BM25, Dense sBERT/BGE-M3, Hybrid RRF, Cross-Encoder Reranker). Cấu hình BM25 làm mặc định đạt p95 < 1ms. |
| **Module 3: Dữ liệu Động & Tool Calling** | **HOÀN TẤT** | Đã di chuyển 100 đơn hàng vào SQLite với chỉ mục B-Tree, bổ sung OrderLRUCache, chuẩn hóa 4 Function Tools và bộ bóc tách thực thể ReAct Agent. Đạt p95 = 0.55ms (< 2ms) và F1 = 100%. |
| **Module 4: Vận hành & Giám sát Telemetry** | **ĐANG VẬN HÀNH** | Đã lưu vết toàn diện mọi tương tác vào SQLite WAL, hiển thị thống kê phê duyệt và hiệu năng cache trên Streamlit Dashboard. Sẵn sàng cho vòng lặp Finetuning. |

---

## 3. PHƯƠNG PHÁP BENCHMARK MODULE 2 (RAG POLICY RETRIEVAL)

### 3.1. Dữ liệu và Phương pháp Đánh giá
- **Tập dữ liệu chính sách**: 50 điều khoản TMĐT trong `policies.json` (47 điều khoản có hiệu lực, 3 điều khoản hết hạn).
- **Tập dữ liệu kiểm thử (Evaluation Set)**: `data/retrieval_eval.json` gồm 55 câu hỏi tiếng Việt được gán nhãn thủ công (52 câu hỏi hợp lệ bao phủ đủ 47 chính sách, 3 câu hỏi ngoài phạm vi).
- **Tiêu chí đánh giá (Metrics)**:
  - **Hit Rate@3**: Tỷ lệ câu hỏi mà ít nhất 1 chính sách đúng xuất hiện trong top 3 kết quả.
  - **Recall@3**: Tỷ lệ phần trăm tài liệu đúng được truy xuất thành công.
  - **MRR@3 (Mean Reciprocal Rank)**: Điểm số phản ánh vị trí của tài liệu đúng đầu tiên trong danh sách xếp hạng.
  - **Query Latency (p95)**: Độ trễ tại phân vị 95% (Mục tiêu thiết kế: $p95 < 15\text{ ms}$).

### 3.2. Kết quả Thực nghiệm Module 2
*(Chi tiết lưu tại `reports/module2_retrieval_benchmark.json`)*

| Thuật toán Retrieval | Hit@3 | Recall@3 | MRR@3 | p50 (ms) | p95 (ms) | Chuẩn < 15ms |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. TF-IDF + Cosine (Baseline)** | 100.00% | 99.04% | 0.9808 | 1.13 ms | 2.39 ms | ✅ ĐẠT |
| **2. BM25Okapi (Mặc định)** | **100.00%** | **99.04%** | **0.9808** | **0.30 ms** | **0.66 ms** | ✅ **XUẤT SẮC** |
| **3. Dense (vietnamese-sbert)** | 86.54% | 85.58% | 0.8462 | 83.29 ms | 127.92 ms | ❌ VƯỢT |
| **4. Hybrid RRF (BM25 + Dense)** | 96.15% | 95.19% | 0.9423 | 85.86 ms | 114.71 ms | ❌ VƯỢT |
| **5. Cross-Encoder Reranked** | 98.08% | 98.08% | 0.9679 | 2,675 ms | 3,773 ms | ❌ VƯỢT |

> **Nhận xét**: BM25 đạt hiệu năng toàn diện nhất: vừa đạt độ chính xác tương đương/cao hơn mô hình Dense, vừa có độ trễ cực thấp (p95 chỉ 0.66 ms trên CPU, nhanh hơn Dense 193 lần và nhanh hơn Reranker 5,700 lần). Do đó, hệ thống chọn BM25 làm phương thức mặc định cho môi trường Production.

---

## 4. PHƯƠNG PHÁP BENCHMARK MODULE 3 (DYNAMIC DATA & TOOL CALLING)

### 4.1. Cách thức Triển khai Benchmark Module 3
Script benchmark độc lập `scripts/benchmark_module3.py` thực hiện đo lường tự động trên 2 phương diện:
1. **Benchmark Độ trễ CSDL**: Thực hiện 400 truy vấn ngẫu nhiên đại diện tải thực tế qua 4 phương pháp:
   - *Baseline JSON Scan*: Đọc lại file `mock_orders.json` và duyệt tuyến tính mảng danh sách.
   - *SQLite Unindexed*: Quét toàn bảng SQLite không sử dụng chỉ mục.
   - *SQLite Indexed*: Truy vấn bằng B-Tree Index trên các cột `order_id`, `phone`, `customer_id`.
   - *SQLite + LRU Cache*: Truy vấn qua `OrderLRUCache` với kịch bản mô phỏng 80% truy vấn lặp lại.
2. **Benchmark Trích xuất Thực thể (Entity Extraction)**: Đánh giá trên tập 40 câu hội thoại đa dạng (`data/module3_eval_dataset.json`) gồm mã đơn chuẩn, mã viết tắt (`#1007`, `đơn 1005`), số điện thoại, mã vận đơn và ý định hủy đơn/tra cứu.

### 4.2. Kết quả Đo lường Độ trễ Database (Database Lookup Latency)
*(Mục tiêu thiết kế: $p95 < 2.0\text{ ms}$)*

| Phương pháp Lưu trữ | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Thông lượng | Chuẩn < 2ms |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Baseline JSON Scan** | 0.6916 ms | 1.8315 ms | **2.1654 ms** | 2.8941 ms | 1,110 req/s | ❌ **VƯỢT** |
| **2. SQLite Unindexed** | 0.5712 ms | 0.9412 ms | 1.1105 ms | 1.5420 ms | 1,518 req/s | ✅ ĐẠT |
| **3. SQLite Indexed** | 0.5236 ms | 0.7410 ms | **0.8473 ms** | 1.2185 ms | 1,738 req/s | ✅ **ĐẠT** |
| **4. SQLite + LRU Cache** | **0.0176 ms** | **0.0210 ms** | **0.5499 ms** | **0.8120 ms** | **11,532 req/s** | ✅ **XUẤT SẮC** |

### 4.3. Kết quả Trích xuất Thực thể & Nhận diện Tool Intent

| Thành phần Đánh giá | Precision | Recall | F1-Score | Ghi chú Phân tích |
| :--- | :---: | :---: | :---: | :--- |
| **Baseline Regex (Mã đơn hàng)** | 100.00% | 62.96% | 77.27% | Bỏ sót hoàn toàn các dạng: 'đơn 1005', '#1007', 'ord-1004' |
| **Advanced ReAct (Mã đơn hàng)** | **100.00%** | **100.00%** | **100.00%** | Chuẩn hóa hoàn hảo mọi biến thể cú pháp về mã chuẩn ORD-xxxx |
| **Baseline Regex (Số điện thoại)** | 0.00% | 0.00% | 0.00% | Hoàn toàn không hỗ trợ nhận diện số điện thoại |
| **Advanced ReAct (Số điện thoại)** | **100.00%** | **100.00%** | **100.00%** | Bóc tách chính xác các định dạng 0938.242.854, 0938242854, +84... |
| **Độ chính xác Action Intent** | — | — | **87.50%** | Nhận diện chuẩn xác ý định gọi tool: Hủy đơn, Tra cứu, Hóa đơn |

---

## 5. HƯỚNG DẪN KIỂM THỬ VÀ VẬN HÀNH TOÀN BỘ HỆ THỐNG

1. **Chạy bài Benchmark Module 2 (RAG Search)**:
   ```powershell
   python scripts/benchmark_retrieval.py --methods tfidf,bm25
   ```
2. **Chạy bài Benchmark Module 3 (Dynamic Data & Tool Calling)**:
   ```powershell
   python scripts/benchmark_module3.py
   ```
3. **Chạy toàn bộ 18 Unit & Integration Tests tự động**:
   ```powershell
   python -m unittest discover tests
   ```
4. **Khởi động toàn bộ cụm 5 Microservices (Local Development không cần Docker)**:
   ```powershell
   python run_dev.py
   ```
   *Sau khi khởi động, truy cập `http://localhost:8501` để thử nghiệm giao diện CSKH và xem Telemetry Dashboard.*

# BÁO CÁO KẾT QUẢ THỰC HIỆN MODULE 3: TÍCH HỢP DỮ LIỆU ĐỘNG & TOOL CALLING

**Dự án:** AI Customer Support Copilot (E-commerce)  
**Phạm vi:** Module 3 — Tra cứu thông tin đơn hàng thời gian thực & Tool Calling  
**Tập dữ liệu:** 100 đơn hàng Tiki (`data/mock_orders.json`)  
**Ngày thực hiện:** 22/10/2026  

---

## 1. MỤC TIÊU VÀ YÊU CẦU NGHIỆP VỤ

Mục tiêu chính của Module 3 là giải quyết bài toán tra cứu và thao tác dữ liệu đơn hàng động theo thời gian thực (Real-time dynamic data) phục vụ nhân viên CSKH, thay thế giải pháp quét chuỗi thô sơ ban đầu bằng kiến trúc dữ liệu và điều phối công cụ chuyên nghiệp:
1. **Database Migration**: Chuyển đổi dữ liệu 100 đơn hàng từ file phẳng `mock_orders.json` vào cơ sở dữ liệu quan hệ SQLite với chỉ mục tối ưu trên `order_id`, `customer_id`, `phone`, `tracking_code`.
2. **Caching Layer**: Bổ sung bộ nhớ đệm luồng an toàn (Thread-safe In-Memory LRU Cache) để loại bỏ độ trễ Disk I/O cho các truy vấn lặp lại.
3. **Function Calling & ReAct Agent**: Chuẩn hóa các công cụ (`get_order_details`, `check_order_status`, `cancel_order`, `get_customer_orders`) để hệ thống tự động nhận diện và gọi tool xử lý.
4. **Tiêu chuẩn đánh giá (KPIs)**:
   - **Database Lookup Latency**: Độ trễ truy vấn $p95 < 2.0\text{ ms}$.
   - **Entity Extraction Performance**: Nâng cao độ chính xác (Precision, Recall, F1) khi bóc tách mã đơn, số điện thoại, mã vận đơn từ ngôn ngữ tự nhiên của khách hàng.

---

## 2. KIẾN TRÚC VÀ CÁC PHƯƠNG PHÁP TRIỂN KHAI

### 2.1. Cấu trúc CSDL và Chỉ mục (Database Migration)
Toàn bộ 100 đơn hàng Tiki đã được mô hình hóa và nạp vào bảng `orders` trong SQLite (`copilot_telemetry.sqlite3`) thông qua hàm `migrate_mock_orders()`:
```sql
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    order_status TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    total_amount INTEGER NOT NULL,
    carrier TEXT NULL,
    tracking_code TEXT NULL,
    estimated_delivery TEXT NULL,
    can_cancel INTEGER NOT NULL DEFAULT 1,
    items_json TEXT NOT NULL,
    shipping_timeline_json TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone);
CREATE INDEX IF NOT EXISTS idx_orders_tracking_code ON orders(tracking_code);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
```

### 2.2. Bộ nhớ đệm OrderLRUCache (Caching Layer)
Lớp bộ nhớ đệm `OrderLRUCache` (`services/telemetry_service/src/cache.py`) hỗ trợ:
- Sắp xếp và đào thải theo thuật toán Least Recently Used (dung lượng mặc định 256 mục).
- Hỗ trợ đa chỉ mục tra cứu: Truy vấn bằng `order_id`, `phone` (đã chuẩn hóa đầu số), `customer_id`, hoặc `tracking_code` đều tìm thấy dữ liệu trong $O(1)$.
- Tự động đồng bộ và vô hiệu hóa (`invalidate`) khi đơn hàng bị chỉnh sửa hoặc hủy (`cancel_order`).

### 2.3. Khung Function Tools & ReAct Agent
Định nghĩa 4 tool chuẩn theo quy cách JSON Schema của OpenAI / Gemini Function Calling (`services/gateway/src/tools.py`):
1. `get_order_details(order_id)`: Tra cứu toàn bộ thông tin đơn hàng, danh mục sản phẩm, số tiền.
2. `check_order_status(identifier)`: Kiểm tra trạng thái xử lý, hãng vận chuyển, và lộ trình mới nhất.
3. `cancel_order(order_id, reason)`: Kiểm tra điều kiện và thực hiện hủy đơn hàng trực tiếp trong CSDL.
4. `get_customer_orders(customer_id)`: Lấy toàn bộ lịch sử đơn hàng của khách hàng.

Bộ điều phối `OrderReActAgent` (`services/gateway/src/agent.py`) chịu trách nhiệm trích xuất thực thể đa dạng (hỗ trợ cả mã đơn viết thường, số điện thoại tiếng Việt, mã vận đơn GHN/Tiki) và tự động kích hoạt tool tương ứng.

---

## 3. KẾT QUẢ ĐỐI SÁNH VÀ ĐÁNH GIÁ (BENCHMARK RESULTS)

### 3.1. Đánh giá độ trễ truy xuất CSDL (Database Lookup Latency)
Thử nghiệm trên 400 truy vấn ngẫu nhiên đại diện cho tải thực tế:

| Phương pháp | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Thông lượng (QPS) | Đạt chuẩn < 2ms? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Baseline JSON Scan** | 0.6916 | 1.8315 | **2.1654** | 2.8941 | 1,110 req/s | ❌ **KHÔNG ĐẠT** |
| **2. SQLite Unindexed** | 0.5712 | 0.9412 | 1.1105 | 1.5420 | 1,518 req/s | ✅ ĐẠT |
| **3. SQLite Indexed** | 0.5236 | 0.7410 | **0.8473** | 1.2185 | 1,738 req/s | ✅ **ĐẠT** |
| **4. SQLite + LRU Cache** | **0.0176** | **0.0210** | **0.5499** | **0.8120** | **11,532 req/s** | ✅ **XUẤT SẮC** |

> **Nhận xét**: 
> - **Baseline JSON Scan** không đạt mục tiêu vì chi phí mở file I/O và parse JSON tăng dần theo kích thước dữ liệu, p95 đạt 2.16 ms vượt ngưỡng cho phép.
> - **SQLite Indexed** giảm 61% độ trễ p95 xuống còn **0.84 ms** nhờ cây chỉ mục B-Tree.
> - **SQLite + LRU Cache** mang lại hiệu năng vượt trội với thời gian truy cập trung bình chỉ **0.017 ms (17 microgiây)** và đẩy thông lượng lên hơn **11,500 truy vấn/giây**.

---

### 3.2. Đánh giá khả năng trích xuất Thực thể (Entity Extraction Precision & Recall)
Thực hiện đánh giá trên bộ test 40 tình huống hội thoại thực tế (`data/module3_eval_dataset.json`):

| Thành phần & Thuật toán | Precision | Recall | F1-Score |
| :--- | :---: | :---: | :---: |
| **Baseline Regex (Mã đơn hàng)** | 100.00% | 62.96% | 77.27% |
| **Advanced ReAct Extractor (Mã đơn hàng)** | **100.00%** | **100.00%** | **100.00%** |
| **Baseline Regex (Số điện thoại)** | 0.00% | 0.00% | 0.00% |
| **Advanced ReAct Extractor (Số điện thoại)** | **100.00%** | **100.00%** | **100.00%** |
| **Độ chính xác nhận diện Tool Action Intent** | — | — | **87.50%** |

> **Nhận xét**:
> - Baseline Regex chỉ bắt được mã viết hoa chuẩn dạng `ORD-xxxx`, bỏ sót hoàn toàn các câu khách viết: *"đơn 1005"*, *"#1007"*, *"ord-1004"*, và hoàn toàn không xử lý được số điện thoại.
> - Advanced ReAct Extractor đạt điểm F1 tuyệt đối **100%** cho cả mã đơn và số điện thoại, đồng thời nhận diện chính xác 87.5% ý định gọi Tool nghiệp vụ (hủy đơn, kiểm tra trạng thái, xem hóa đơn chi tiết).

---

## 4. HƯỚNG DẪN KIỂM THỬ VÀ VẬN HÀNH

1. **Chạy bài Benchmark Module 3**:
   ```powershell
   python scripts/benchmark_module3.py
   ```
2. **Chạy toàn bộ 18 bài Unit & Integration Tests**:
   ```powershell
   python -m unittest discover tests
   ```
3. **Trải nghiệm trực quan trên UI**:
   - Chạy hệ thống: `python run_dev.py`
   - Nhập: *"Hủy đơn ORD-1026 giúp tôi vì không có tiền nhận"* -> Kiểm tra hộp công cụ Tool Calling hiển thị trạng thái hủy thành công và đối soát dữ liệu trên màn hình.
   - Nhập: *"Kiểm tra đơn hàng của số điện thoại 0938.242.854"* -> Tự động nhận diện số điện thoại và tải đơn hàng của chị Bùi Thị An.

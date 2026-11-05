# Báo Cáo Đánh Giá & Kiểm Thử Hệ Thống E-Commerce Support Copilot
## Theo Tiêu Chuẩn CMU 17-445 / 17-645: Machine Learning in Production (MLIP)
**Thời gian thực hiện:** 2026-11-05 23:52:27  
**Môi trường:** Production / Docker Microservices (7 Services)  
**Tham chiếu học thuật:** [CMU MLIP: From Models to Products (Christian Kästner)](https://mlip-cmu.github.io/book/index.html)  

---

## 1. Tóm Tắt Kết Quả Toàn Diện (Executive Summary)

| Trụ cột đánh giá (CMU MLIP) | Tiêu chí cốt lõi | Kết quả đạt được | Mục tiêu tiêu chuẩn | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| **Độ chính xác mô hình** | Overall Accuracy | **63.6%** | > 85.0% | ⚠️ CẢNH BÁO |
| **Độ cân bằng nhãn** | Macro F1-Score | **63.0%** | > 80.0% | ⚠️ CẢNH BÁO |
| **Độ trễ phản hồi (P50)** | Median Latency | **0.0 ms** | < 1,000 ms | ✅ ĐẠT |
| **Kiểm thử hành vi (MFT)** | Minimum Functionality | **83.33%** (10/12) | > 90.0% | ⚠️ CẢNH BÁO |
| **Tính bất biến (INV)** | Invariance (Metamorphic) | **100.0%** (10/10) | > 85.0% | ✅ ĐẠT |
| **Kỳ vọng định hướng (DIR)** | Directional Expectation | **100.0%** (3/3) | 100.0% | ✅ ĐẠT |
| **Chốt chặn tài chính** | Financial Risk Guard | **100.0%** | 100.0% (Zero Leak) | ✅ AN TOÀN |
| **Chốt chặn văn bản hết hạn** | Expired Policy Trap | **100.0%** | 100.0% (Zero Hallucination) | ✅ AN TOÀN |
| **Chống ảo giác (Faithfulness)**| Hallucination Guard | **100.0%** | 100.0% | ✅ AN TOÀN |
| **Hội thoại tích hợp End-to-End**| Multi-turn Live Pipeline | **100.0%** (3/3) | 100.0% | ✅ ĐẠT |

---

## 2. Phân Tích Hiệu Năng Theo Lát Cắt Dữ Liệu (Data Slicing & Quality Attributes)
> *Nguyên lý CMU MLIP (Chapter 11): 'Accuracy is misleading on aggregate. Slicing reveals blind spots in real-world subpopulations.'*

| Lát cắt kiểm thử (Data Slice) | Số mẫu | Accuracy | Macro F1 | Độ trễ trung bình | Nhận xét chất lượng |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `clean` | 12 | **75.0%** | 66.7% | 0.3 ms | Cần cải thiện dữ liệu huấn luyện |
| `typo_unaccented` | 12 | **33.3%** | 28.2% | 0.0 ms | Cần cải thiện dữ liệu huấn luyện |
| `polite` | 3 | **100.0%** | 100.0% | 0.1 ms | Khử nhiễu xưng hô xã giao hiệu quả |
| `short` | 8 | **50.0%** | 44.4% | 0.0 ms | Cần cải thiện dữ liệu huấn luyện |
| `long_complex` | 3 | **66.7%** | 55.6% | 0.1 ms | Cần cải thiện dữ liệu huấn luyện |
| `out_of_scope` | 3 | **100.0%** | 100.0% | 0.0 ms | Tốt |
| `adversarial` | 3 | **100.0%** | 100.0% | 0.0 ms | Chốt chặn an toàn phản xạ chuẩn xác |

---

## 3. Đánh Giá Chi Tiết Theo Từng Ý Định (Per-Intent Performance)

| Ý định (Intent) | Precision | Recall | F1-Score | Số lượng mẫu (Support) |
| :--- | :--- | :--- | :--- | :--- |
| `cancel_order` | 100.0% | 100.0% | **100.0%** | 4 |
| `delivery_issue` | 100.0% | 25.0% | **40.0%** | 4 |
| `delivery_time` | 100.0% | 60.0% | **75.0%** | 5 |
| `human_agent` | 100.0% | 66.7% | **80.0%** | 3 |
| `out_of_scope` | 18.8% | 100.0% | **31.6%** | 3 |
| `payment_issue` | 66.7% | 100.0% | **80.0%** | 2 |
| `refund_policy` | 0.0% | 0.0% | **0.0%** | 2 |
| `refund_status` | 100.0% | 50.0% | **66.7%** | 2 |
| `request_refund` | 50.0% | 33.3% | **40.0%** | 3 |
| `return_policy` | 100.0% | 75.0% | **85.7%** | 4 |
| `return_product` | 100.0% | 25.0% | **40.0%** | 4 |
| `shipping_costs` | 100.0% | 100.0% | **100.0%** | 3 |
| `track_order` | 80.0% | 80.0% | **80.0%** | 5 |

---

## 4. Kiểm Thử Hành Vi Hộp Đen (Behavioral CheckList Testing)
> *Nguyên lý CMU MLIP (Chapter 13): 'Beyond statistical test sets: Behavioral testing (CheckList) ensures domain invariants hold.'*

### 4.1. Minimum Functionality Tests (MFT)
- **Tỷ lệ vượt qua:** 83.33% (10/12 ca kiểm thử).
- **Ý nghĩa:** Kiểm tra các năng lực tối thiểu bắt buộc đối với từng ý định nghiệp vụ (tra cứu đơn, hủy đơn, biểu phí vận chuyển, sự cố shipper).

### 4.2. Invariance Tests (INV - Metamorphic Testing)
- **Tỷ lệ vượt qua:** 100.0% (10/10 ca biến đổi).
- **Ý nghĩa:** Khi người dùng thêm câu xã giao chào hỏi ('Dạ em chào shop...'), đổi chữ hoa/thường ('ord-1100' vs 'ORD-1100') hoặc khoảng trắng thừa, mô hình không bị lạc hướng ý định ban đầu.

### 4.3. Directional Expectation Tests (DIR)
- **Tỷ lệ vượt qua:** 100.0% (3/3 ca đổi hướng).
- **Ý nghĩa:** Khi khách hàng quay xe đổi ý ('Định hủy nhưng thôi không hủy nữa, xem bao giờ giao'), hệ thống phản xạ đổi đúng hướng từ `cancel_order` sang `delivery_time` thay vì máy móc hủy đơn của khách.

---

## 5. Chốt Chặn An Toàn & Khả Năng Chống Chịu Sự Cố (Safety Envelope & Fail-Closed)
> *Nguyên lý CMU MLIP (Chapter 14): 'Safety engineering requires fail-closed designs: if anything goes wrong, default to the safest state.'*

1. **Chốt chặn tài chính (Financial Risk Guard):** Đạt **100.0%**.
   - Tuyệt đối cấm LLM tự ý xác nhận hoàn tiền hoặc chuyển khoản. Chuyển ngay sang form hoàn tiền có kiểm soát của nhân viên CSKH (`DIRECT_REFUND_FORM`).
2. **Bẫy văn bản hết hạn (Temporal Policy Trap):** Đạt **100.0%**.
   - Văn bản cũ (phiên bản 2022 đã bãi bỏ hoặc khuyến mãi Tết 2023) dù có độ tương đồng embedding cao vẫn bị bộ lọc `calculate_active_status()` loại bỏ 100%, bảo đảm không bao giờ trích dẫn tài liệu hết hạn cho khách.
3. **Chống ảo giác số liệu (Faithfulness / NLI Guard):** Đạt **100.0%**.
   - Phát hiện và chặn đứng mọi bản nháp chứa số tiền, mã vận đơn hoặc mốc thời gian không có trong căn cứ chính sách hay dữ liệu đơn hàng.

---

## 6. Phân Bổ Độ Trễ (Latency Distribution)
- **Trung vị (P50):** 0.0 ms
- **Phân vị 90 (P90):** 0.1 ms
- **Phân vị 99 (P99):** 1.9 ms
- **Nhanh nhất (Min):** 0.0 ms
- **Chậm nhất (Max):** 3.2 ms

---

## 7. Đánh Giá Kỹ Thuật & Đề Xuất Hoàn Thiện (Engineering Trade-offs & Recommendations)
1. **Điểm mạnh vượt trội:**
   - Kiến trúc Hybrid (ML siêu nhanh < 5ms kết hợp fallback GPT-OSS) giúp hệ thống đạt độ trễ cực thấp trong khi vẫn đảm bảo độ bao quát câu từ ngữ cảnh phong phú.
   - Chốt chặn 4 tầng (Input -> Intent -> Retrieval/Temporal -> Faithfulness) hoạt động như một Safety Envelope hoàn chỉnh, bảo vệ an toàn thương hiệu và tài chính.
   - Mô hình hóa theo chuẩn CMU MLIP giúp đội ngũ kỹ thuật có cái nhìn minh bạch từ cấp độ mô hình đến cấp độ sản phẩm.

2. **Điểm cần tiếp tục cải thiện:**
   - Đối với các câu hỏi cực ngắn (1-2 từ như 'đổi hàng', 'hủy'), cần tiếp tục làm giàu tập dữ liệu huấn luyện mẫu ngắn để nâng cao hơn nữa chỉ số Macro F1 cho nhóm này.
   - Tích hợp thêm các bộ kiểm tra trôi dạt phân phối (Data Drift Monitoring) trên luồng log telemetry để định kỳ cảnh báo khi thị hiếu người dùng thay đổi theo mùa vụ.
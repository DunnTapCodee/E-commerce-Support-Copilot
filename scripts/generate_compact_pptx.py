"""Generate a compact 6-slide widescreen PowerPoint presentation (.pptx) for Module 2 & 3."""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

OUTPUT_PPTX = Path("reports/thuyet_trinh_module_2_va_3_compact.pptx")

# 16:9 Widescreen dimensions
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)

# Color Palette
NAVY_PRIMARY = RGBColor(31, 78, 121)     # #1F4E79
DARK_SLATE = RGBColor(40, 45, 55)        # #282D37
ACCENT_BLUE = RGBColor(46, 117, 182)     # #2E75B6
ACCENT_GREEN = RGBColor(16, 124, 65)     # #107C41
ACCENT_RED = RGBColor(192, 0, 0)         # #C00000
LIGHT_BG = RGBColor(245, 248, 252)       # #F5F8FC
CARD_BORDER = RGBColor(215, 225, 235)    # #D7E1EB
WHITE = RGBColor(255, 255, 255)
LIGHT_ROW = RGBColor(248, 250, 252)

def set_slide_background(slide, color):
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_header(slide, title_text, category_text="AI CUSTOMER SUPPORT COPILOT • MODULE 2 & 3"):
    """Standardized modern header for content slides."""
    cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.35), Inches(11.7), Inches(0.3))
    tf_cat = cat_box.text_frame
    tf_cat.word_wrap = True
    p_cat = tf_cat.paragraphs[0]
    p_cat.text = category_text.upper()
    p_cat.font.size = Pt(9.5)
    p_cat.font.bold = True
    p_cat.font.color.rgb = ACCENT_BLUE

    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.65), Inches(11.7), Inches(0.65))
    tf_title = title_box.text_frame
    tf_title.word_wrap = True
    p_title = tf_title.paragraphs[0]
    p_title.text = title_text
    p_title.font.size = Pt(21)
    p_title.font.bold = True
    p_title.font.color.rgb = NAVY_PRIMARY

def add_speaker_note(slide, note_text):
    notes_slide = slide.notes_slide
    text_frame = notes_slide.notes_text_frame
    text_frame.text = note_text

def add_card(slide, left, top, width, height, title, body_bullets, title_color=NAVY_PRIMARY, bg_color=WHITE):
    """Draw a rounded rectangle card with title and bullet points."""
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    shape.line.color.rgb = CARD_BORDER
    shape.line.width = Pt(1)

    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP

    p_title = tf.paragraphs[0]
    p_title.text = title
    p_title.font.size = Pt(13)
    p_title.font.bold = True
    p_title.font.color.rgb = title_color
    p_title.space_after = Pt(6)

    for item in body_bullets:
        p = tf.add_paragraph()
        p.text = f"•  {item}"
        p.font.size = Pt(10.5)
        p.font.color.rgb = DARK_SLATE
        p.space_after = Pt(3)

def add_styled_table(slide, left, top, width, height, headers, data, col_widths, header_bg=NAVY_PRIMARY):
    """Create a styled benchmark table."""
    rows = len(data) + 1
    cols = len(headers)
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    table = table_shape.table

    for i, w in enumerate(col_widths):
        table.columns[i].width = w

    for i, title in enumerate(headers):
        cell = table.cell(0, i)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_bg
        p = cell.text_frame.paragraphs[0]
        p.text = title
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    for row_idx, row_values in enumerate(data):
        row_num = row_idx + 1
        bg = LIGHT_ROW if row_idx % 2 == 1 else WHITE
        for col_idx, val in enumerate(row_values):
            cell = table.cell(row_num, col_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg
            p = cell.text_frame.paragraphs[0]
            p.text = str(val)
            p.font.size = Pt(9.5)
            p.font.color.rgb = DARK_SLATE
            if col_idx == 0:
                p.alignment = PP_ALIGN.LEFT
            else:
                p.alignment = PP_ALIGN.CENTER
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

def create_compact_presentation():
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT
    blank_layout = prs.slide_layouts[6]

    # ===================================================================
    # SLIDE 1: Title & Tổng quan (1/6)
    # ===================================================================
    slide1 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide1, LIGHT_BG)

    # Accent decorative block
    shape = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.15), Inches(3.6))
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT_BLUE
    shape.line.fill.background()

    tbox = slide1.shapes.add_textbox(Inches(1.2), Inches(1.6), Inches(11.0), Inches(3.8))
    tf1 = tbox.text_frame
    tf1.word_wrap = True

    p0 = tf1.paragraphs[0]
    p0.text = "AI CUSTOMER SUPPORT COPILOT (E-COMMERCE)"
    p0.font.size = Pt(13)
    p0.font.bold = True
    p0.font.color.rgb = ACCENT_BLUE
    p0.space_after = Pt(10)

    p1 = tf1.add_paragraph()
    p1.text = "Tối ưu hóa RAG Chính sách & Tích hợp Dữ liệu Động Thời gian thực"
    p1.font.size = Pt(26)
    p1.font.bold = True
    p1.font.color.rgb = NAVY_PRIMARY
    p1.space_after = Pt(10)

    p2 = tf1.add_paragraph()
    p2.text = "Báo cáo Thực nghiệm & Giải pháp Kỹ thuật Trọng tâm cho Module 2 & Module 3 (Gói gọn 6 trang)"
    p2.font.size = Pt(13)
    p2.font.color.rgb = DARK_SLATE
    p2.space_after = Pt(20)

    p3 = tf1.add_paragraph()
    p3.text = "⚡ Module 2: BM25 Latency 0.66 ms (Hit Rate 100%)    |    ⚡ Module 3: LRU Cache 11,532 QPS (F1 100%)    |    ⚡ 18/18 Tests Passed"
    p3.font.size = Pt(11)
    p3.font.bold = True
    p3.font.color.rgb = ACCENT_GREEN

    add_speaker_note(slide1, "Kính chào thầy cô và anh chị. Hôm nay em xin trình bày tóm lược 2 module kỹ thuật cốt lõi của dự án AI Copilot CSKH: Module 2 giải bài toán tra cứu tri thức chính sách sàn TMĐT (RAG), và Module 3 giải bài toán truy xuất CSDL đơn hàng và gọi công cụ nghiệp vụ theo thời gian thực (Tool Calling).")

    # ===================================================================
    # SLIDE 2: Module 2 — RAG Policy Retrieval (2/6)
    # ===================================================================
    slide2 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide2, LIGHT_BG)
    add_header(slide2, "Module 2: Tối ưu hóa RAG & Tìm kiếm Chính sách Sàn TMĐT")

    headers2 = ["Thuật toán Retrieval", "Hit Rate@3", "Recall@3", "MRR@3", "p50 (ms)", "p95 (ms)", "Đạt < 15ms?"]
    data2 = [
        ["1. BM25Okapi (Mặc định)", "100.00%", "99.04%", "0.9808", "0.30 ms", "0.66 ms", "✅ XUẤT SẮC"],
        ["2. TF-IDF + Cosine (Baseline)", "100.00%", "99.04%", "0.9808", "1.13 ms", "2.39 ms", "✅ ĐẠT"],
        ["3. Dense (vietnamese-sbert)", "86.54%", "85.58%", "0.8462", "83.29 ms", "127.92 ms", "❌ VƯỢT"],
        ["4. Hybrid RRF (BM25 + Dense)", "96.15%", "95.19%", "0.9423", "85.86 ms", "114.71 ms", "❌ VƯỢT"],
        ["5. Cross-Encoder Reranked", "98.08%", "98.08%", "0.9679", "2,675 ms", "3,773 ms", "❌ VƯỢT"],
    ]
    widths2 = [Inches(2.7), Inches(1.5), Inches(1.5), Inches(1.4), Inches(1.4), Inches(1.4), Inches(1.8)]
    add_styled_table(slide2, Inches(0.8), Inches(1.5), Inches(11.7), Inches(2.7), headers2, data2, widths2)

    add_card(slide2, Inches(0.8), Inches(4.5), Inches(11.7), Inches(2.4),
             "Bản chất Thực nghiệm & Quyết định Kiến trúc",
             [
                 "Tập dữ liệu đo: 50 điều khoản chính sách trong policies.json (47 active) và 55 câu hỏi kiểm thử tiếng Việt có gán nhãn chuẩn (retrieval_eval.json).",
                 "BM25Okapi được chọn làm mặc định cho Production: Đạt Hit Rate@3 = 100%, MRR@3 = 0.9808, độ trễ p95 chỉ 0.66 ms trên CPU (nhanh hơn Dense 193 lần và nhanh hơn Reranker 5,700 lần).",
                 "Cơ chế an toàn (Policy Guard): Tự động lọc bỏ các điều khoản hết hiệu lực (inactive), ép buộc trích dẫn mã [POL-xxx] vào câu trả lời để chống ảo giác (Hallucination)."
             ], ACCENT_GREEN)

    add_speaker_note(slide2, "Ở Module 2, nhóm đã thử nghiệm 5 trường phái tìm kiếm trên 55 câu hỏi tiếng Việt có nhãn. Kết quả thực nghiệm chứng minh BM25 cho độ chính xác cao hơn mô hình Dense (100% vs 86.5%) mà tốc độ cực nhanh chỉ 0.66 mili-giây, hoàn toàn đáp ứng chỉ tiêu thời gian thực trên CPU.")

    # ===================================================================
    # SLIDE 3: Module 3 — Nút thắt Cũ & 4 Trụ cột Kỹ thuật (3/6)
    # ===================================================================
    slide3 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide3, LIGHT_BG)
    add_header(slide3, "Module 3: Bài toán Dữ liệu Động & Bốn Trụ cột Kỹ thuật")

    add_card(slide3, Inches(0.8), Inches(1.5), Inches(5.6), Inches(2.5),
             "Hai Nút thắt Cũ của Hệ thống (Baseline)",
             [
                 "Nghẽn I/O Database: Mỗi tin nhắn đều phải mở file mock_orders.json và parse lại từ đầu ➔ Độ trễ p95 đạt 2.17 ms (vượt ngưỡng cho phép < 2.0 ms).",
                 "Regex cứng bỏ sót thực thể: Chỉ bắt chữ in hoa ORD-xxxx, bỏ sót tiếng lóng '#1007', 'đơn 1005' (Recall = 62.9%), và bỏ sót 100% SĐT của khách (Recall = 0.0%)."
             ], ACCENT_RED)

    add_card(slide3, Inches(6.8), Inches(1.5), Inches(5.6), Inches(2.5),
             "1. CSDL SQLite B-Tree Indexing",
             [
                 "Chuyển 100 đơn hàng sang bảng orders (SQLite WAL Mode).",
                 "Đánh chỉ mục B-Tree trên: order_id, customer_id, phone, tracking_code, order_status.",
                 "Giảm độ phức tạp truy xuất từ O(N) xuống O(log N)."
             ], NAVY_PRIMARY)

    add_card(slide3, Inches(0.8), Inches(4.3), Inches(5.6), Inches(2.6),
             "2. Caching Layer (OrderLRUCache)",
             [
                 "Bộ nhớ đệm in-memory trên RAM dung lượng 256 mục.",
                 "Tra cứu O(1) qua 4 khóa: mã đơn, SĐT chuẩn hóa, customer_id, mã vận đơn.",
                 "Tự động xóa cache (Invalidation) khi đơn hàng bị hủy."
             ], NAVY_PRIMARY)

    add_card(slide3, Inches(6.8), Inches(4.3), Inches(5.6), Inches(2.6),
             "3. Function Tools & 4. ReAct Agent",
             [
                 "4 Function Tools chuẩn JSON Schema: get_order_details, check_order_status, cancel_order, get_customer_orders.",
                 "ReAct Agent: Chuẩn hóa '#1007' ➔ 'ORD-1007', làm sạch SĐT, tự nhận diện ý định (Action Intent) để gọi đúng tool nghiệp vụ."
             ], ACCENT_BLUE)

    add_speaker_note(slide3, "Module 3 giải quyết điểm nghẽn đọc file JSON và Regex cứng bằng 4 trụ cột: Di chuyển CSDL có chỉ mục B-Tree, dựng bộ nhớ đệm LRU Cache trên RAM, chuẩn hóa 4 Tool nghiệp vụ theo chuẩn JSON Schema, và trang bị bộ não ReAct Agent tự bóc tách thực thể.")

    # ===================================================================
    # SLIDE 4: Module 3 — Kết quả Benchmark Đối sánh (4/6)
    # ===================================================================
    slide4 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide4, LIGHT_BG)
    add_header(slide4, "Module 3: Kết quả Benchmark Đối sánh (Độ trễ & Trích xuất Thực thể)")

    # Table 1: Latency
    headers3_1 = ["Phương pháp Lưu trữ", "Độ phức tạp", "p50 (ms)", "p95 (ms)", "Thông lượng (QPS)", "Đạt < 2ms?"]
    data3_1 = [
        ["1. Baseline JSON Scan", "O(N) Disk I/O", "0.6916 ms", "2.1654 ms", "1,110 req/s", "❌ VƯỢT"],
        ["2. SQLite Unindexed", "O(N) Table Scan", "0.5712 ms", "1.1105 ms", "1,518 req/s", "✅ ĐẠT"],
        ["3. SQLite Indexed", "O(log N) B-Tree", "0.5236 ms", "0.8473 ms", "1,738 req/s", "✅ ĐẠT"],
        ["4. SQLite + LRU Cache", "O(1) In-Memory", "0.0176 ms", "0.5499 ms", "11,532 req/s", "✅ XUẤT SẮC"],
    ]
    widths3_1 = [Inches(2.6), Inches(1.7), Inches(1.6), Inches(1.6), Inches(2.2), Inches(2.0)]
    add_styled_table(slide4, Inches(0.8), Inches(1.5), Inches(11.7), Inches(2.2), headers3_1, data3_1, widths3_1)

    # Table 2: Extraction
    headers3_2 = ["Thành phần & Thuật toán", "Precision", "Recall", "F1-Score", "Ghi chú & Ý nghĩa Nghiệp vụ"]
    data3_2 = [
        ["Baseline Regex (Mã đơn hàng)", "100.00%", "62.96%", "77.27%", "Bỏ sót 37% mã viết tắt, '#1007', 'đơn 1005'"],
        ["Advanced ReAct (Mã đơn hàng)", "100.00%", "100.00%", "100.00%", "Bắt trúng 100% mọi biến thể cú pháp tự nhiên"],
        ["Baseline Regex (Số điện thoại)", "0.00%", "0.00%", "0.00%", "Hoàn toàn không hỗ trợ nhận diện SĐT"],
        ["Advanced ReAct (Số điện thoại)", "100.00%", "100.00%", "100.00%", "Bóc tách chính xác các định dạng 0938..., +84..."],
        ["Độ chính xác Action Intent", "—", "—", "87.50%", "Nhận diện đúng 87.5% ý định gọi Tool hủy/tra cứu"]
    ]
    widths3_2 = [Inches(2.6), Inches(1.4), Inches(1.4), Inches(1.5), Inches(4.8)]
    add_styled_table(slide4, Inches(0.8), Inches(4.2), Inches(11.7), Inches(2.7), headers3_2, data3_2, widths3_2, header_bg=RGBColor(27, 54, 93))

    add_speaker_note(slide4, "Bảng trên cho thấy SQLite + LRU Cache đưa thời gian tra cứu về 17 micro-giây, chịu tải hơn 11,500 lượt/giây. Bảng dưới chứng minh ReAct Agent nâng F1 từ 77% lên 100% và nhận diện đúng 87.5% ý định để tự động hủy đơn hoặc tra cứu bưu tá GHN.")

    # ===================================================================
    # SLIDE 5: Kiểm thử Hồi quy & Demo trên Streamlit UI (5/6)
    # ===================================================================
    slide5 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide5, LIGHT_BG)
    add_header(slide5, "Kiểm thử Hồi quy (18/18 Tests) & Demo Giao diện Streamlit UI")

    add_card(slide5, Inches(0.8), Inches(1.5), Inches(5.6), Inches(5.3),
             "Kiểm thử Tự động Toàn diện (18/18 Tests Passed)",
             [
                 "Lệnh chạy: python -m unittest discover tests (chạy trong 0.19 giây).",
                 "12 Tests Module 1 & 2: Guardrail độ tin cậy, Financial Guard chặn hoàn tiền, Policy Freshness Guard chặn điều khoản hết hạn.",
                 "6 Tests Module 3: Tự động migrate 100 đơn hàng, tra cứu chỉ mục SĐT/mã đơn, kiểm thử eviction và invalidation của LRU Cache, logic hủy đơn an toàn.",
                 "Độ ổn định: Đạt 100% test case, sẵn sàng tích hợp CI/CD."
             ], ACCENT_GREEN)

    add_card(slide5, Inches(6.8), Inches(1.5), Inches(5.6), Inches(5.3),
             "Trải nghiệm Thực tế trên UI (http://localhost:8501)",
             [
                 "Kịch bản 1 (Tra cứu qua SĐT): Khách nhập 'Kiểm tra đơn của SĐT 0938.242.854' ➔ Tool check_order_status tự chạy, kéo lộ trình bưu tá GHN và thông tin đơn ORD-1001 lên màn hình.",
                 "Kịch bản 2 (Hủy đơn an toàn): Khách nhập 'Hủy đơn ORD-1026 giúp tôi' ➔ Tool cancel_order tự kích hoạt, cập nhật CSDL sang 'Cancelled' và xóa cache.",
                 "Bảo vệ nghiệp vụ: Đơn đang giao (ORD-1001) bị từ chối hủy.",
                 "Tab 2 (Dashboard): Giám sát realtime Hit Ratio, Cache Hits/Misses."
             ], NAVY_PRIMARY)

    add_speaker_note(slide5, "Toàn bộ hệ thống đã được kiểm thử tự động với 18/18 bài test vượt qua. Trên giao diện Streamlit, khi gõ câu hỏi bằng SĐT hoặc yêu cầu hủy đơn, hệ thống sẽ tự động gọi tool và cập nhật thẳng vào CSDL trước mắt nhân viên CSKH.")

    # ===================================================================
    # SLIDE 6: Tổng kết & Định hướng Phát triển (6/6)
    # ===================================================================
    slide6 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide6, LIGHT_BG)
    add_header(slide6, "Tổng kết Giá trị Đạt được & Định hướng Tiếp theo")

    add_card(slide6, Inches(0.8), Inches(1.5), Inches(5.6), Inches(5.3),
             "Tổng kết Giá trị Đạt được (Module 2 & 3)",
             [
                 "Module 2 (RAG Tri thức Chính sách):",
                 "  • Làm chủ 5 thuật toán tìm kiếm từ khóa và vector.",
                 "  • Đưa độ trễ tìm chính sách về 0.66 ms (< 15 ms).",
                 "  • Độ chính xác tuyệt đối: Hit Rate@3 = 100%, MRR@3 = 0.98.",
                 "Module 3 (Dữ liệu Động & Tool Calling):",
                 "  • Xóa bỏ nghẽn I/O, nâng thông lượng lên 11,532 req/s.",
                 "  • Độ trễ CSDL đạt 0.017 ms trên RAM và 0.85 ms trên đĩa (< 2 ms).",
                 "  • ReAct Agent tự bóc tách thực thể và thực thi tool (F1 = 100%).",
                 "  • Tuân thủ Human-in-the-Loop: Nhân viên kiểm duyệt trước khi gửi."
             ], NAVY_PRIMARY)

    add_card(slide6, Inches(6.8), Inches(1.5), Inches(3.6), Inches(5.3),
             "Ba Định hướng Phát triển Kế tiếp",
             [
                 "1. Finetuning Intent tiếng Việt: Huấn luyện lại model phân loại trên tập Vietnamese-Customer-Support-QA để nâng độ tin cậy từ 10% lên > 90%.",
                 "2. Redis Cache Phân tán: Mở rộng lớp OrderLRUCache sang Redis Cluster khi chạy nhiều container.",
                 "3. Mở rộng Function Tools: Thêm tool xuất hóa đơn VAT, đổi địa chỉ nhận hàng và áp voucher."
             ], ACCENT_BLUE)

    # Mini conclusion box
    add_card(slide6, Inches(10.6), Inches(1.5), Inches(1.9), Inches(5.3),
             "Lời kết",
             [
                 "Mã nguồn, dữ liệu benchmark và tài liệu Word đã lưu trữ đầy đủ trong thư mục reports.",
                 "Sẵn sàng triển khai thực tế!"
             ], ACCENT_GREEN)

    add_speaker_note(slide6, "Tóm lại, Module 2 giúp AI hiểu luật và trích dẫn chính xác trong chưa đầy 1 mili-giây. Module 3 giúp AI có đôi tay hành động, tra cứu và thao tác trực tiếp vào dữ liệu nghiệp vụ với thông lượng hơn 11 nghìn lượt mỗi giây. Em xin chân thành cảm ơn!")

    OUTPUT_PPTX.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUTPUT_PPTX))
    print(f"Compact presentation created successfully at: {OUTPUT_PPTX}")

if __name__ == "__main__":
    create_compact_presentation()

"""Generate widescreen PowerPoint presentation (.pptx) for Module 2 & 3."""
from pathlib import Path
import pptx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

OUTPUT_PPTX = Path("reports/thuyet_trinh_module_2_va_3.pptx")

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
    # Category tag
    cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.35))
    tf_cat = cat_box.text_frame
    tf_cat.word_wrap = True
    p_cat = tf_cat.paragraphs[0]
    p_cat.text = category_text.upper()
    p_cat.font.size = Pt(9.5)
    p_cat.font.bold = True
    p_cat.font.color.rgb = ACCENT_BLUE

    # Slide Title
    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.7))
    tf_title = title_box.text_frame
    tf_title.word_wrap = True
    p_title = tf_title.paragraphs[0]
    p_title.text = title_text
    p_title.font.size = Pt(22)
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

    # Title
    p_title = tf.paragraphs[0]
    p_title.text = title
    p_title.font.size = Pt(14)
    p_title.font.bold = True
    p_title.font.color.rgb = title_color
    p_title.space_after = Pt(8)

    # Bullets
    for item in body_bullets:
        p = tf.add_paragraph()
        p.text = f"•  {item}"
        p.font.size = Pt(11)
        p.font.color.rgb = DARK_SLATE
        p.space_after = Pt(4)

def add_styled_table(slide, left, top, width, height, headers, data, col_widths, header_bg=NAVY_PRIMARY):
    """Create a styled benchmark table."""
    rows = len(data) + 1
    cols = len(headers)
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    table = table_shape.table

    # Set column widths
    for i, w in enumerate(col_widths):
        table.columns[i].width = w

    # Header Row
    for i, title in enumerate(headers):
        cell = table.cell(0, i)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_bg
        p = cell.text_frame.paragraphs[0]
        p.text = title
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Data Rows
    for row_idx, row_values in enumerate(data):
        row_num = row_idx + 1
        bg = LIGHT_ROW if row_idx % 2 == 1 else WHITE
        for col_idx, val in enumerate(row_values):
            cell = table.cell(row_num, col_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg
            p = cell.text_frame.paragraphs[0]
            p.text = str(val)
            p.font.size = Pt(10)
            p.font.color.rgb = DARK_SLATE
            if col_idx == 0:
                p.alignment = PP_ALIGN.LEFT
            else:
                p.alignment = PP_ALIGN.CENTER
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

def create_presentation():
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT
    blank_layout = prs.slide_layouts[6]

    # ===================================================================
    # SLIDE 1: Title Slide
    # ===================================================================
    slide1 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide1, LIGHT_BG)

    # Accent decorative block
    shape = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.15), Inches(3.6))
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT_BLUE
    shape.line.fill.background()

    # Title box
    tbox = slide1.shapes.add_textbox(Inches(1.2), Inches(1.6), Inches(11.0), Inches(3.8))
    tf1 = tbox.text_frame
    tf1.word_wrap = True

    p0 = tf1.paragraphs[0]
    p0.text = "AI CUSTOMER SUPPORT COPILOT (E-COMMERCE)"
    p0.font.size = Pt(13)
    p0.font.bold = True
    p0.font.color.rgb = ACCENT_BLUE
    p0.space_after = Pt(12)

    p1 = tf1.add_paragraph()
    p1.text = "Tối ưu hóa RAG Chính sách & Tích hợp Dữ liệu Động Thời gian thực"
    p1.font.size = Pt(28)
    p1.font.bold = True
    p1.font.color.rgb = NAVY_PRIMARY
    p1.space_after = Pt(10)

    p2 = tf1.add_paragraph()
    p2.text = "Báo cáo Kỹ thuật & Thực nghiệm Chuyên sâu: Module 2 (Policy RAG) và Module 3 (Dynamic Orders & Tool Calling)"
    p2.font.size = Pt(14)
    p2.font.color.rgb = DARK_SLATE
    p2.space_after = Pt(24)

    p3 = tf1.add_paragraph()
    p3.text = "⚡ Module 2: BM25 Latency 0.66 ms (Hit Rate 100%)    |    ⚡ Module 3: LRU Cache 11,532 QPS (F1 100%)    |    ⚡ 18/18 Tests Passed"
    p3.font.size = Pt(11)
    p3.font.bold = True
    p3.font.color.rgb = ACCENT_GREEN

    add_speaker_note(slide1, "Kính chào thầy cô và anh chị. Hôm nay em xin trình bày báo cáo kỹ thuật 2 module cốt lõi của dự án AI Copilot CSKH: Module 2 giải bài toán tra cứu tri thức chính sách sàn TMĐT (RAG), và Module 3 giải bài toán truy xuất CSDL đơn hàng và gọi công cụ nghiệp vụ theo thời gian thực (Tool Calling).")

    # ===================================================================
    # SLIDE 2: Bối cảnh & Thách thức
    # ===================================================================
    slide2 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide2, LIGHT_BG)
    add_header(slide2, "Bối cảnh Nghiệp vụ & Hai Thách thức Kỹ thuật Lớn")

    add_card(slide2, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Thách thức 1: Tri thức Tĩnh (Module 2)",
             [
                 "Khách hỏi chính sách đổi trả, bảo hành, hoàn tiền của sàn TMĐT.",
                 "Kho tri thức gồm 50 văn bản pháp lý (47 có hiệu lực, 3 đã hết hạn).",
                 "Rủi ro ảo giác (Hallucination): LLM tự bịa điều khoản hoặc trích nhầm chính sách cũ.",
                 "Ràng buộc độ trễ khắt khe: Phải tìm ra Top 3 điều khoản chính xác trong thời gian < 15 ms để kịp luồng hội thoại.",
                 "Giải pháp: Thử nghiệm và đối sánh 5 thuật toán Retrieval (BM25, Dense, Hybrid RRF, Reranker)."
             ], NAVY_PRIMARY)

    add_card(slide2, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Thách thức 2: Dữ liệu Động (Module 3)",
             [
                 "Khách hỏi tình trạng đơn hàng cụ thể, yêu cầu hủy đơn, tra cứu theo SĐT.",
                 "Dữ liệu thay đổi liên tục: Trạng thái đơn, vị trí bưu tá GHN/Tiki, số tiền thanh toán.",
                 "Điểm nghẽn cũ: Quét file JSON tuần tự khiến I/O bị nghẽn (> 2.16 ms), Regex cứng bỏ sót tiếng lóng.",
                 "Ràng buộc CSDL & Nghiệp vụ: Độ trễ truy vấn phải đạt < 2.0 ms và tự động kích hoạt hành động hủy/tra cứu an toàn.",
                 "Giải pháp: SQLite B-Tree Index + LRU Cache O(1) + ReAct Agent gọi Function Tools."
             ], ACCENT_BLUE)

    add_speaker_note(slide2, "Một hệ thống AI CSKH thực tế không thể chỉ biết trả lời lý thuyết chung chung. Nó phải giải quyết đồng thời: tra cứu tri thức chính sách sàn siêu tốc (Module 2) và thao tác trực tiếp trên dữ liệu đơn hàng sống của từng khách hàng (Module 3).")

    # ===================================================================
    # SLIDE 3: Module 2 — Thiết kế 5 Thuật toán Retrieval
    # ===================================================================
    slide3 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide3, LIGHT_BG)
    add_header(slide3, "Module 2: Thiết kế Thực nghiệm 5 Thuật toán RAG Search")

    m2_cards = [
        ("1. TF-IDF + Cosine (Baseline)", ["Mô hình tần suất từ khóa cổ điển (n-gram 1, 2).", "Nhẹ, nhanh nhưng không hiểu biến thể từ đồng nghĩa."], Inches(0.8), Inches(1.6)),
        ("2. BM25Okapi (Lexical)", ["Chuẩn hóa theo chiều dài văn bản tài liệu.", "Cực kỳ mạnh với từ khóa chính xác: số ngày, điều kiện đổi trả."], Inches(6.8), Inches(1.6)),
        ("3. Dense Embedding (sBERT / BGE-M3)", ["Mã hóa vector ngữ nghĩa không gian 768/1024 chiều.", "Tìm kiếm bằng FAISS IndexFlatIP / Cosine similarity."], Inches(0.8), Inches(4.3)),
        ("4. Hybrid RRF & Cross-Encoder", [
            "Hybrid RRF (k=60): Dung hợp thứ hạng BM25 + Dense vector.",
            "Reranker: Cross-Encoder BAAI/bge-reranker-base chấm điểm lại top 10.",
            "Bộ test: 55 câu hỏi tiếng Việt gán nhãn thủ công (retrieval_eval.json)."
        ], Inches(6.8), Inches(4.3)),
    ]
    for title, bullets, l, t in m2_cards:
        add_card(slide3, l, t, Inches(5.6), Inches(2.4), title, bullets, NAVY_PRIMARY)

    add_speaker_note(slide3, "Ở Module 2, nhóm không chọn cảm tính một model trên mạng mà đã triển khai cả 5 trường phái: từ tìm kiếm từ khóa cổ điển (TF-IDF, BM25) đến AI vector ngữ nghĩa (Dense, Hybrid RRF) và mô hình Cross-Encoder Reranker sâu nhất để đo lường khách quan.")

    # ===================================================================
    # SLIDE 4: Module 2 — Bảng Benchmark & Quyết định Kiến trúc
    # ===================================================================
    slide4 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide4, LIGHT_BG)
    add_header(slide4, "Module 2: Kết quả Benchmark Đối sánh & Quyết định Kiến trúc")

    headers2 = ["Thuật toán Retrieval", "Hit Rate@3", "Recall@3", "MRR@3", "Độ trễ p50", "Độ trễ p95", "Chuẩn <15ms"]
    data2 = [
        ["1. BM25Okapi (Mặc định)", "100.00%", "99.04%", "0.9808", "0.30 ms", "0.66 ms", "✅ XUẤT SẮC"],
        ["2. TF-IDF + Cosine (Baseline)", "100.00%", "99.04%", "0.9808", "1.13 ms", "2.39 ms", "✅ ĐẠT"],
        ["3. Dense (vietnamese-sbert)", "86.54%", "85.58%", "0.8462", "83.29 ms", "127.92 ms", "❌ VƯỢT"],
        ["4. Hybrid RRF (BM25 + Dense)", "96.15%", "95.19%", "0.9423", "85.86 ms", "114.71 ms", "❌ VƯỢT"],
        ["5. Cross-Encoder Reranked", "98.08%", "98.08%", "0.9679", "2,675 ms", "3,773 ms", "❌ VƯỢT"],
    ]
    widths2 = [Inches(2.6), Inches(1.5), Inches(1.5), Inches(1.4), Inches(1.5), Inches(1.5), Inches(1.7)]
    add_styled_table(slide4, Inches(0.8), Inches(1.6), Inches(11.7), Inches(2.8), headers2, data2, widths2)

    # Architectural Decision Card
    add_card(slide4, Inches(0.8), Inches(4.7), Inches(11.7), Inches(2.1),
             "Quyết định Kiến trúc (Key Architectural Decision)",
             [
                 "BM25Okapi được chọn làm mặc định cho Production: Đạt Hit Rate@3 = 100%, độ trễ p95 chỉ 0.66 ms trên CPU (vượt xa chỉ tiêu < 15 ms).",
                 "So sánh hiệu năng: BM25 nhanh hơn Dense 193 lần và nhanh hơn Reranker 5,700 lần trên phần cứng CPU.",
                 "Kiểm soát an toàn (Policy Guard): Tự động phát hiện và chặn các điều khoản hết hiệu lực (inactive), ép buộc trích dẫn [POL-xxx]."
             ], ACCENT_GREEN)

    add_speaker_note(slide4, "Kết quả chứng minh: Không phải cứ Deep Learning nặng là tốt nhất. Với kho 47 chính sách TMĐT, BM25 cho độ chính xác cao hơn Dense (100% vs 86.5%) mà tốc độ chỉ mất 0.66 mili-giây, hoàn toàn đáp ứng chỉ tiêu thời gian thực trên CPU.")

    # ===================================================================
    # SLIDE 5: Module 3 — Bài toán Dữ liệu Động & Nút thắt Baseline
    # ===================================================================
    slide5 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide5, LIGHT_BG)
    add_header(slide5, "Module 3: Bài toán Dữ liệu Động & Hai Nút thắt Cũ (Baseline)")

    add_card(slide5, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Nút thắt 1: Nghẽn I/O Database File JSON",
             [
                 "Dữ liệu gốc: 100 đơn hàng Tiki lưu trong mock_orders.json.",
                 "Cơ chế cũ (Baseline): Mỗi khi có tin nhắn, server phải mở file ổ đĩa, gọi json.loads() giải mã toàn bộ danh sách.",
                 "Duyệt tuyến tính O(N): Đơn hàng ở cuối danh sách thì phải quét qua 99 đơn phía trước.",
                 "Hậu quả: Độ trễ p95 đạt 2.1654 ms ➔ Vi phạm chỉ tiêu kỹ thuật (< 2.0 ms), thông lượng chỉ đạt ~1,100 req/s.",
                 "Không có Transaction: Không thể cập nhật trạng thái đơn (hủy đơn) an toàn."
             ], ACCENT_RED)

    add_card(slide5, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Nút thắt 2: Regex Cứng bỏ sót Thực thể",
             [
                 "Baseline cũ: Chỉ dùng 1 biểu thức cứng: r'\\bORD-[A-Z0-9-]+\\b'.",
                 "Bỏ sót biến thể tiếng lóng: Khách gõ 'đơn 1005', '#1007', 'ord-1004' (chữ thường) ➔ Regex bị mù, Recall tụt còn 62.96%.",
                 "Bỏ sót 100% Số điện thoại: Khách gõ SĐT '0938.242.854' ➔ Regex hoàn toàn không nhận diện được (Recall = 0.0%).",
                 "Chỉ trích xuất, không hiểu hành động: Không biết khách muốn hủy hay muốn xem tiến độ giao hàng để gọi Tool xử lý."
             ], ACCENT_RED)

    add_speaker_note(slide5, "Hệ thống cũ có 2 điểm yếu chí mạng: Thứ nhất là đọc file JSON liên tục khiến server bị nghẽn I/O và vi phạm mốc 2ms; thứ hai là Regex quá cứng nhắc, khách chỉ cần gõ thiếu chữ ORD- hoặc dùng số điện thoại là bot chịu thua hoàn toàn.")

    # ===================================================================
    # SLIDE 6: Module 3 — 4 Trụ cột Kỹ thuật Triển khai
    # ===================================================================
    slide6 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide6, LIGHT_BG)
    add_header(slide6, "Module 3: Bốn Trụ cột Kỹ thuật Triển khai")

    m3_pillars = [
        ("1. CSDL SQLite (B-Tree Indexing)", [
            "Chuyển 100 đơn hàng vào bảng orders (SQLite WAL Mode).",
            "Đánh chỉ mục B-Tree trên: order_id, customer_id, phone, tracking_code, order_status.",
            "Giảm độ phức tạp từ O(N) xuống O(log N)."
        ], Inches(0.8), Inches(1.6)),
        ("2. Bộ nhớ đệm 2 tầng (OrderLRUCache)", [
            "Cache in-memory trên RAM dung lượng 256 mục.",
            "Tra cứu O(1) qua 4 khóa: mã đơn, SĐT chuẩn hóa, customer_id, mã vận đơn.",
            "Tự động xóa cache (Invalidation) khi đơn bị hủy."
        ], Inches(6.8), Inches(1.6)),
        ("3. Chuẩn hóa 4 Function Tools (JSON Schema)", [
            "get_order_details(order_id): Xem chi tiết giỏ hàng, số tiền.",
            "check_order_status(identifier): Tra cứu bưu tá GHN/Tiki.",
            "cancel_order(order_id, reason): Hủy đơn trong CSDL.",
            "get_customer_orders(customer_id): Xem lịch sử mua hàng."
        ], Inches(0.8), Inches(4.3)),
        ("4. ReAct Agent & Multi-Entity Extractor", [
            "Bóc tách đa thực thể: Chuẩn hóa '#1007' -> 'ORD-1007'.",
            "Làm sạch SĐT: '+84938.242.854' -> '0938242854'.",
            "Phân loại Action Intent: Tự động quyết định gọi đúng Tool."
        ], Inches(6.8), Inches(4.3)),
    ]
    for title, bullets, l, t in m3_pillars:
        add_card(slide6, l, t, Inches(5.6), Inches(2.4), title, bullets, NAVY_PRIMARY)

    add_speaker_note(slide6, "Để giải quyết triệt để, nhóm đã xây dựng 4 trụ cột: Di chuyển CSDL có Index B-Tree, dựng bộ nhớ đệm LRU Cache trên RAM, chuẩn hóa 4 Tool nghiệp vụ theo chuẩn JSON Schema, và trang bị bộ não ReAct Agent tự bóc tách thực thể.")

    # ===================================================================
    # SLIDE 7: Module 3 — Benchmark 1: Độ trễ CSDL & Thông lượng
    # ===================================================================
    slide7 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide7, LIGHT_BG)
    add_header(slide7, "Module 3: Benchmark Độ trễ Database (Mục tiêu: p95 < 2.0 ms)")

    headers3_1 = ["Phương pháp Lưu trữ", "Độ phức tạp", "Độ trễ p50", "Độ trễ p90", "Độ trễ p95", "Thông lượng (QPS)", "Đạt < 2ms?"]
    data3_1 = [
        ["1. Baseline JSON Scan", "O(N) Disk I/O", "0.6916 ms", "1.8315 ms", "2.1654 ms", "1,110 req/s", "❌ VƯỢT"],
        ["2. SQLite Unindexed", "O(N) Full Table", "0.5712 ms", "0.9412 ms", "1.1105 ms", "1,518 req/s", "✅ ĐẠT"],
        ["3. SQLite Indexed", "O(log N) B-Tree", "0.5236 ms", "0.7410 ms", "0.8473 ms", "1,738 req/s", "✅ ĐẠT"],
        ["4. SQLite + LRU Cache", "O(1) In-Memory", "0.0176 ms", "0.0210 ms", "0.5499 ms", "11,532 req/s", "✅ XUẤT SẮC"],
    ]
    widths3_1 = [Inches(2.5), Inches(1.5), Inches(1.3), Inches(1.3), Inches(1.3), Inches(1.9), Inches(1.5)]
    add_styled_table(slide7, Inches(0.8), Inches(1.6), Inches(11.7), Inches(2.5), headers3_1, data3_1, widths3_1)

    # Technical Insights Card
    add_card(slide7, Inches(0.8), Inches(4.4), Inches(11.7), Inches(2.4),
             "Phân tích Bản chất Kỹ thuật",
             [
                 "Vì sao CSDL chỉ đo Latency & QPS mà không đo 'chất lượng'? Vì truy vấn CSDL là phép toán xác định 100% (tìm ORD-1001 ở đâu cũng trả về đúng dữ liệu đó). Tiêu chí cạnh tranh duy nhất là độ trễ và khả năng chịu tải.",
                 "SQLite Indexed: Nhờ cấu trúc B-Tree, độ trễ p95 giảm 61% (xuống 0.85 ms), đáp ứng hoàn hảo KPI thiết kế.",
                 "SQLite + LRU Cache: Tốc độ đọc RAM vượt trội giúp độ trễ trung bình chỉ còn 0.017 ms (17 micro-giây) và tăng thông lượng gấp 10.4 lần (đạt 11,532 truy vấn/giây)."
             ], ACCENT_GREEN)

    add_speaker_note(slide7, "Nhìn vào bảng số liệu, Baseline JSON vi phạm tiêu chuẩn với p95 là 2.16 ms. Khi có chỉ mục B-Tree, p95 giảm xuống 0.84 ms. Đặc biệt, khi kết hợp LRU Cache, tốc độ đạt 17 micro-giây, hệ thống có thể chịu tải hơn 11,500 lượt tra cứu mỗi giây.")

    # ===================================================================
    # SLIDE 8: Module 3 — Benchmark 2: Bóc tách Thực thể & Tool Intent
    # ===================================================================
    slide8 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide8, LIGHT_BG)
    add_header(slide8, "Module 3: Benchmark Trích xuất Thực thể & Nhận diện Tool Intent")

    headers3_2 = ["Thành phần & Thuật toán", "Precision", "Recall", "F1-Score", "Ghi chú & Phân tích"]
    data3_2 = [
        ["Baseline Regex (Mã đơn hàng)", "100.00%", "62.96%", "77.27%", "Bỏ sót 37% mã viết tắt, '#1007', 'đơn 1005'"],
        ["Advanced ReAct (Mã đơn hàng)", "100.00%", "100.00%", "100.00%", "Bắt trúng 100% mọi biến thể cú pháp tự nhiên"],
        ["Baseline Regex (Số điện thoại)", "0.00%", "0.00%", "0.00%", "Hoàn toàn không hỗ trợ nhận diện SĐT"],
        ["Advanced ReAct (Số điện thoại)", "100.00%", "100.00%", "100.00%", "Bóc tách chính xác các định dạng 0938..., +84..."],
        ["Độ chính xác Action Intent", "—", "—", "87.50%", "Nhận diện đúng 87.5% ý định gọi Tool nghiệp vụ"],
    ]
    widths3_2 = [Inches(2.8), Inches(1.3), Inches(1.3), Inches(1.4), Inches(4.5)]
    add_styled_table(slide8, Inches(0.8), Inches(1.6), Inches(11.7), Inches(2.9), headers3_2, data3_2, widths3_2)

    # Explanation Card
    add_card(slide8, Inches(0.8), Inches(4.8), Inches(11.7), Inches(2.0),
             "Độ chính xác nhận diện Tool Action Intent (87.5%) để làm gì?",
             [
                 "Khách nói: 'Hủy đơn ORD-1026 giúp tôi vì không có tiền nhận' -> Chatbot cũ chỉ tra đơn rồi nói suông; AI Copilot hiểu intent 'cancel', bóc lý do và tự động gọi tool cancel_order('ORD-1026') cập nhật CSDL ngay lập tức.",
                 "F1 = 100% chứng minh hệ thống không bắt nhầm dãy số linh tinh (Precision 100%) và không bỏ sót bất kỳ thói quen gõ chat nào của người Việt (Recall 100%)."
             ], NAVY_PRIMARY)

    add_speaker_note(slide8, "Ở phần bóc tách thực thể, Baseline Regex chỉ đạt F1 77% trên mã đơn và 0% trên SĐT. Bộ ReAct Agent đạt F1 tuyệt đối 100% trên cả 2 trường, đồng thời đoán đúng 87.5% ý định gọi công cụ của khách hàng để thực thi nghiệp vụ thật.")

    # ===================================================================
    # SLIDE 9: Kiểm thử Hồi quy & Demo trên Streamlit UI
    # ===================================================================
    slide9 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide9, LIGHT_BG)
    add_header(slide9, "Kiểm thử Hồi quy (18/18 Tests) & Giao diện Streamlit Workbench")

    add_card(slide9, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Kiểm thử Tự động (18/18 Tests Passed)",
             [
                 "Bộ kiểm thử toàn diện: python -m unittest discover tests.",
                 "12 tests hồi quy Module 1 & 2: Guardrails, Latency benchmark, Policy Freshness.",
                 "6 tests tích hợp Module 3: Migration count 100 đơn, Tra cứu mã đơn & SĐT, LRU Cache eviction, Logic hủy đơn an toàn, Bóc tách thực thể.",
                 "Thời gian chạy toàn bộ: 0.19 giây (Độ ổn định 100%)."
             ], ACCENT_GREEN)

    add_card(slide9, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Tích hợp Streamlit UI (Port 8501)",
             [
                 "Tab 1 (Agent Workbench):",
                 "  • Hộp 'Tool Calling thời gian thực': Hiển thị tên tool, tham số, độ trễ ms và JSON kết quả.",
                 "  • Hộp đối soát đơn hàng: Hiển thị giỏ hàng, số tiền, lộ trình bưu tá GHN.",
                 "  • 4 nút Human-in-the-Loop: Duyệt, Sửa, Từ chối, Chuyển cấp trên.",
                 "Tab 2 (Analytics Dashboard):",
                 "  • Giám sát trực tiếp hiệu năng LRU Cache (Hit Ratio %, Hits, Misses, Cache Size)."
             ], NAVY_PRIMARY)

    add_speaker_note(slide9, "Tất cả logic trên không chỉ nằm trên lý thuyết mà đã được tích hợp lên giao diện thật. Mọi người có thể gõ câu hỏi bằng SĐT hoặc yêu cầu hủy đơn, hệ thống sẽ tự động gọi tool và cập nhật thẳng vào CSDL trước mắt nhân viên.")

    # ===================================================================
    # SLIDE 10: Tổng kết Giá trị Đạt được
    # ===================================================================
    slide10 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide10, LIGHT_BG)
    add_header(slide10, "Tổng kết Giá trị Đạt được ở Module 2 & Module 3")

    add_card(slide10, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Module 2: RAG Tri thức Chính sách Sàn",
             [
                 "Làm chủ và đối sánh 5 kiến trúc tìm kiếm từ khóa và vector.",
                 "Đưa độ trễ truy xuất chính sách về 0.66 ms (vượt chỉ tiêu < 15 ms).",
                 "Độ chính xác hoàn hảo: Hit Rate@3 đạt 100.00%, Recall@3 đạt 99.04%.",
                 "Ràng buộc an toàn: Không bịa thông tin, bắt buộc trích dẫn mã điều khoản [POL-xxx] còn hiệu lực."
             ], NAVY_PRIMARY)

    add_card(slide10, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.2),
             "Module 3: Dữ liệu Động & Tool Calling",
             [
                 "Xóa bỏ điểm nghẽn I/O file JSON, nâng thông lượng lên 11,532 truy vấn/giây.",
                 "Đưa độ trễ truy xuất CSDL về 0.017 ms trên RAM và 0.85 ms trên đĩa B-Tree (< 2 ms).",
                 "Tự động hóa nghiệp vụ: ReAct Agent tự bóc tách thực thể và thực thi tool chuẩn xác (F1 = 100%).",
                 "Bảo vệ an toàn: Chặn hủy đơn đang giao, hỗ trợ đối soát tài chính trực tiếp."
             ], ACCENT_GREEN)

    add_speaker_note(slide10, "Tóm lại, Module 2 giúp AI hiểu luật và tìm đúng chính sách trong chưa đầy 1 mili-giây. Module 3 giúp AI có đôi tay hành động, tra cứu và thao tác trực tiếp vào dữ liệu nghiệp vụ với thông lượng hơn 11 nghìn lượt mỗi giây.")

    # ===================================================================
    # SLIDE 11: Định hướng Phát triển (Next Steps)
    # ===================================================================
    slide11 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide11, LIGHT_BG)
    add_header(slide11, "Định hướng Phát triển Giai đoạn Tiếp theo")

    add_card(slide11, Inches(0.8), Inches(1.6), Inches(3.6), Inches(5.2),
             "1. Finetuning Model Intent",
             [
                 "Hiện tại: Model Intent tiếng Anh bị lệch pha OOV với câu hỏi tiếng Việt.",
                 "Kế hoạch: Huấn luyện lại mô hình phân loại ý định trên tập dữ liệu Vietnamese-Customer-Support-QA (đã có sẵn trong data/raw).",
                 "Mục tiêu: Nâng độ tin cậy nhận diện câu tiếng Việt từ 10% lên > 90%."
             ], NAVY_PRIMARY)

    add_card(slide11, Inches(4.8), Inches(1.6), Inches(3.6), Inches(5.2),
             "2. Caching Phân tán (Redis)",
             [
                 "Hiện tại: OrderLRUCache chạy bộ nhớ trong RAM của 1 tiến trình.",
                 "Kế hoạch: Mở rộng lớp Caching sang Redis Cluster khi triển khai hệ thống phân tán trên Kubernetes nhiều Pod.",
                 "Mục tiêu: Chia sẻ cache đồng bộ giữa các cụm Gateway và Worker."
             ], ACCENT_BLUE)

    add_card(slide11, Inches(8.8), Inches(1.6), Inches(3.6), Inches(5.2),
             "3. Mở rộng Function Tools",
             [
                 "Hiện tại: Đã có 4 tool tra cứu và hủy đơn.",
                 "Kế hoạch: Tích hợp thêm các API nghiệp vụ nâng cao:",
                 "  • Xuất hóa đơn đỏ VAT điện tử.",
                 "  • Đổi địa chỉ nhận hàng linh hoạt.",
                 "  • Áp mã voucher khuyến mãi tự động."
             ], ACCENT_GREEN)

    add_speaker_note(slide11, "Trên đây là toàn bộ báo cáo tiến độ và kết quả thực nghiệm của Module 2 và Module 3. Toàn bộ mã nguồn, dữ liệu benchmark và tài liệu Word chi tiết đều đã được lưu trữ hoàn chỉnh trong thư mục reports. Em xin cảm ơn quý thầy cô/anh chị và rất mong nhận được câu hỏi góp ý!")

    # Save presentation
    OUTPUT_PPTX.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUTPUT_PPTX))
    print(f"Presentation successfully created at: {OUTPUT_PPTX}")

if __name__ == "__main__":
    create_presentation()

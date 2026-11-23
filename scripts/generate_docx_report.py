"""Script to generate the comprehensive Word (.docx) project report."""
from pathlib import Path
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

OUTPUT_DOCX = Path("reports/bao_cao_tong_the_tien_do_va_benchmark.docx")

def set_cell_background(cell, fill_hex):
    """Set background color of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set inner padding for table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def format_table(table, col_widths, headers, data, header_bg="1F4E79"):
    """Format table with professional borders, padding, and header shading."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Headers
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_background(hdr_cells[i], header_bg)
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=140, right=140)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in p.runs:
            r.font.bold = True
            r.font.color.rgb = RGBColor(255, 255, 255)
            r.font.size = Pt(10)
            r.font.name = "Calibri"

    # Data rows
    for row_idx, row_data in enumerate(data):
        row_cells = table.rows[row_idx + 1].cells
        bg_color = "F2F5F8" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, val in enumerate(row_data):
            row_cells[col_idx].text = str(val)
            set_cell_background(row_cells[col_idx], bg_color)
            set_cell_margins(row_cells[col_idx], top=80, bottom=80, left=140, right=140)
            p = row_cells[col_idx].paragraphs[0]
            if col_idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.size = Pt(9.5)
                r.font.name = "Calibri"

    # Set column widths
    for row in table.rows:
        for idx, width in enumerate(col_widths):
            row.cells[idx].width = Inches(width)

def build_report():
    doc = Document()

    # Set Margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)

    # Document Header / Pre-title
    p_meta = doc.add_paragraph()
    r_meta = p_meta.add_run("BÁO CÁO KỸ THUẬT VÀ THỰC NGHIỆM HỆ THỐNG")
    r_meta.font.size = Pt(10)
    r_meta.font.bold = True
    r_meta.font.color.rgb = RGBColor(100, 110, 120)

    # Document Title
    p_title = doc.add_paragraph()
    r_title = p_title.add_run("AI Customer Support Copilot: Mục tiêu, Tiến độ & Phương pháp Benchmark")
    r_title.font.size = Pt(22)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(31, 78, 121)

    p_sub = doc.add_paragraph()
    r_sub = p_sub.add_run("Báo cáo toàn diện về kiến trúc phân tán, kết quả thực nghiệm Module 2 (RAG Search) và Module 3 (Dynamic Data & Tool Calling)")
    r_sub.font.italic = True
    r_sub.font.size = Pt(11)
    r_sub.font.color.rgb = RGBColor(80, 80, 80)

    p_info = doc.add_paragraph()
    r_info = p_info.add_run("• Ngày báo cáo: 22/10/2026   |   • Trạng thái: Hoàn thành Module 1, Module 2, Module 3   |   • Bộ kiểm thử: 18/18 Tests Passed")
    r_info.font.size = Pt(9.5)
    r_info.font.bold = True
    r_info.font.color.rgb = RGBColor(46, 117, 182)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # ===================================================================
    # 1. TỔNG QUAN DỰ ÁN VÀ KIẾN TRÚC HỆ THỐNG
    # ===================================================================
    h1 = doc.add_heading("1. Tổng quan Dự án & Kiến trúc Hệ thống", level=1)
    h1.paragraph_format.space_before = Pt(12)

    doc.add_paragraph(
        "Dự án 'AI Customer Support Copilot' là hệ thống trợ lý thông minh hỗ trợ nhân viên chăm sóc khách hàng (CSKH) "
        "cho sàn thương mại điện tử (e-commerce). Hệ thống tuân thủ nghiêm ngặt nguyên lý Human-in-the-Loop: AI đóng vai trò "
        "phân tích, trích xuất dữ liệu, kiểm tra an toàn và soạn thảo bản nháp có căn cứ xác thực; quyền quyết định cuối cùng "
        "(duyệt, chỉnh sửa, từ chối, chuyển cấp trên) luôn thuộc về nhân viên vận hành trước khi gửi tin nhắn cho khách hàng."
    )

    doc.add_paragraph(
        "Hệ thống được thiết kế theo kiến trúc Microservices phân tán gồm 5 dịch vụ chuyên biệt giao tiếp qua REST API:"
    )

    services_data = [
        ["1. Gateway Orchestrator", "8000", "FastAPI", "Điều phối State Machine trung tâm, kiểm soát 3 tầng Guardrails, kích hoạt ReAct Agent & Tool Calling."],
        ["2. RAG & Knowledge Service", "8002", "FastAPI", "Quản lý 47 chính sách TMĐT, tích hợp 5 thuật toán tìm kiếm (BM25, Dense, Hybrid RRF), sinh nháp qua Gemini API."],
        ["3. Telemetry & Order Service", "8003", "FastAPI", "CSDL SQLite (WAL Mode), lưu trữ Audit log, quản lý 100 đơn hàng Tiki với B-Tree Index và Order LRU Cache."],
        ["4. Intent Classification", "8005", "FastAPI", "Phân loại ý định khách hàng (LinearSVC + TF-IDF), tính điểm tin cậy (Confidence Calibration) và phân phối xác suất."],
        ["5. CSKH Agent Workbench", "8501", "Streamlit", "Giao diện làm việc cho nhân viên CSKH (soạn nháp, xem trích dẫn, tra cứu đơn) và Dashboard giám sát phân tích."]
    ]
    t_svc = doc.add_table(rows=len(services_data) + 1, cols=4)
    format_table(t_svc, [1.6, 0.7, 0.9, 3.6], ["Dịch vụ Microservice", "Port", "Công nghệ", "Chức năng và Nhiệm vụ"], services_data)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ===================================================================
    # 2. TIẾN ĐỘ THỰC HIỆN CÁC MODULE
    # ===================================================================
    h2 = doc.add_heading("2. Tiến độ Thực hiện các Module Dự án", level=1)
    h2.paragraph_format.space_before = Pt(14)

    doc.add_paragraph(
        "Dự án được phân chia thành các Module trọng tâm bám sát tài liệu đặc tả nghiệp vụ. Bảng dưới đây tổng hợp tiến độ thực tế:"
    )

    progress_data = [
        ["Module 1: Ý định & An toàn (Guardrails)", "HOÀN TẤT", "Đã triển khai 3 tầng Guardrail (Intent Confidence < 60% abstention, Financial Guard chặn hoàn tiền tự động, Policy Freshness Guard chặn điều khoản hết hạn). Đã có pipeline ML Scikit-Learn."],
        ["Module 2: RAG & Tìm kiếm Chính sách", "HOÀN TẤT", "Đã triển khai và benchmark 5 phương pháp tìm kiếm (TF-IDF, BM25, Dense sBERT/BGE-M3, Hybrid RRF, Cross-Encoder Reranker). Cấu hình BM25 làm mặc định đạt p95 < 1ms."],
        ["Module 3: Dữ liệu Động & Tool Calling", "HOÀN TẤT", "Đã di chuyển 100 đơn hàng vào SQLite với chỉ mục B-Tree, bổ sung OrderLRUCache, chuẩn hóa 4 Function Tools và bộ bóc tách thực thể ReAct Agent. Đạt p95 = 0.55ms (< 2ms) và F1 = 100%."],
        ["Module 4: Vận hành & Giám sát Telemetry", "ĐANG VẬN HÀNH", "Đã lưu vết toàn diện mọi tương tác vào SQLite WAL, hiển thị thống kê phê duyệt và hiệu năng cache trên Streamlit Dashboard. Sẵn sàng cho vòng lặp Finetuning."]
    ]
    t_prog = doc.add_table(rows=len(progress_data) + 1, cols=3)
    format_table(t_prog, [2.0, 1.1, 3.7], ["Module Dự án", "Trạng thái", "Nội dung & Kết quả đã bàn giao"], progress_data, header_bg="203764")

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ===================================================================
    # 3. PHƯƠNG PHÁP BENCHMARK MODULE 2: RAG & TÌM KIẾM CHÍNH SÁCH
    # ===================================================================
    h3 = doc.add_heading("3. Phương pháp Benchmark Module 2 (RAG Policy Retrieval)", level=1)
    h3.paragraph_format.space_before = Pt(14)

    doc.add_paragraph(
        "Mục tiêu của Module 2 là xác định và đối sánh phương pháp tìm kiếm tối ưu nhất để truy xuất đúng top 3 điều khoản "
        "chính sách làm căn cứ trả lời cho câu hỏi của khách hàng, đảm bảo cân bằng giữa độ chính xác và độ trễ hệ thống."
    )

    doc.add_heading("3.1. Dữ liệu và Phương pháp Đánh giá", level=2)
    doc.add_paragraph("• Tập dữ liệu chính sách: 50 điều khoản TMĐT trong policies.json (47 điều khoản có hiệu lực, 3 điều khoản hết hạn).")
    doc.add_paragraph("• Tập dữ liệu kiểm thử (Evaluation Set): data/retrieval_eval.json gồm 55 câu hỏi tiếng Việt được gán nhãn thủ công (52 câu hỏi hợp lệ bao phủ đủ 47 chính sách, 3 câu hỏi ngoài phạm vi).")
    doc.add_paragraph("• Tiêu chí đánh giá (Metrics):")
    doc.add_paragraph("    - Hit Rate@3: Tỷ lệ câu hỏi mà ít nhất 1 chính sách đúng xuất hiện trong top 3 kết quả.")
    doc.add_paragraph("    - Recall@3: Tỷ lệ phần trăm tài liệu đúng được truy xuất thành công.")
    doc.add_paragraph("    - MRR@3 (Mean Reciprocal Rank): Điểm số phản ánh vị trí của tài liệu đúng đầu tiên trong danh sách xếp hạng.")
    doc.add_paragraph("    - Query Latency (p95): Độ trễ tại phân vị 95% (Mục tiêu thiết kế: p95 < 15 ms).")

    doc.add_heading("3.2. Kết quả Thực nghiệm Module 2", level=2)

    m2_data = [
        ["1. TF-IDF + Cosine (Baseline)", "100.00%", "99.04%", "0.9808", "1.13 ms", "2.39 ms", "✅ ĐẠT"],
        ["2. BM25Okapi (Mặc định)", "100.00%", "99.04%", "0.9808", "0.30 ms", "0.66 ms", "✅ XUẤT SẮC"],
        ["3. Dense (vietnamese-sbert)", "86.54%", "85.58%", "0.8462", "83.29 ms", "127.92 ms", "❌ VƯỢT"],
        ["4. Hybrid RRF (BM25 + Dense)", "96.15%", "95.19%", "0.9423", "85.86 ms", "114.71 ms", "❌ VƯỢT"],
        ["5. Cross-Encoder Reranked", "98.08%", "98.08%", "0.9679", "2,675 ms", "3,773 ms", "❌ VƯỢT"]
    ]
    t_m2 = doc.add_table(rows=len(m2_data) + 1, cols=7)
    format_table(t_m2, [1.9, 0.8, 0.8, 0.8, 0.8, 0.8, 0.9], ["Thuật toán Retrieval", "Hit@3", "Recall@3", "MRR@3", "p50 (ms)", "p95 (ms)", "Chuẩn <15ms"], m2_data)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    doc.add_paragraph(
        "Nhận xét kỹ thuật: BM25 đạt hiệu năng toàn diện nhất: vừa đạt độ chính xác tương đương/cao hơn mô hình Dense, "
        "vừa có độ trễ cực thấp (p95 chỉ 0.66 ms trên CPU, nhanh hơn Dense 193 lần và nhanh hơn Reranker 5,700 lần). "
        "Do đó, hệ thống chọn BM25 làm phương thức mặc định cho môi trường Production."
    )

    # ===================================================================
    # 4. PHƯƠNG PHÁP BENCHMARK MODULE 3: DỮ LIỆU ĐỘNG & TOOL CALLING
    # ===================================================================
    h4 = doc.add_heading("4. Phương pháp Benchmark Module 3 (Dynamic Data & Tool Calling)", level=1)
    h4.paragraph_format.space_before = Pt(14)

    doc.add_paragraph(
        "Module 3 giải quyết bài toán tra cứu và thao tác dữ liệu đơn hàng thời gian thực. Hệ thống chuyển đổi từ "
        "cơ chế quét file JSON và regex thô sơ sang cơ sở dữ liệu quan hệ có chỉ mục, bộ nhớ đệm đa khóa và Function Calling."
    )

    doc.add_heading("4.1. Cách thức Triển khai Benchmark Module 3", level=2)
    doc.add_paragraph("Script benchmark độc lập scripts/benchmark_module3.py thực hiện đo lường tự động trên 2 phương diện:")
    doc.add_paragraph("1. Benchmark Độ trễ CSDL: Thực hiện 400 truy vấn ngẫu nhiên đại diện tải thực tế qua 4 phương pháp:")
    doc.add_paragraph("    - Baseline JSON Scan: Đọc lại file mock_orders.json và duyệt tuyến tính mảng danh sách.")
    doc.add_paragraph("    - SQLite Unindexed: Quét toàn bảng SQLite không sử dụng chỉ mục.")
    doc.add_paragraph("    - SQLite Indexed: Truy vấn bằng B-Tree Index trên các cột order_id, phone, customer_id.")
    doc.add_paragraph("    - SQLite + LRU Cache: Truy vấn qua OrderLRUCache với kịch bản mô phỏng 80% truy vấn lặp lại.")
    doc.add_paragraph("2. Benchmark Trích xuất Thực thể (Entity Extraction): Đánh giá trên tập 40 câu hội thoại đa dạng (data/module3_eval_dataset.json) gồm mã đơn chuẩn, mã viết tắt (#1007, đơn 1005), số điện thoại, mã vận đơn và ý định hủy đơn/tra cứu.")

    doc.add_heading("4.2. Kết quả Đo lường Độ trễ Database (Database Lookup Latency)", level=2)

    m3_lat_data = [
        ["1. Baseline JSON Scan", "0.6916 ms", "1.8315 ms", "2.1654 ms", "2.8941 ms", "1,110 req/s", "❌ VƯỢT"],
        ["2. SQLite Unindexed", "0.5712 ms", "0.9412 ms", "1.1105 ms", "1.5420 ms", "1,518 req/s", "✅ ĐẠT"],
        ["3. SQLite Indexed", "0.5236 ms", "0.7410 ms", "0.8473 ms", "1.2185 ms", "1,738 req/s", "✅ ĐẠT"],
        ["4. SQLite + LRU Cache", "0.0176 ms", "0.0210 ms", "0.5499 ms", "0.8120 ms", "11,532 req/s", "✅ XUẤT SẮC"]
    ]
    t_m3_lat = doc.add_table(rows=len(m3_lat_data) + 1, cols=7)
    format_table(t_m3_lat, [1.9, 0.8, 0.8, 0.8, 0.8, 0.9, 0.8], ["Phương pháp Lưu trữ", "p50", "p90", "p95", "p99", "Thông lượng", "Chuẩn <2ms"], m3_lat_data)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    doc.add_heading("4.3. Kết quả Trích xuất Thực thể & Nhận diện Tool Intent", level=2)

    m3_ext_data = [
        ["Baseline Regex (Mã đơn hàng)", "100.00%", "62.96%", "77.27%", "Bỏ sót hoàn toàn các dạng: 'đơn 1005', '#1007', 'ord-1004'"],
        ["Advanced ReAct (Mã đơn hàng)", "100.00%", "100.00%", "100.00%", "Chuẩn hóa hoàn hảo mọi biến thể cú pháp về mã chuẩn ORD-xxxx"],
        ["Baseline Regex (Số điện thoại)", "0.00%", "0.00%", "0.00%", "Hoàn toàn không hỗ trợ nhận diện số điện thoại"],
        ["Advanced ReAct (Số điện thoại)", "100.00%", "100.00%", "100.00%", "Bóc tách chính xác các định dạng 0938.242.854, 0938242854, +84..."],
        ["Độ chính xác Action Intent", "—", "—", "87.50%", "Nhận diện chuẩn xác ý định gọi tool: Hủy đơn, Tra cứu, Hóa đơn"]
    ]
    t_m3_ext = doc.add_table(rows=len(m3_ext_data) + 1, cols=5)
    format_table(t_m3_ext, [2.1, 0.9, 0.9, 0.9, 2.0], ["Thành phần Đánh giá", "Precision", "Recall", "F1-Score", "Ghi chú Phân tích"], m3_ext_data, header_bg="1B365D")

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ===================================================================
    # 5. HƯỚNG DẪN KIỂM THỬ VÀ VẬN HÀNH TOÀN BỘ HỆ THỐNG
    # ===================================================================
    h5 = doc.add_heading("5. Hướng dẫn Kiểm thử & Vận hành Hệ thống", level=1)
    h5.paragraph_format.space_before = Pt(14)

    doc.add_paragraph("Để tái lập kết quả và vận hành kiểm thử hệ thống, người dùng thực hiện các lệnh sau trên PowerShell:")

    doc.add_paragraph("1. Chạy bài Benchmark Module 2 (RAG Search):")
    p_c1 = doc.add_paragraph()
    r_c1 = p_c1.add_run("   python scripts/benchmark_retrieval.py --methods tfidf,bm25")
    r_c1.font.name = "Consolas"
    r_c1.font.size = Pt(9.5)

    doc.add_paragraph("2. Chạy bài Benchmark Module 3 (Dynamic Data & Tool Calling):")
    p_c2 = doc.add_paragraph()
    r_c2 = p_c2.add_run("   python scripts/benchmark_module3.py")
    r_c2.font.name = "Consolas"
    r_c2.font.size = Pt(9.5)

    doc.add_paragraph("3. Chạy toàn bộ 18 Unit & Integration Tests tự động:")
    p_c3 = doc.add_paragraph()
    r_c3 = p_c3.add_run("   python -m unittest discover tests")
    r_c3.font.name = "Consolas"
    r_c3.font.size = Pt(9.5)

    doc.add_paragraph("4. Khởi động toàn bộ cụm 5 Microservices (Local Development không cần Docker):")
    p_c4 = doc.add_paragraph()
    r_c4 = p_c4.add_run("   python run_dev.py")
    r_c4.font.name = "Consolas"
    r_c4.font.size = Pt(9.5)

    doc.add_paragraph("Sau khi khởi động, truy cập http://localhost:8501 để thử nghiệm giao diện CSKH và xem Telemetry Dashboard.")

    # Save document
    OUTPUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUTPUT_DOCX))
    print(f"Document successfully created at: {OUTPUT_DOCX}")

if __name__ == "__main__":
    build_report()

"""Generate a comprehensive Word (.docx) report benchmarking 4 approaches for Module 3."""
import json
import os
import sys
from pathlib import Path
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

OUTPUT_FILE = Path("reports/bao_cao_benchmark_4_phuong_phap_module3.docx")
BENCHMARK_JSON = Path("reports/benchmark_4_methods_results.json")

def set_cell_background(cell, hex_color):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=120, bottom=120, left=160, right=160):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = RGBColor(31, 78, 121)
    return p

def add_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(46, 117, 182)
    return p

def add_body_p(doc, text, bold_prefix="", italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = "Arial"
        r_pre.font.size = Pt(10)
        r_pre.font.bold = True
        r_pre.font.color.rgb = RGBColor(30, 30, 30)
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(10)
    r.font.italic = italic
    r.font.color.rgb = RGBColor(40, 45, 55)
    return p

def add_bullet_p(doc, text, bold_prefix=""):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = "Arial"
        r_pre.font.size = Pt(10)
        r_pre.font.bold = True
        r_pre.font.color.rgb = RGBColor(30, 30, 30)
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(10)
    r.font.color.rgb = RGBColor(40, 45, 55)
    return p

def add_callout(doc, text, title="GHI CHÚ QUAN TRỌNG", hex_border="2E75B6", hex_bg="F0F4F8"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, hex_bg)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="36" w:space="0" w:color="{hex_border}"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    run_t = p.add_run(f"📌 {title}: ")
    run_t.font.name = "Arial"
    run_t.font.bold = True
    run_t.font.size = Pt(10)
    run_t.font.color.rgb = RGBColor(31, 78, 121)
    
    run_b = p.add_run(text)
    run_b.font.name = "Arial"
    run_b.font.size = Pt(10)
    run_b.font.color.rgb = RGBColor(40, 45, 55)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

def add_code_block(doc, code_text):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F4F6F9")
    set_cell_margins(cell, top=100, bottom=100, left=150, right=150)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="5B9BD5"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(code_text)
    r.font.name = "Consolas"
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(35, 55, 75)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

def style_table_header(row, col_widths, hex_bg="1F4E79"):
    for idx, cell in enumerate(row.cells):
        set_cell_background(cell, hex_bg)
        set_cell_margins(cell, top=120, bottom=120, left=140, right=140)
        cell.width = col_widths[idx]
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.name = "Arial"
                r.font.bold = True
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

def style_table_row(row, col_widths, hex_bg="FFFFFF", align_first_left=True):
    for idx, cell in enumerate(row.cells):
        set_cell_background(cell, hex_bg)
        set_cell_margins(cell, top=80, bottom=80, left=140, right=140)
        cell.width = col_widths[idx]
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.15
            if idx == 0 and align_first_left:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for r in p.runs:
                r.font.name = "Arial"
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(40, 45, 55)

def build_report():
    doc = Document()
    
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Title
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(4)
    title_p.paragraph_format.space_after = Pt(4)
    run_title = title_p.add_run("BÁO CÁO PHÂN TÍCH & BENCHMARK ĐỐI ĐẦU 4 PHƯƠNG PHÁP")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(31, 78, 121)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(10)
    run_sub = sub_p.add_run("XÁC ĐỊNH THÔNG TIN VÀ TRUY XUẤT ĐƠN HÀNG TỪ CÂU HỎI KHÁCH HÀNG (MODULE 3)\n(Bản 1: Thuần Prompt | Bản 2: Luật/Normalize | Bản 3: Embedding | Bản 4: Hybrid)")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(11.5)
    run_sub.font.bold = True
    run_sub.font.color.rgb = RGBColor(46, 117, 182)

    # Metadata Table
    meta_tbl = doc.add_table(rows=4, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_widths = [Inches(2.0), Inches(4.7)]
    meta_data = [
        ("Dự án áp dụng:", "E-Commerce Support Copilot (Hệ thống AI Hỗ trợ CSKH)"),
        ("Phân hệ trọng tâm:", "Module 3: Advanced ReAct & Dynamic Order Matcher"),
        ("Tập dữ liệu kiểm thử:", "30 câu hỏi thực tế qua 6 nhóm nghiệp vụ trên 100 đơn hàng SQLite"),
        ("Thời gian thực hiện:", "Tháng 10/2026 - Phiên bản Kiến trúc v2.0 (Git Branch Tan)"),
    ]
    for r_idx, (k, v) in enumerate(meta_data):
        row = meta_tbl.rows[r_idx]
        bg = "F4F6F9" if r_idx % 2 == 0 else "FFFFFF"
        row.cells[0].paragraphs[0].add_run(k).font.bold = True
        row.cells[1].paragraphs[0].add_run(v)
        style_table_row(row, meta_widths, hex_bg=bg)
        row.cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(31, 78, 121)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    add_callout(
        doc,
        "Báo cáo này công bố kết quả kiểm thử thực nghiệm (Benchmark) độc lập của cả 4 phương pháp xác định đơn hàng: "
        "Bản 1 (Thuần Prompt LLM), Bản 2 (Luật / Regex), Bản 3 (Dense Embedding) và Bản 4 (Hybrid). Kết quả chỉ ra Bản 4 (Hybrid) "
        "đạt độ chính xác tuyệt đối 100% với độ trễ cực thấp 0.34 ms, trở thành giải pháp tối ưu nhất cho Production.",
        title="TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)"
    )

    # 1. ĐẶT VẤN ĐỀ
    add_heading_1(doc, "1. ĐẶT VẤN ĐỀ & BỐI CẢNH BÀI TOÁN XÁC ĐỊNH ĐƠN HÀNG")
    add_body_p(
        doc,
        "Trong thương mại điện tử, khách hàng gửi các câu hỏi đa dạng: từ việc cung cấp mã đơn chuẩn ('ORD-1001'), "
        "mã viết tắt có khoảng trắng ('check order ORD - 1003', 'đơn 1003'), số điện thoại ('0938.242.854'), mã vận đơn ('GIAO89254563'), "
        "cho đến việc khách hàng KHÔNG nhớ mã đơn mà chỉ nhớ tên món đồ ('Đơn mua Bộ drap ga giường cotton lụa của Bùi Thị An')."
    )
    add_body_p(
        doc,
        "Mục tiêu của Module 3 là: Xác định các thông tin đơn hàng từ input người dùng và trả về đúng bản ghi đơn hàng cần tìm trong CSDL.",
        bold_prefix="Nhiệm vụ cốt lõi: "
    )

    # 2. BỐN PHƯƠNG PHÁP TRIỂN KHAI
    add_heading_1(doc, "2. NGUYÊN LÝ HOẠT ĐỘNG CỦA 4 PHƯƠNG PHÁP")
    
    add_heading_2(doc, "2.1. Bản 1: Thuần Prompt (LLM Zero-Shot Entity Extraction)")
    add_bullet_p(doc, "Gửi trực tiếp câu hỏi người dùng kèm System Prompt sang mô hình Google Gemini Flash Lite để bóc tách JSON cấu trúc ({'order_id', 'phone', 'tracking_code', 'product_keyword', 'customer_name'}).", bold_prefix="Cơ chế: ")
    add_bullet_p(doc, "Rất thông minh trong đọc hiểu ngữ cảnh tự nhiên, nhưng bị giới hạn bởi độ trễ mạng Internet (~1.4s) và chi phí Token API.", bold_prefix="Đặc trưng: ")

    add_heading_2(doc, "2.2. Bản 2: Luật / Normalize (Rule-based Regex & Normalization)")
    add_bullet_p(doc, "Tiền xử lý chuỗi (masking SĐT, chuẩn hóa dấu câu) và quét qua các biểu thức chính quy (RE_PHONE, RE_EXTENDED_ORDER, RE_TRACKING).", bold_prefix="Cơ chế: ")
    add_bullet_p(doc, "Tốc độ siêu tốc (0.05 ms), 0 VNĐ, chạy offline 100%. Tuy nhiên hoàn toàn bất lực khi khách chỉ nhớ tên sản phẩm mà không cung cấp mã số.", bold_prefix="Đặc trưng: ")

    add_heading_2(doc, "2.3. Bản 3: Embedding (Dense Vector Semantic Matching)")
    add_bullet_p(doc, "Vector hóa toàn bộ 100 đơn hàng thành các tài liệu ngữ nghĩa đa chiều chứa: Mã đơn, tên khách, SĐT, mã vận đơn, và tên các sản phẩm trong đơn. Khi có query, tính Cosine Similarity để tìm ra đơn hàng có độ tương đồng ngữ nghĩa cao nhất.", bold_prefix="Cơ chế: ")
    add_bullet_p(doc, "Rất xuất sắc khi khách hỏi theo tên sản phẩm ('Đơn mua Bộ drap ga giường'), nhưng yếu khi tìm các mã vận đơn ngẫu nhiên (GIAO89254563) vì chuỗi vô nghĩa này không có ngữ nghĩa trong từ điển.", bold_prefix="Đặc trưng: ")

    add_heading_2(doc, "2.4. Bản 4: Hybrid (Keyword/Rule + Dense Embedding)")
    add_bullet_p(doc, "Mô hình kết hợp 2 tầng (Two-Tier Cascade): Ưu tiên quét luật Regex bắt các mã chuẩn xác 100% (< 0.1ms). Nếu không có mã số, tự động kích hoạt Tầng Embedding để tìm kiếm ngữ nghĩa theo tên sản phẩm và tên khách hàng.", bold_prefix="Cơ chế: ")
    add_bullet_p(doc, "Dung hòa hoàn hảo: Vừa có tốc độ tức thì và độ chính xác của Rule, vừa có trí thông minh ngữ nghĩa của Embedding.", bold_prefix="Đặc trưng: ")

    # 3. KẾT QUẢ BENCHMARK
    add_heading_1(doc, "3. BẢNG TỔNG HỢP KẾT QUẢ BENCHMARK ĐỐI ĐẦU TOÀN DIỆN")
    add_body_p(
        doc,
        "Dưới đây là kết quả kiểm thử thực nghiệm trên 30 câu hỏi thực tế đại diện cho 6 nhóm tình huống nghiệp vụ trên tập 100 đơn hàng:"
    )

    comp_tbl = doc.add_table(rows=5, cols=5)
    comp_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w = [Inches(2.2), Inches(1.2), Inches(1.2), Inches(1.1), Inches(1.1)]
    
    headers = ["Phương Pháp Đánh Giá", "Độ Chính Xác", "Mean Latency", "P95 Latency", "Chi Phí API"]
    for idx, name in enumerate(headers):
        comp_tbl.rows[0].cells[idx].paragraphs[0].add_run(name)
    style_table_header(comp_tbl.rows[0], col_w)

    data_summary = [
        ("Bản 1: Thuần Prompt (LLM Gemini)", "80.0% (24/30)", "1,395.44 ms", "4,233.07 ms", "Phí Token API"),
        ("Bản 2: Luật / Normalize (Regex)", "83.3% (25/30)", "0.05 ms ⚡", "0.12 ms", "0 VNĐ (Offline)"),
        ("Bản 3: Dense Embedding", "76.7% (23/30)", "1.36 ms", "3.22 ms", "0 VNĐ (Offline)"),
        ("Bản 4: Hybrid (Keyword + Embedding)", "100.0% (30/30) 🏆", "0.34 ms ⚡", "1.36 ms", "0 VNĐ (Offline)"),
    ]

    for r_idx, r_vals in enumerate(data_summary):
        row = comp_tbl.rows[r_idx + 1]
        bg = "EBF1F5" if r_idx == 3 else ("F9FBFC" if r_idx % 2 == 0 else "FFFFFF")
        for c_idx, val in enumerate(r_vals):
            p = row.cells[c_idx].paragraphs[0]
            r = p.add_run(val)
            if r_idx == 3:
                r.font.bold = True
                if c_idx == 1:
                    r.font.color.rgb = RGBColor(192, 0, 0)
        style_table_row(row, col_w, hex_bg=bg)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # 4. CHI TIẾT THEO TỪNG NHÓM
    add_heading_1(doc, "4. PHÂN TÍCH ĐỘ CHÍNH XÁC THEO 6 NHÓM NGHIỆP VỤ")

    cat_tbl = doc.add_table(rows=7, cols=5)
    cat_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cat_w = [Inches(2.4), Inches(1.1), Inches(1.1), Inches(1.1), Inches(1.1)]
    
    cat_headers = ["Nhóm Kịch Bản Thử Nghiệm", "Bản 1: Prompt", "Bản 2: Rule", "Bản 3: Embed", "Bản 4: Hybrid"]
    for idx, name in enumerate(cat_headers):
        cat_tbl.rows[0].cells[idx].paragraphs[0].add_run(name)
    style_table_header(cat_tbl.rows[0], cat_w, hex_bg="2E75B6")

    cat_data = [
        ("1. Mã đơn chuẩn (ORD-1001...)", "5/5 (100%)", "5/5 (100%)", "5/5 (100%)", "5/5 (100%) 🏆"),
        ("2. Viết tắt / Cách chữ (ORD - 1003, #1002)", "5/5 (100%)", "5/5 (100%)", "5/5 (100%)", "5/5 (100%) 🏆"),
        ("3. Tra cứu bằng SĐT (0938.242.854)", "5/5 (100%)", "5/5 (100%)", "3/5 (60%)", "5/5 (100%) 🏆"),
        ("4. Tra bằng Mã vận đơn (GIAO89254563)", "3/5 (60%)", "5/5 (100%)", "0/5 (0%)", "5/5 (100%) 🏆"),
        ("5. Tra theo Tên sản phẩm / Khách hàng", "1/5 (20%)", "0/5 (0%) ❌", "5/5 (100%) 🏆", "5/5 (100%) 🏆"),
        ("6. Câu hỏi chung ngoài luồng (Negative)", "5/5 (100%)", "5/5 (100%)", "5/5 (100%)", "5/5 (100%) 🏆"),
    ]

    for r_idx, r_vals in enumerate(cat_data):
        row = cat_tbl.rows[r_idx + 1]
        bg = "F9FBFC" if r_idx % 2 == 0 else "FFFFFF"
        for c_idx, val in enumerate(r_vals):
            p = row.cells[c_idx].paragraphs[0]
            r = p.add_run(val)
            if c_idx == 4:
                r.font.bold = True
                r.font.color.rgb = RGBColor(31, 78, 121)
        style_table_row(row, cat_w, hex_bg=bg)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    add_heading_2(doc, "4.1. Nhận xét then chốt từ dữ liệu thực nghiệm")
    add_bullet_p(doc, "Khi khách hỏi: 'Đơn mua Bộ drap ga giường cotton lụa của Bùi Thị An', Bản 2 (Rule) hoàn toàn thất bại (0%) vì không có mã đơn. Ngược lại, Bản 3 (Embedding) và Bản 4 (Hybrid) đạt 100% nhờ khả năng khớp ngữ nghĩa tên sản phẩm.", bold_prefix="Trường hợp khách không nhớ mã đơn: ")
    add_bullet_p(doc, "Các chuỗi vận đơn như 'GIAO89254563' không có ý nghĩa từ vựng nên Bản 3 (Embedding) đạt 0%. Lúc này, Bản 2 (Rule) lại phát huy sức mạnh bắt đúng tiền tố bưu cục đạt 100%.", bold_prefix="Trường hợp mã vận đơn bưu cục: ")
    add_bullet_p(doc, "Bản 4 (Hybrid) kết hợp cả hai cơ chế, bù trừ hoàn hảo các lỗ hổng của từng bên, đem lại độ chính xác tuyệt đối 100% trên toàn bộ các ca thử nghiệm.", bold_prefix="Sự vượt trội của Hybrid: ")

    # 5. KẾT LUẬN
    add_heading_1(doc, "5. KẾT LUẬN & ĐỀ XUẤT KIẾN TRÚC CHO PRODUCTION")
    add_body_p(
        doc,
        "1. Bản 4 (Hybrid: Keyword + Embedding) là giải pháp tối ưu toàn diện nhất cho Module 3, vừa đạt độ chính xác 100%, vừa có tốc độ phản hồi cực nhanh (0.34ms) và không tốn chi phí vận hành API."
    )
    add_body_p(
        doc,
        "2. Toàn bộ 4 phương pháp đã được đóng gói thành các lớp chuẩn hóa trong file services/gateway/src/order_matchers.py trên Git Branch Tan."
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUTPUT_FILE))
    print(f"Updated Word report saved successfully to: {OUTPUT_FILE.resolve()}")

if __name__ == "__main__":
    build_report()

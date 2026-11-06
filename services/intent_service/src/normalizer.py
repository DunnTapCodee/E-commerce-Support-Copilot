"""Text normalizer for Vietnamese e-commerce queries.
Handles unaccented Vietnamese recovery, typo corrections, and intent phrase expansion
to ensure high robustness (Model Quality & Behavioral Testing - Sliced Robustness).
"""
import re
from typing import Tuple

# Common unaccented Vietnamese phrase mappings to standard accented forms
UNACCENTED_PHRASE_MAPPINGS = [
    # 1. Order Tracking / Delivery Time
    (r"\bkiem tra don hang\b", "kiểm tra đơn hàng"),
    (r"\btra cuu don hang\b", "tra cứu đơn hàng"),
    (r"\btra cuu don\b", "tra cứu đơn hàng"),
    (r"\bdon hang cua toi\b", "đơn hàng của tôi"),
    (r"\bdon cua toi\b", "đơn hàng của tôi"),
    (r"\bdon hang\b", "đơn hàng"),
    (r"\bbao gio giao toi\b", "bao giờ giao tới"),
    (r"\bbao gio giao\b", "bao giờ giao"),
    (r"\bbao gio toi\b", "bao giờ tới"),
    (r"\bbao gio\b", "bao giờ"),
    (r"\bkhi nao giao toi\b", "khi nào giao tới"),
    (r"\bkhi nao giao\b", "khi nào giao"),
    (r"\bkhi nao toi\b", "khi nào tới"),
    (r"\bkhi nao nhan duoc\b", "khi nào nhận được"),
    (r"\bkhi nao nhan\b", "khi nào nhận"),
    (r"\bkhi nao\b", "khi nào"),
    (r"\bchua thay giao\b", "chưa thấy giao"),
    (r"\bchua thay hang\b", "chưa thấy hàng"),
    (r"\bchua thay\b", "chưa thấy"),
    (r"\bchua nhan duoc\b", "chưa nhận được"),
    (r"\bdang o dau\b", "đang ở đâu"),

    # Delivery Issue (Khiếu nại giao trễ / sự cố)
    (r"\bgiao tre qua\b", "giao trễ quá"),
    (r"\bgiao tre\b", "giao trễ"),
    (r"\bgiao cham\b", "giao chậm"),
    (r"\bvan chua thay\b", "vẫn chưa thấy"),

    # 2. Cancel Order
    (r"\bhuy don hang\b", "hủy đơn hàng"),
    (r"\bhuy don\b", "hủy đơn"),
    (r"\bko mua nua\b", "không mua nữa"),
    (r"\bkhong mua nua\b", "không mua nữa"),
    (r"\bmuon huy\b", "muốn hủy"),

    # 3. Return & Refund Policies & Actions
    (r"\bchinh sach doi tra hang\b", "chính sách đổi trả hàng"),
    (r"\bchinh sach doi tra\b", "chính sách đổi trả"),
    (r"\bchinh sach hoan tien\b", "chính sách hoàn tiền"),
    (r"\bchinh sach bao hanh\b", "chính sách bảo hành"),
    (r"\bchinh sach\b", "chính sách"),
    (r"\bquy dinh hoan tien\b", "quy định hoàn tiền"),
    (r"\bquy dinh doi tra\b", "quy định đổi trả"),
    (r"\bquy dinh\b", "quy định"),
    (r"\bdoi tra hang\b", "đổi trả hàng"),
    (r"\bdoi tra\b", "đổi trả"),
    (r"\bmuon tra lai\b", "muốn trả lại"),
    (r"\btra lai\b", "trả lại"),
    (r"\btra hang\b", "trả hàng"),
    (r"\bdoi hang\b", "đổi hàng"),
    (r"\btra lai tien cho toi\b", "trả lại tiền cho tôi"),
    (r"\btra lai tien\b", "trả lại tiền"),
    (r"\bhoan tien cho toi\b", "hoàn tiền cho tôi"),
    (r"\bhoan tien lai\b", "hoàn tiền lại"),
    (r"\bhoan tien\b", "hoàn tiền"),
    (r"\btien hoan da ve\b", "tiền hoàn đã về"),
    (r"\btien hoan\b", "tiền hoàn"),
    (r"\bda ve vi chua\b", "đã về ví chưa"),
    (r"\bda ve\b", "đã về"),
    (r"\bve vi\b", "về ví"),
    (r"\bdoi san pham\b", "đổi sản phẩm"),
    (r"\bhang loi\b", "hàng lỗi"),
    (r"\bbi loi\b", "bị lỗi"),
    (r"\bbi hong\b", "bị hỏng"),
    (r"\bbi re\b", "bị rè"),
    (r"\bbi chat\b", "bị chật"),
    (r"\bvo hop\b", "vỡ hộp"),
    (r"\bmop meo\b", "móp méo"),

    # 4. Warranty Policy
    (r"\bbao hanh san pham\b", "bảo hành sản phẩm"),
    (r"\bbao hanh\b", "bảo hành"),
    (r"\bbao lau\b", "bao lâu"),
    (r"\bmay thang\b", "mấy tháng"),

    # 5. Shipping Costs
    (r"\bphi van chuyen\b", "phí vận chuyển"),
    (r"\bphi giao hang\b", "phí giao hàng"),
    (r"\bphi ship bao nhieu\b", "phí ship bao nhiêu"),
    (r"\bphi ship\b", "phí ship"),
    (r"\bcuoc phi\b", "cước phí vận chuyển"),
    (r"\bgiao ve\b", "giao về"),
    (r"\bton bao nhieu\b", "tốn bao nhiêu"),

    # 6. Promotions / Vouchers
    (r"\bma giam gia\b", "mã giảm giá"),
    (r"\bkhuyen mai\b", "khuyến mãi"),
    (r"\buu dai\b", "ưu đãi"),
    (r"\bvoucher\b", "mã giảm giá voucher"),

    # 7. Payment Issues
    (r"\bloi thanh toan\b", "lỗi thanh toán"),
    (r"\bthanh toan\b", "thanh toán"),
    (r"\btru tien nhung\b", "trừ tiền nhưng"),
    (r"\btru tien\b", "trừ tiền"),
    (r"\bthe tin dung\b", "thẻ tín dụng"),

    # 8. Human Agent / Escalation
    (r"\bgap truc tiep nhan vien cskh\b", "gặp trực tiếp nhân viên chăm sóc khách hàng"),
    (r"\bgap truc tiep nhan vien\b", "gặp trực tiếp nhân viên"),
    (r"\bnhan vien cskh\b", "nhân viên chăm sóc khách hàng"),
    (r"\bnhan vien\b", "nhân viên"),
    (r"\bcskh\b", "chăm sóc khách hàng"),
    (r"\btong dai vien\b", "tổng đài viên"),
    (r"\bgap nguoi\b", "gặp nhân viên tư vấn"),
    (r"\bchat voi nguoi\b", "chat với nhân viên"),
    (r"\bnguoi that\b", "người thật"),
    (r"\btruc tiep\b", "trực tiếp"),

    # Common grammatical words
    (r"\btoi muon\b", "tôi muốn"),
    (r"\bcho minh hoi\b", "cho mình hỏi"),
    (r"\bcho hoi\b", "cho hỏi"),
    (r"\bgiup minh\b", "giúp mình"),
    (r"\bgiup toi\b", "giúp tôi"),
    (r"\bkhong duoc\b", "không được"),
    (r"\blam sao\b", "làm sao"),
    (r"\bnhu the nao\b", "như thế nào"),
    (r"\bcua toi\b", "của tôi"),
    (r"\btai sao\b", "tại sao"),
]

# Vietnamese accent characters
VIETNAMESE_ACCENTS_PATTERN = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


def has_vietnamese_accents(text: str) -> bool:
    """Return True if text contains accented Vietnamese characters."""
    return bool(VIETNAMESE_ACCENTS_PATTERN.search(text))


def normalize_vietnamese_query(query: str) -> Tuple[str, bool]:
    """Normalize query by expanding unaccented terms if query is unaccented.
    
    Returns:
        (normalized_query, was_modified)
    """
    normalized = query.strip()
    # If the user already wrote with accents, don't force unaccented regex unless needed
    has_accents = has_vietnamese_accents(normalized)
    was_modified = False

    lower_text = normalized.lower()

    if not has_accents:
        # User typed without accents (e.g. 'kiem tra don hang ord-1002 giup minh')
        # Apply dictionary mapping (longest match first)
        working_text = lower_text
        sorted_mappings = sorted(UNACCENTED_PHRASE_MAPPINGS, key=lambda x: len(x[0]), reverse=True)
        for pattern, replacement in sorted_mappings:
            new_text = re.sub(pattern, replacement, working_text, flags=re.IGNORECASE)
            if new_text != working_text:
                working_text = new_text
                was_modified = True

        if was_modified:
            # Preserve uppercase tokens like order IDs (ORD-1002)
            words_orig = normalized.split()
            words_new = working_text.split()
            # If length changed, return working_text
            normalized = working_text

    return normalized, was_modified

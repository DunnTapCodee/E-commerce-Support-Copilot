"""Offline Heuristic Policy Metadata Extraction Fallback.

Isolated from `policy_filter.py` so deterministic category/policy_type/tag keyword rules
only run when live LLM extraction is disabled, unconfigured, or unreachable.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from contracts.schemas import PolicyFilterResult, RetrievedDocument
from services.document_service.src.policy_manager import calculate_active_status, policy_manager

_CATEGORY_SPECS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("return_refund", ("đổi trả", "hoàn trả", "trả hàng", "đổi hàng")),
    ("refund", ("hoàn tiền", "bồi hoàn", "refund")),
    ("shipping", ("vận chuyển", "giao hàng", "ship", "phí ship", "hỏa tốc", "tiết kiệm")),
    ("warranty", ("bảo hành", "sửa chữa", "linh kiện", "bảo trì")),
    ("payment", ("thanh toán", "cod", "thẻ tín dụng", "momo", "zalopay", "ngân hàng")),
    ("promotions", ("khuyến mãi", "voucher", "mã giảm giá", "ưu đãi", "giảm giá", "hoàn xu")),
    ("account", ("tài khoản", "bảo mật", "đăng nhập", "mật khẩu", "quên mật khẩu")),
)

_TAG_KEYWORDS = (
    "đổi trả", "hoàn tiền", "bảo hành", "vận chuyển", "freeship", "voucher",
    "thanh toán", "cod", "hỏa tốc", "chính hãng", "7 ngày", "14 ngày", "30 ngày",
)


def generate_unique_doc_id(existing_ids: List[str], prefix: str = "POL") -> str:
    """Generate an unused deterministic-prefix POL-* identifier."""
    while True:
        candidate = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        if candidate not in existing_ids:
            return candidate


def detect_category_offline(text: str) -> str:
    """Heuristic category classification for offline fallback."""
    low = text.lower()
    for category, cues in _CATEGORY_SPECS:
        if any(w in low for w in cues):
            return category
    return "support"


def detect_policy_type_offline(text: str) -> str:
    """Heuristic policy lifecycle classification for offline fallback."""
    low = text.lower()
    if any(w in low for w in ("thay thế", "hết hạn sử dụng", "bị hủy bỏ", "bản cũ", "superseded")):
        return "superseded"
    if any(w in low for w in ("tạm thời", "chương trình", "chiến dịch", "áp dụng từ ngày", "đến hết ngày", "khuyến mãi tết", "flash sale")):
        return "temporary"
    return "permanent"


def extract_dates_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Heuristic extraction of effective and expiration dates."""
    date_patterns = (
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}-\d{1,2}-\d{4})",
    )
    found_dates: List[Tuple[int, str]] = []
    for pat in date_patterns:
        for m in re.finditer(pat, text):
            d_str = m.group(1)
            try:
                if "/" in d_str:
                    parts = d_str.split("/")
                    dt = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
                elif "-" in d_str and len(d_str.split("-")[0]) == 2:
                    parts = d_str.split("-")
                    dt = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
                else:
                    parts = d_str.split("-")
                    dt = datetime(int(parts[0]), int(parts[1]), int(parts[2])).date()
                found_dates.append((m.start(), dt.strftime("%Y-%m-%d")))
            except Exception:
                pass

    found_dates.sort(key=lambda item: item[0])
    eff_date = found_dates[0][1] if len(found_dates) >= 1 else None
    exp_date = found_dates[1][1] if len(found_dates) >= 2 else None
    return eff_date, exp_date


def extract_tags_offline(text: str) -> List[str]:
    """Heuristic keyword tag extraction for offline fallback."""
    low = text.lower()
    return [kw for kw in _TAG_KEYWORDS if kw in low][:5]


def heuristic_fallback_extract(raw_text: str, suggested_category: Optional[str] = None) -> PolicyFilterResult:
    """Offline heuristic policy extraction when LLM is disabled or unreachable."""
    lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
    title = lines[0] if lines else "Chính sách mới"
    if len(title) > 100:
        title = title[:97] + "..."

    content = raw_text.strip()
    category = suggested_category or detect_category_offline(raw_text)
    policy_type = detect_policy_type_offline(raw_text)
    eff_date, exp_date = extract_dates_from_text(raw_text)

    existing_docs = policy_manager.load_policies()
    existing_ids = [d.doc_id for d in existing_docs]
    doc_id = generate_unique_doc_id(existing_ids, prefix="POL")

    temp_dict = {
        "doc_id": doc_id,
        "policy_type": policy_type,
        "effective_date": eff_date,
        "expiration_date": exp_date,
    }
    is_active, status_reason = calculate_active_status(temp_dict)

    doc = RetrievedDocument(
        doc_id=doc_id,
        category=category,
        title=title,
        content=content,
        version="1.0",
        is_active=is_active,
        policy_type=policy_type,
        effective_date=eff_date,
        expiration_date=exp_date,
        tags=extract_tags_offline(raw_text),
    )

    warnings = [
        "Trích xuất qua bộ phân tích Heuristic Rule (chưa sử dụng LLM).",
        f"Trạng thái tự động: {'Active' if is_active else 'Inactive'} ({status_reason})",
    ]
    if policy_type == "temporary" and not exp_date:
        warnings.append("Cảnh báo: Chính sách tạm thời cần có ngày hết hạn cụ thể.")

    return PolicyFilterResult(
        extracted_policy=doc,
        warnings=warnings,
        confidence_score=0.70,
    )

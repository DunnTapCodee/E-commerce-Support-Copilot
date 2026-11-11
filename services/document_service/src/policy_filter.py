"""Policy extraction: LLM-first (OpenAI-compatible / Gemini) with Heuristic Fallback.

Extracts structured policy fields from raw staff documents:
  - doc_id: Generated or extracted
  - category: return_refund, shipping, warranty, payment, promotions, account, support
  - title: Extracted title
  - content: Structured content / conditions
  - version: Document version
  - policy_type: permanent | temporary | superseded
  - effective_date: ISO YYYY-MM-DD
  - expiration_date: ISO YYYY-MM-DD
  - tags: Extracted keywords
  - is_active: Dynamically computed via calculate_active_status()
"""
import json
import os
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import httpx

from contracts.schemas import (
    PolicyFilterResult,
    RawPolicyFilterRequest,
    RetrievedDocument,
)
from services.document_service.src.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from services.document_service.src.policy_manager import (
    calculate_active_status,
    policy_manager,
)


def _generate_unique_doc_id(existing_ids: List[str], prefix: str = "POL") -> str:
    while True:
        candidate = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        if candidate not in existing_ids:
            return candidate


def _detect_category(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ["đổi trả", "hoàn trả", "trả hàng", "đổi hàng"]):
        return "return_refund"
    if any(w in low for w in ["hoàn tiền", "bồi hoàn", "refund"]):
        return "refund"
    if any(w in low for w in ["vận chuyển", "giao hàng", "ship", "phí ship", "hỏa tốc", "tiết kiệm"]):
        return "shipping"
    if any(w in low for w in ["bảo hành", "sửa chữa", "linh kiện", "bảo trì"]):
        return "warranty"
    if any(w in low for w in ["thanh toán", "cod", "thẻ tín dụng", "momo", "zalopay", "ngân hàng"]):
        return "payment"
    if any(w in low for w in ["khuyến mãi", "voucher", "mã giảm giá", "ưu đãi", "giảm giá", "hoàn xu"]):
        return "promotions"
    if any(w in low for w in ["tài khoản", "bảo mật", "đăng nhập", "mật khẩu", "quên mật khẩu"]):
        return "account"
    return "support"


def _detect_policy_type(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ["thay thế", "hết hạn sử dụng", "bị hủy bỏ", "bản cũ", "superseded"]):
        return "superseded"
    if any(w in low for w in ["tạm thời", "chương trình", "chiến dịch", "áp dụng từ ngày", "đến hết ngày", "khuyến mãi tết", "flash sale"]):
        return "temporary"
    return "permanent"


def _extract_dates_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Heuristic extraction of effective and expiration dates."""
    date_patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}-\d{1,2}-\d{4})",
    ]
    found_dates = []
    for pat in date_patterns:
        for m in re.finditer(pat, text):
            d_str = m.group(1)
            # normalize to YYYY-MM-DD
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
                found_dates.append(dt.strftime("%Y-%m-%d"))
            except Exception:
                pass

    eff_date = found_dates[0] if len(found_dates) >= 1 else None
    exp_date = found_dates[1] if len(found_dates) >= 2 else None
    return eff_date, exp_date


def _extract_tags(text: str) -> List[str]:
    keywords = [
        "đổi trả", "hoàn tiền", "bảo hành", "vận chuyển", "freeship", "voucher",
        "thanh toán", "cod", "hỏa tốc", "chính hãng", "7 ngày", "14 ngày", "30 ngày"
    ]
    low = text.lower()
    tags = [kw for kw in keywords if kw in low]
    return tags[:5]


def _heuristic_fallback_extract(raw_text: str, suggested_category: Optional[str] = None) -> PolicyFilterResult:
    """Heuristic extraction using regex and rule matching."""
    lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
    title = lines[0] if lines else "Chính sách mới"
    if len(title) > 100:
        title = title[:97] + "..."

    content = raw_text.strip()
    category = suggested_category or _detect_category(raw_text)
    policy_type = _detect_policy_type(raw_text)
    eff_date, exp_date = _extract_dates_from_text(raw_text)

    existing_docs = policy_manager.load_policies()
    existing_ids = [d.doc_id for d in existing_docs]
    doc_id = _generate_unique_doc_id(existing_ids, prefix="POL")

    # Dynamic is_active calculation
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
        tags=_extract_tags(raw_text),
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


async def _llm_extract_openai(raw_text: str, suggested_category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Extract fields using OpenAI-compatible API."""
    if not OPENAI_API_KEY:
        return None

    system_prompt = """Bạn là trợ lý AI chuyên phân tích và chuẩn hóa văn bản chính sách thương mại điện tử.
Hãy đọc kỹ văn bản chính sách thô của nhân viên và trích xuất thành định dạng JSON chuẩn:
{
  "title": "Tiêu đề ngắn gọn, rõ ràng của chính sách",
  "category": "return_refund | shipping | warranty | payment | promotions | account | support",
  "policy_type": "permanent | temporary | superseded",
  "effective_date": "YYYY-MM-DD hoặc null nếu không ghi rõ",
  "expiration_date": "YYYY-MM-DD hoặc null nếu chính sách vĩnh viễn",
  "content": "Nội dung chuẩn hóa đầy đủ của chính sách, trình bày rõ ràng có gạch đầu dòng",
  "version": "1.0",
  "tags": ["tag1", "tag2", "tag3"]
}
Chỉ trả về duy nhất chuỗi JSON hợp lệ, không kèm markdown hoặc giải thích thêm."""

    prompt = f"Gợi ý danh mục: {suggested_category or 'Không có'}\n\nVăn bản chính sách thô:\n{raw_text}"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                return json.loads(content.strip())
            try:
                error_message = resp.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                error_message = ""
            print(
                f"[PolicyFilter] OpenAI extraction failed: HTTP {resp.status_code} "
                f"for model {OPENAI_MODEL}: {error_message[:200]}"
            )
    except Exception as exc:
        print(f"[PolicyFilter] OpenAI extraction failed: {exc}")
    return None


async def _llm_extract_gemini(raw_text: str, api_key: str, suggested_category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Extract fields using Gemini API."""
    if not api_key:
        return None

    prompt = f"""Bạn là trợ lý AI chuẩn hóa chính sách thương mại điện tử.
Trích xuất thông tin từ văn bản thô sau thành duy nhất 1 JSON object:
{{
  "title": "Tiêu đề chính sách",
  "category": "return_refund | shipping | warranty | payment | promotions | account | support",
  "policy_type": "permanent | temporary | superseded",
  "effective_date": "YYYY-MM-DD hoặc null",
  "expiration_date": "YYYY-MM-DD hoặc null",
  "content": "Nội dung chuẩn hóa",
  "version": "1.0",
  "tags": ["tag1", "tag2"]
}}

Văn bản thô:
{raw_text}
"""

    models = [GEMINI_MODEL, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    text_out = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text_out.startswith("```json"):
                        text_out = text_out[7:]
                    if text_out.endswith("```"):
                        text_out = text_out[:-3]
                    return json.loads(text_out.strip())
            except Exception:
                continue
    return None


async def filter_raw_policy(request: RawPolicyFilterRequest) -> PolicyFilterResult:
    """Cascade Policy Extraction: OpenAI -> Gemini -> Heuristic."""
    raw_text = request.raw_text.strip()
    if not raw_text:
        raise ValueError("Văn bản chính sách không được để trống.")

    extracted_dict = None
    extraction_source = "heuristic"

    # 1. Try OpenAI-compatible LLM
    try:
        extracted_dict = await _llm_extract_openai(raw_text, request.suggested_category)
        if extracted_dict:
            extraction_source = f"openai ({OPENAI_MODEL})"
    except Exception:
        pass

    # 2. Try Gemini LLM
    if not extracted_dict:
        gemini_key = request.gemini_api_key or GEMINI_API_KEY
        if gemini_key:
            try:
                extracted_dict = await _llm_extract_gemini(raw_text, gemini_key, request.suggested_category)
                if extracted_dict:
                    extraction_source = "gemini"
            except Exception:
                pass

    # 3. Fallback to Heuristic
    if not extracted_dict:
        return _heuristic_fallback_extract(raw_text, request.suggested_category)

    # Process Extracted Dict
    existing_docs = policy_manager.load_policies()
    existing_ids = [d.doc_id for d in existing_docs]
    doc_id = _generate_unique_doc_id(existing_ids, prefix="POL")

    # Automated is_active calculation based on dates & type
    extracted_dict["doc_id"] = doc_id
    is_active, status_reason = calculate_active_status(extracted_dict)
    extracted_dict["is_active"] = is_active

    doc = RetrievedDocument(
        doc_id=doc_id,
        category=extracted_dict.get("category") or request.suggested_category or _detect_category(raw_text),
        title=extracted_dict.get("title") or "Chính sách mới",
        content=extracted_dict.get("content") or raw_text,
        version=str(extracted_dict.get("version") or "1.0"),
        is_active=is_active,
        policy_type=extracted_dict.get("policy_type") or "permanent",
        effective_date=extracted_dict.get("effective_date"),
        expiration_date=extracted_dict.get("expiration_date"),
        tags=extracted_dict.get("tags") or _extract_tags(raw_text),
    )

    warnings = [
        f"Trích xuất thành công bằng mô hình AI ({extraction_source}).",
        f"Trạng thái tự động: {'Active' if is_active else 'Inactive'} ({status_reason})",
    ]
    if doc.policy_type == "temporary" and not doc.expiration_date:
        warnings.append("Cảnh báo: Chính sách tạm thời cần có ngày hết hạn rõ ràng.")

    return PolicyFilterResult(
        extracted_policy=doc,
        warnings=warnings,
        confidence_score=0.92,
    )


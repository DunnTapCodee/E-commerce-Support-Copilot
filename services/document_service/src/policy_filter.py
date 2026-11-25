"""Policy extraction: OpenAI LLM Primary with Offline Heuristic Fallback (`offline_policy_fallback.py`)."""
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from contracts.llm_failover import call_chat_completion_with_failover
from contracts.schemas import (
    PolicyFilterResult,
    RawPolicyFilterRequest,
    RetrievedDocument,
)
from services.document_service.src.config import (
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from services.document_service.src.offline_policy_fallback import (
    detect_category_offline as _detect_category,
    detect_policy_type_offline as _detect_policy_type,
    extract_dates_from_text as _extract_dates_from_text,
    extract_tags_offline as _extract_tags,
    generate_unique_doc_id as _generate_unique_doc_id,
    heuristic_fallback_extract as _heuristic_fallback_extract,
)
from services.document_service.src.policy_manager import (
    calculate_active_status,
    policy_manager,
)


def extract_text_from_file_bytes(filename: str, file_bytes: bytes) -> str:
    """Safely extract plain text from uploaded files (docx, txt, json, md, csv, etc.)."""
    fname = filename.lower()

    # 1. Word .docx format (ZIP archive containing word/document.xml)
    if fname.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                if "word/document.xml" in zf.namelist():
                    xml_content = zf.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    paragraphs = []
                    for node in tree.iter():
                        if node.tag.endswith("}p"):
                            p_texts = [child.text for child in node.iter() if child.tag.endswith("}t") and child.text]
                            if p_texts:
                                paragraphs.append("".join(p_texts))
                    if paragraphs:
                        return "\n\n".join(paragraphs).strip()
                    texts = [node.text for node in tree.iter() if node.tag.endswith("}t") and node.text]
                    return "\n".join(texts).strip()
        except Exception as exc:
            print(f"[DocumentParser] Error parsing docx: {exc}")

    # 2. Text / Markdown / CSV / JSON
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            decoded = file_bytes.decode(enc).strip()
            if decoded:
                return decoded
        except Exception:
            continue

    return ""


async def _llm_extract_openai_items(raw_text: str, suggested_category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract 1 or multiple structured policy items from text using OpenAI-compatible LLM.

    Always returns a list of policy dicts (may have 1 or more items).
    """
    system_prompt = """Bạn là trợ lý AI chuyên phân tích và chuẩn hóa văn bản chính sách thương mại điện tử.
Người dùng sẽ cung cấp một văn bản hoặc tài liệu (có thể chứa 1 hoặc NHIỀU chính sách khác nhau).
Hãy phát hiện và trích xuất TẤT CẢ các chính sách có trong văn bản thành một danh sách JSON (JSON Array):
[
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
]
Quy tắc:
1. Nếu văn bản chỉ chứa 1 chính sách, hãy trả về mảng có đúng 1 phần tử.
2. Nếu văn bản chứa NHIỀU chính sách khác nhau, hãy bóc tách riêng biệt từng chính sách thành từng phần tử trong mảng.
3. Chỉ trả về duy nhất chuỗi JSON hợp lệ (bắt đầu bằng [ và kết thúc bằng ]), không kèm markdown hoặc giải thích thêm."""

    prompt = f"Gợi ý danh mục: {suggested_category or 'Không có'}\n\nVăn bản tài liệu thô:\n{raw_text}"

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    try:
        data = await call_chat_completion_with_failover(
            payload=payload,
            base_url=OPENAI_BASE_URL,
            timeout=35.0,
        )
        if data and "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"].strip()
            # Clean possible markdown wrap
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            parsed = json.loads(content.strip())
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        print(f"[PolicyFilter] LLM extraction returned no choices for model {OPENAI_MODEL}")
    except Exception as exc:
        print(f"[PolicyFilter] LLM extraction error: {exc}")
    return []


async def _llm_extract_openai(raw_text: str, suggested_category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Extract single policy dict (backward compatibility)."""
    items = await _llm_extract_openai_items(raw_text, suggested_category)
    return items[0] if items else None


async def filter_bulk_raw_policy(raw_text: str, suggested_category: Optional[str] = None) -> List[PolicyFilterResult]:
    """Policy Extraction: OpenAI LLM extracting multiple policies → Heuristic fallback.

    Returns a list of PolicyFilterResult items.
    """
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("Văn bản chính sách không được để trống.")

    existing_docs = policy_manager.load_policies()
    existing_ids = [d.doc_id for d in existing_docs]

    extracted_items = []
    extraction_source = f"openai ({OPENAI_MODEL})"

    try:
        extracted_items = await _llm_extract_openai_items(raw_text, suggested_category)
    except Exception:
        pass

    results: List[PolicyFilterResult] = []

    if extracted_items:
        for idx, item_dict in enumerate(extracted_items):
            doc_id = _generate_unique_doc_id(existing_ids, prefix="POL")
            existing_ids.append(doc_id)

            item_dict["doc_id"] = doc_id
            is_active, status_reason = calculate_active_status(item_dict)
            item_dict["is_active"] = is_active

            doc = RetrievedDocument(
                doc_id=doc_id,
                category=item_dict.get("category") or suggested_category or _detect_category(raw_text),
                title=item_dict.get("title") or f"Chính sách {idx + 1}",
                content=item_dict.get("content") or raw_text,
                version=str(item_dict.get("version") or "1.0"),
                is_active=is_active,
                policy_type=item_dict.get("policy_type") or "permanent",
                effective_date=item_dict.get("effective_date"),
                expiration_date=item_dict.get("expiration_date"),
                tags=item_dict.get("tags") or _extract_tags(raw_text),
            )

            warnings = [
                f"Trích xuất thành công bằng mô hình AI ({extraction_source}).",
                f"Trạng thái tự động: {'Active' if is_active else 'Inactive'} ({status_reason})",
            ]
            if doc.policy_type == "temporary" and not doc.expiration_date:
                warnings.append("Cảnh báo: Chính sách tạm thời cần có ngày hết hạn rõ ràng.")

            results.append(
                PolicyFilterResult(
                    extracted_policy=doc,
                    warnings=warnings,
                    confidence_score=0.92,
                )
            )
        return results

    # Fallback heuristic if LLM failed
    fallback_res = _heuristic_fallback_extract(raw_text, suggested_category)
    return [fallback_res]


async def filter_raw_policy(request: RawPolicyFilterRequest) -> PolicyFilterResult:
    """Policy Extraction: OpenAI LLM → Heuristic fallback.

    1. Gửi văn bản thô tới OpenAI LLM để trích xuất các trường thông tin.
    2. Nếu OpenAI thất bại → fallback sang bộ phân tích heuristic.
    """
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

    # 2. Fallback to Heuristic if LLM extraction failed
    if not extracted_dict:
        return _heuristic_fallback_extract(raw_text, request.suggested_category)

    # Process Extracted Dict from LLM
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

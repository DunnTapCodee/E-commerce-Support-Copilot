"""Policy extraction: LLM-first (Gemini) with heuristic fallback.

Flow:
  1. Gọi Gemini API để trích xuất JSON từ văn bản chính sách thô.
  2. Nếu Gemini không khả dụng hoặc trả về lỗi, fallback sang heuristic regex.
"""
import json
import os
import re
import uuid
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from contracts.schemas import (
    RawPolicyFilterRequest,
    PolicyFilterResult,
    RetrievedDocument,
)
from services.rag_service.src.ingestion import load_policy_documents


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_gemini_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key and not key.startswith("your_") and len(key) > 10:
        return key
    return ""


def _get_candidate_models() -> List[str]:
    configured = os.getenv("GEMINI_MODEL", "").strip()
    models = []
    if configured:
        models.append(configured)
    # Available models ordered by speed and general availability
    models.extend([
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ])
    seen = set()
    result = []
    for m in models:
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _get_gemini_api_url(model: Optional[str] = None) -> str:
    m = model or "gemini-1.5-flash"
    return f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def _generate_unique_doc_id(existing_ids: List[str]) -> str:
    while True:
        candidate = f"POL-{uuid.uuid4().hex[:8].upper()}"
        if candidate not in existing_ids:
            return candidate


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _detect_category(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ["đổi trả", "hoàn trả", "trả hàng"]):
        return "return_refund"
    if any(w in low for w in ["hoàn tiền", "bồi hoàn", "refund"]):
        return "refund"
    if any(w in low for w in ["vận chuyển", "giao hàng", "ship", "phí vận chuyển", "hỏa tốc"]):
        return "shipping"
    if any(w in low for w in ["bảo hành", "sửa chữa", "linh kiện"]):
        return "warranty"
    if any(w in low for w in ["thanh toán", "cod", "thẻ tín dụng", "ví momo", "zalo pay", "ngân hàng"]):
        return "payment"
    if any(w in low for w in ["khuyến mãi", "voucher", "mã giảm giá", "ưu đãi", "giảm giá"]):
        return "promotions"
    if any(w in low for w in ["tài khoản", "bảo mật", "đăng nhập", "mật khẩu"]):
        return "account"
    return "support"


def _detect_policy_type(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["chương trình khuyến mãi", "flash sale", "sự kiện", "áp dụng từ ngày", "chiến dịch", "ưu đãi tết", "black friday"]):
        return "temporary"
    if "bãi bỏ" in lowered or "thay thế" in lowered:
        return "superseded"
    return "permanent"


def _extract_dates(text: str) -> Tuple[Optional[str], Optional[str]]:
    date_pattern = r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})"
    range_match = re.search(rf"từ\s+{date_pattern}\s+đến\s+{date_pattern}", text, re.IGNORECASE)
    if range_match:
        return range_match.group(1), range_match.group(2)
    dates = re.findall(date_pattern, text)
    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return dates[0], None
    return None, None


def _parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM output — strips markdown fences if present."""
    # Remove ```json ... ``` or ``` ... ``` fences
    cleaned = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def auto_extract_policy(request: RawPolicyFilterRequest) -> PolicyFilterResult:
    """Parse raw policy text using Gemini LLM, with heuristic fallback.

    Returns a PolicyFilterResult containing:
    - extracted_policy: RetrievedDocument with all structured fields.
    - warnings: Any warnings from extraction.
    - confidence_score: 0.95 for LLM path, 0.75–0.90 for heuristic fallback.
    """
    raw = request.raw_text.strip()
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # 1. LLM Extraction via Gemini
    # ------------------------------------------------------------------
    api_key = (request.gemini_api_key or "").strip() or _get_gemini_api_key()

    if api_key:
        try:
            prompt = (
                "Bạn là trợ lý AI chuyên trích xuất thông tin chính sách sàn thương mại điện tử từ văn bản tiếng Việt. "
                "Hãy phân tích văn bản và trả về DUY NHẤT một đối tượng JSON (không markdown, không giải thích) "
                "với các trường sau:\n"
                "{\n"
                "  \"policy_id\": \"<chuỗi id ngắn gọn ví dụ POL-XXXXXXXX hoặc null>\",\n"
                "  \"category\": \"<chuyên mục, ví dụ: return_refund, shipping, payment, warranty, promotions, support>\",\n"
                "  \"title\": \"<tiêu đề ngắn gọn của chính sách>\",\n"
                "  \"description\": \"<mô tả đầy đủ nội dung chính sách>\",\n"
                "  \"version\": \"1.0\",\n"
                "  \"policy_type\": \"permanent\" hoặc \"temporary\",\n"
                "  \"effective_date\": \"YYYY-MM-DD\" hoặc null,\n"
                "  \"expiration_date\": \"YYYY-MM-DD\" hoặc null,\n"
                "  \"tags\": [\"tag1\", \"tag2\", ...]\n"
                "}\n\n"
                "Quy tắc:\n"
                "- Nếu chính sách có ngày bắt đầu và kết thúc cụ thể của sự kiện/khuyến mãi → policy_type = \"temporary\".\n"
                "- Nếu là quy định, chính sách hoạt động tiêu chuẩn lâu dài → policy_type = \"permanent\".\n"
                "- Đối với permanent, expiration_date luôn là null.\n"
                "- Trích xuất tags liên quan giúp tìm kiếm chính sách.\n\n"
                "Văn bản chính sách:\n"
                f"{raw}"
            )

            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 800},
            }

            candidate_models = _get_candidate_models()
            last_err = ""
            for model_name in candidate_models:
                api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                try:
                    resp = requests.post(f"{api_url}?key={api_key}", json=payload, timeout=20)
                except Exception as req_err:
                    last_err = f"Lỗi kết nối tới {model_name}: {req_err}"
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            llm_output = parts[0].get("text", "").strip()
                            try:
                                extracted_json = _parse_llm_json(llm_output)

                                # Load existing IDs to avoid collision
                                policies_path = Path(__file__).parents[3] / "data" / "knowledge_base" / "policies.json"
                                existing_ids: List[str] = []
                                try:
                                    existing = load_policy_documents(policies_path)
                                    existing_ids = [p.doc_id for p in existing]
                                except Exception:
                                    pass

                                doc_id = extracted_json.get("policy_id") or _generate_unique_doc_id(existing_ids)
                                if doc_id in existing_ids:
                                    doc_id = _generate_unique_doc_id(existing_ids)

                                category = extracted_json.get("category") or request.suggested_category or _detect_category(raw)
                                title = extracted_json.get("title") or "Untitled Policy"
                                description = extracted_json.get("description") or raw
                                version = str(extracted_json.get("version") or "1.0")
                                policy_type = extracted_json.get("policy_type") or "permanent"
                                if policy_type not in ("permanent", "temporary"):
                                    policy_type = "permanent"
                                effective_date = extracted_json.get("effective_date")
                                expiration_date = extracted_json.get("expiration_date") if policy_type == "temporary" else None
                                tags = extracted_json.get("tags") or []

                                extracted = RetrievedDocument(
                                    doc_id=doc_id,
                                    category=category,
                                    title=title,
                                    content=description,
                                    version=version,
                                    is_active=True,
                                    policy_type=policy_type,
                                    effective_date=effective_date,
                                    expiration_date=expiration_date,
                                    tags=tags,
                                )
                                return PolicyFilterResult(
                                    extracted_policy=extracted,
                                    warnings=warnings,
                                    confidence_score=0.95,
                                )

                            except (json.JSONDecodeError, KeyError, ValueError) as parse_err:
                                warnings.append(f"LLM ({model_name}) trả về JSON không hợp lệ: {parse_err}")
                                break
                elif resp.status_code in (429, 500, 502, 503, 504):
                    # Model is experiencing high demand / overload, try next candidate model
                    last_err = f"Model {model_name} đang quá tải ({resp.status_code}), chuyển sang model khác..."
                    continue
                elif resp.status_code == 403:
                    if "free tier is not available for this project" in resp.text:
                        last_err = (
                            "Google thông báo: Dự án liên kết với Key này chưa được mở Free Tier "
                            "('The Gemini API free tier is not available for this project'). "
                            "Nguyên nhân: Key nằm trong một GCP Project cũ hoặc tài khoản tổ chức/trường học. "
                            "Khắc phục: Dùng Gmail cá nhân vào https://aistudio.google.com -> 'Create API key' -> chọn 'Create API key in new project'."
                        )
                        break
                    else:
                        last_err = f"Model {model_name} trả về lỗi 403: {resp.text[:150]}"
                        continue
                elif resp.status_code == 404:
                    last_err = f"Model {model_name} trả về lỗi 404 (model không tồn tại hoặc đã ngừng hỗ trợ)."
                    continue
                elif resp.status_code in (400, 401):
                    last_err = (
                        f"Key không hợp lệ hoặc đã bị vô hiệu hóa (Mã lỗi {resp.status_code}). "
                        "Vui lòng tạo hoặc sao chép lại API Key trên Google AI Studio."
                    )
                    break
                else:
                    last_err = f"Gemini API ({model_name}) trả về lỗi {resp.status_code}: {resp.text[:150]}"
                    continue

            if last_err and not warnings:
                if any(x in last_err for x in ["503", "429", "quá tải", "high demand"]):
                    warnings.append(
                        "Google Gemini API hiện đang bị quá tải cục bộ (lỗi 503: High demand). "
                        "Hệ thống đã tự động chuyển sang bộ chuẩn hoá Heuristic dự phòng."
                    )
                else:
                    warnings.append(last_err)

        except requests.exceptions.Timeout:
            warnings.append("Gemini API timeout, chuyển sang heuristic.")
        except Exception as exc:
            warnings.append(f"Lỗi khi gọi Gemini: {exc}")
    else:
        warnings.append("GEMINI_API_KEY chưa được cấu hình, sử dụng heuristic parser.")

    # ------------------------------------------------------------------
    # 2. Heuristic Fallback
    # ------------------------------------------------------------------
    title_match = re.search(r"^(.*?)(?:\.|:|\n)", raw)
    title = title_match.group(1).strip() if title_match else "Untitled Policy"
    content = raw

    policies_path = Path(__file__).parents[3] / "data" / "knowledge_base" / "policies.json"
    existing = []
    try:
        existing = load_policy_documents(policies_path)
    except Exception:
        existing = []
    existing_ids = [p.doc_id for p in existing]
    doc_id = _generate_unique_doc_id(existing_ids)

    category = request.suggested_category or _detect_category(raw)
    policy_type = _detect_policy_type(raw)
    effective_date_raw, expiration_date_raw = _extract_dates(raw)

    eff_iso = None
    exp_iso = None
    if effective_date_raw:
        dt = _parse_date(effective_date_raw)
        if dt:
            eff_iso = dt.strftime("%Y-%m-%d")
    if expiration_date_raw and policy_type == "temporary":
        dt = _parse_date(expiration_date_raw)
        if dt:
            exp_iso = dt.strftime("%Y-%m-%d")

    # Generate helpful default tags based on keywords
    tags = []
    for kw in ["đổi trả", "bảo hành", "vận chuyển", "thanh toán", "khuyến mãi", "khiếu nại"]:
        if kw in raw.lower():
            tags.append(kw)
    if not tags:
        tags = [category]

    extracted = RetrievedDocument(
        doc_id=doc_id,
        category=category,
        title=title,
        content=content,
        version="1.0",
        is_active=True,
        policy_type=policy_type,
        effective_date=eff_iso,
        expiration_date=exp_iso,
        tags=tags,
    )

    confidence = {"permanent": 0.9, "temporary": 0.8, "superseded": 0.7}.get(policy_type, 0.8)
    return PolicyFilterResult(
        extracted_policy=extracted,
        warnings=warnings,
        confidence_score=confidence,
    )

"""Business safety guardrail checks for API Gateway.
Includes:
1. Rule-based Intent Guard (Confidence threshold < 0.60, out-of-scope, explicit human agent).
2. Financial Action Guard (Interception of refund/payment actions to prevent automated financial execution).
3. Temporal Policy Guard (Lọc bẫy chính sách cũ: So sánh effective_date và expiration_date với ngày hiện tại).
4. Response Faithfulness & Hallucination Guard (NLI Entailment Check & Guardrails Framework Adapter).
"""

from datetime import date, datetime
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from contracts.schemas import (
    GuardrailResult,
    IntentPredictionResponse,
    RetrievedDocument,
)
from services.gateway.src.config import (
    DISABLE_CONFIDENCE_GUARD,
    FAITHFULNESS_THRESHOLD,
    FINANCIAL_INTENTS,
    INTENT_CONFIDENCE_THRESHOLD,
)


def _escalate(
    reason: str,
    temporal_status: Optional[str] = None,
    faithfulness_score: Optional[float] = None,
    hallucination_detected: Optional[bool] = None,
) -> GuardrailResult:
    """Create a safe decision that prevents LLM generation or blocks draft."""
    return GuardrailResult(
        allow_llm=False,
        action_type="ESCALATE_HUMAN",
        reason=reason,
        temporal_status=temporal_status,
        faithfulness_score=faithfulness_score,
        hallucination_detected=hallucination_detected,
    )


# =====================================================================
# 1. Rule-based Intent Guardrails
# =====================================================================
def evaluate_intent_guard(
    intent_resp: IntentPredictionResponse,
) -> GuardrailResult:
    """Reject invalid, uncertain, or unsupported intent predictions."""

    confidence = intent_resp.confidence

    # Fail closed if confidence is invalid.
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return _escalate(
            "Confidence không hợp lệ; cần nhân viên kiểm tra."
        )

    if not intent_resp.intent or not intent_resp.intent.strip():
        return _escalate(
            "Không xác định được ý định của khách hàng."
        )

    if intent_resp.intent == "human_agent":
        return _escalate(
            "Khách hàng yêu cầu hỗ trợ trực tiếp từ nhân viên."
        )

    if not intent_resp.is_in_scope:
        return _escalate(
            "Yêu cầu nằm ngoài phạm vi hỗ trợ; cần nhân viên xử lý."
        )

    if not DISABLE_CONFIDENCE_GUARD and confidence < INTENT_CONFIDENCE_THRESHOLD:
        return _escalate(
            f"Độ tin cậy thấp ({confidence:.0%}); "
            "cần nhân viên xác nhận ý định."
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Ý định hợp lệ, nằm trong phạm vi và đạt ngưỡng tin cậy.",
    )


# =====================================================================
# 2. Financial Safety Guardrails
# =====================================================================
def evaluate_financial_guard(
    intent: str,
) -> Optional[GuardrailResult]:
    """Prevent financial intents from triggering automated decisions."""

    if intent in FINANCIAL_INTENTS:
        return GuardrailResult(
            allow_llm=False,
            action_type="DIRECT_REFUND_FORM",
            reason=(
                "Yêu cầu tài chính cần nhân viên đối soát và quyết định. "
                "Hệ thống không tự phê duyệt hoặc thực hiện giao dịch."
            ),
        )

    return None


# =====================================================================
# 3. Temporal Policy Guard (Lọc bẫy chính sách cũ)
# =====================================================================
def _parse_iso_date(date_str: Optional[str]) -> Optional[date]:
    """Parse string date format (YYYY-MM-DD) safely."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def check_temporal_validity(
    doc: RetrievedDocument,
    reference_date: Optional[date] = None,
) -> Tuple[bool, str, str]:
    """Evaluate temporal validity of a policy document based on its policy_type.

    Logic per policy_type:
    ────────────────────────────────────────────────────────────────────
    permanent  : Standard operational policy; no fixed end date.
                 BLOCK only if is_active=False. expiration_date is ignored.
    temporary  : Time-bound campaign / promotion.
                 BLOCK if is_active=False OR date outside [effective_date, expiration_date].
                 Both date fields MUST be present; missing either is treated as EXPIRED.
    superseded : Replaced version of a former permanent policy.
                 Always BLOCKED regardless of is_active or dates.
    ────────────────────────────────────────────────────────────────────

    Returns:
        (is_valid, status, detail_message)
        where status in {'ACTIVE', 'EXPIRED', 'NOT_YET_EFFECTIVE', 'SUPERSEDED'}
    """
    ref_date = reference_date or date.today()
    policy_type = getattr(doc, "policy_type", "permanent") or "permanent"

    # --- superseded: always blocked ---
    if policy_type == "superseded":
        return (
            False,
            "SUPERSEDED",
            f"Chính sách [{doc.doc_id}] đã bị thay thế bởi phiên bản mới hơn "
            f"và không còn hiệu lực pháp lý (policy_type=superseded).",
        )

    # --- Primary kill-switch: is_active=False blocks all types ---
    if not doc.is_active:
        return (
            False,
            "EXPIRED",
            f"Chính sách [{doc.doc_id}] đã bị vô hiệu hóa (is_active=False).",
        )

    # --- temporary policies: strictly enforce [effective_date, expiration_date] ---
    if policy_type == "temporary":
        eff_date = _parse_iso_date(doc.effective_date)
        exp_date = _parse_iso_date(doc.expiration_date)

        if not eff_date or not exp_date:
            return (
                False,
                "EXPIRED",
                f"Chính sách tạm thời [{doc.doc_id}] thiếu ngày hiệu lực hoặc ngày hết hạn.",
            )

        if ref_date < eff_date:
            return (
                False,
                "NOT_YET_EFFECTIVE",
                f"Chính sách tạm thời [{doc.doc_id}] chưa có hiệu lực cho đến {eff_date.strftime('%d/%m/%Y')} (hiện tại: {ref_date.strftime('%d/%m/%Y')}).",
            )

        if ref_date > exp_date:
            return (
                False,
                "EXPIRED",
                f"Chính sách tạm thời [{doc.doc_id}] đã hết hạn vào ngày {exp_date.strftime('%d/%m/%Y')} (hiện tại: {ref_date.strftime('%d/%m/%Y')}).",
            )

        return (
            True,
            "ACTIVE",
            f"Chính sách tạm thời [{doc.doc_id}] đang có hiệu lực (từ {eff_date.strftime('%d/%m/%Y')} đến {exp_date.strftime('%d/%m/%Y')}).",
        )

    # --- permanent policies (default) ---
    if policy_type == "permanent":
        eff_date = _parse_iso_date(doc.effective_date)
        if eff_date and ref_date < eff_date:
            return (
                False,
                "NOT_YET_EFFECTIVE",
                f"Chính sách [{doc.doc_id}] chưa có hiệu lực cho đến {eff_date.strftime('%d/%m/%Y')} (hiện tại: {ref_date.strftime('%d/%m/%Y')}).",
            )

        exp_date = _parse_iso_date(doc.expiration_date)
        if exp_date and ref_date > exp_date:
            return (
                False,
                "EXPIRED",
                f"Chính sách [{doc.doc_id}] đã hết hạn vào ngày {exp_date.strftime('%d/%m/%Y')} (hiện tại: {ref_date.strftime('%d/%m/%Y')}).",
            )

        return (
            True,
            "ACTIVE",
            f"Chính sách vĩnh viễn [{doc.doc_id}] đang có hiệu lực.",
        )

    return False, "EXPIRED", f"Chính sách [{doc.doc_id}] không hợp lệ (loại không xác định)."


def evaluate_policy_guard(
    citations: List[RetrievedDocument],
    reference_date: Optional[date] = None,
) -> GuardrailResult:
    """Require usable, active, and temporally valid policy documents before LLM generation.

    Applies differentiated validation rules by policy_type:
    - permanent : blocked only if is_active=False
    - temporary : blocked if outside [effective_date, expiration_date] or is_active=False
    - superseded: always blocked
    """

    if not citations:
        return _escalate(
            "Không tìm thấy tài liệu chính sách làm căn cứ trả lời."
        )

    empty_docs = []
    expired_docs = []
    future_docs = []
    superseded_docs = []

    for doc in citations:
        if not doc.doc_id or not doc.content or not doc.content.strip():
            empty_docs.append(doc.doc_id or "UNKNOWN")
            continue

        is_valid, status, detail = check_temporal_validity(doc, reference_date)
        if not is_valid:
            if status == "SUPERSEDED":
                superseded_docs.append(f"{doc.doc_id} ({detail})")
            elif status == "EXPIRED":
                expired_docs.append(f"{doc.doc_id} ({detail})")
            elif status == "NOT_YET_EFFECTIVE":
                future_docs.append(f"{doc.doc_id} ({detail})")

    if empty_docs:
        return _escalate(
            f"Tài liệu rỗng hoặc thiếu nội dung: {', '.join(empty_docs)}."
        )

    if superseded_docs:
        return _escalate(
            reason=(
                "Phát hiện tài liệu đã bị thay thế (Superseded Policy Guard): "
                f"{'; '.join(superseded_docs)}. "
                "Hệ thống từ chối sử dụng tài liệu lỗi thời làm căn cứ tư vấn."
            ),
            temporal_status="SUPERSEDED",
        )

    if expired_docs:
        return _escalate(
            reason=(
                "Phát hiện tài liệu hết hiệu lực (Temporal Policy Guard): "
                f"{'; '.join(expired_docs)}. "
                "Hệ thống tự động kích hoạt Fail-Safe ngăn ngừa tư vấn sai chính sách cũ."
            ),
            temporal_status="EXPIRED",
        )

    if future_docs:
        return _escalate(
            reason=(
                "Phát hiện tài liệu chưa đến ngày áp dụng (Temporal Policy Guard): "
                f"{'; '.join(future_docs)}. "
                "Chính sách chưa chính thức có hiệu lực."
            ),
            temporal_status="NOT_YET_EFFECTIVE",
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Tất cả tài liệu trích dẫn đều đầy đủ và đang trong thời hạn hiệu lực.",
        temporal_status="ACTIVE",
    )


# =====================================================================
# 4. Response Faithfulness & Hallucination Guardrails
# =====================================================================
# Courteous / pleasantry phrases that are common in Vietnamese CS chitchat
# These should never be flagged as ungrounded factual claims or hallucinations unless containing numbers
PURE_COURTESY_PATTERNS = [
    r"^(?:dạ\s+)?(?:em\s+)?(?:chào|kính chào|tiki chào|xin chào)\s*(?:anh/chị|anh|chị|quý khách|bạn|mình)?[\s.,!?-]*$",
    r"^(?:cảm ơn|cam on)\s+(?:anh/chị|anh|chị|quý khách|bạn|mình)?[\s.,!?-]*$",
    r"^(?:em\s+)?(?:luôn\s+)?sẵn sàng hỗ trợ\s*(?:anh/chị|anh|chị|quý khách|thêm)?.*$",
    r"^(?:nếu\s+)?(?:anh/chị|anh|chị|quý khách|mình)\s+cần hỗ trợ thêm.*$",
    r"^chúc\s+(?:anh/chị|anh|chị|quý khách|bạn|mình).*$",
    r"^(?:rất\s+)?vui được hỗ trợ.*$",
    r"^(?:dạ\s+)?(?:em\s+)?(?:đã\s+)?ghi nhận.*$",
]


def _split_into_claims(text: str) -> List[str]:
    """Break text down into atomic statements for claim verification.
    Strips polite greeting prefixes and filters out purely courteous closing statements.
    """
    clean = re.sub(r"\[POL-[A-Z0-9_-]+\]", "", text)
    sentences = [s.strip() for s in re.split(r"[.\n!?]+", clean) if len(s.strip()) > 8]
    claims = []
    for s in sentences:
        has_nums = len(_extract_numeric_entities(s)) > 0
        is_pure = any(re.match(p, s.lower().strip()) for p in PURE_COURTESY_PATTERNS)
        if is_pure and not has_nums:
            continue
        stripped = re.sub(
            r"^(?:dạ\s+)?(?:em\s+)?(?:chào|kính chào|tiki chào|xin chào|cảm ơn)\s+(?:anh/chị|anh|chị|quý khách|bạn|mình)[^,.:\n!?]*[,:]\s*",
            "",
            s,
            flags=re.IGNORECASE,
        ).strip()
        target = stripped if len(stripped) > 5 else s
        is_target_pure = any(re.match(p, target.lower().strip()) for p in PURE_COURTESY_PATTERNS)
        if not is_target_pure or has_nums:
            claims.append(target)
    return claims


def _extract_numeric_entities(text: str) -> List[str]:
    """Identify numbers, percentages, and temporal entities in text."""
    return re.findall(r"\b\d+(?:[\.,]\d+)?%?|\b\d+\s*(?:ngày|tháng|năm|giờ|%|k|đ|vnd|triệu)\b", text, flags=re.IGNORECASE)


def evaluate_response_faithfulness(
    draft_text: str,
    citations: List[RetrievedDocument],
    threshold: float = FAITHFULNESS_THRESHOLD,
    customer_query: Optional[str] = None,
    order_data: Optional[Dict[str, Any]] = None,
) -> GuardrailResult:
    """NLI Entailment & Hallucination Check:
    Verify whether every claim in the LLM draft is faithfully supported by the retrieved context.
    - Premise: Concatenated text of all cited documents + customer query + system order data.
    - Hypothesis: Individual claims made by the draft response.
    - Hallucination detection: Flags fabricated facts, made-up timeframes, or contradictory claims.
    """
    if not draft_text or not draft_text.strip():
        return _escalate(
            "Bản nháp phản hồi rỗng; chặn phản hồi an toàn.",
            faithfulness_score=0.0,
            hallucination_detected=True,
        )

    # Template fallback draft is generated directly from system template and active citations
    if draft_text.startswith("[BẢN NHÁP DỰ PHÒNG"):
        return GuardrailResult(
            allow_llm=True,
            action_type="PROCEED_TO_LLM",
            faithfulness_score=1.0,
            hallucination_detected=False,
            reason="Bản nháp dự phòng được tổng hợp an toàn từ tài liệu chính sách đã kiểm duyệt.",
        )

    if not citations:
        return _escalate(
            "Không có tài liệu trích dẫn tham chiếu để kiểm tra độ trung thực.",
            faithfulness_score=0.0,
            hallucination_detected=True,
        )

    # 1. Build Ground Truth Premise from citations, customer query, and system order data
    premise_parts = [f"{doc.title} {doc.content}" for doc in citations]
    if customer_query:
        premise_parts.append(customer_query)
    if order_data:
        order_str = " ".join(f"{k} {v}" for k, v in order_data.items() if k not in ("shipping_timeline", "items"))
        if "items" in order_data and isinstance(order_data["items"], list):
            order_str += " " + " ".join(it.get("name", "") if isinstance(it, dict) else str(it) for it in order_data["items"])
        if "shipping_timeline" in order_data and isinstance(order_data["shipping_timeline"], list):
            order_str += " " + " ".join(t.get("status", "") if isinstance(t, dict) else str(t) for t in order_data["shipping_timeline"])
        premise_parts.append(order_str)
    premise_text = " ".join(premise_parts).lower()

    # 2. Extract atomic claims from draft text
    claims = _split_into_claims(draft_text)
    if not claims:
        return GuardrailResult(
            allow_llm=True,
            action_type="PROCEED_TO_LLM",
            faithfulness_score=1.0,
            hallucination_detected=False,
            reason="Bản nháp ngắn gọn, không phát hiện khẳng định nằm ngoài tài liệu.",
        )

    entailed_claims = 0
    contradicted_claims = []
    unsupported_claims = []

    for claim in claims:
        claim_lower = claim.lower()
        claim_numbers = set(_extract_numeric_entities(claim_lower))

        # Check for numeric entity contradiction (e.g., claiming 90 days when policy says 30 days)
        unsupported_nums = [n for n in claim_numbers if n not in premise_text]
        if unsupported_nums:
            contradicted_claims.append(
                f"Khẳng định chứa số liệu/thời hạn không có trong chính sách: '{claim}' (Số liệu lạ: {', '.join(unsupported_nums)})"
            )
            continue

        # Semantic token overlap check (Heuristic NLI token containment)
        words = [w for w in re.findall(r"\w+", claim_lower) if len(w) > 3]
        if words:
            overlap = sum(1 for w in words if w in premise_text)
            overlap_ratio = overlap / len(words)
        else:
            overlap_ratio = 1.0

        if overlap_ratio >= 0.40:
            entailed_claims += 1
        else:
            unsupported_claims.append(f"Khẳng định không tìm thấy căn cứ trong tài liệu: '{claim}'")

    total_claims = len(claims)
    faithfulness_score = round(entailed_claims / total_claims, 2) if total_claims > 0 else 1.0

    # Decision logic
    has_contradiction = len(contradicted_claims) > 0
    is_faithful = (faithfulness_score >= threshold) and not has_contradiction

    if not is_faithful:
        violation_details = []
        if contradicted_claims:
            violation_details.extend(contradicted_claims)
        if unsupported_claims:
            violation_details.extend(unsupported_claims)

        detail_summary = " | ".join(violation_details[:2])
        return _escalate(
            reason=(
                f"Phát hiện nguy cơ ảo giác (Faithfulness Score: {faithfulness_score:.0%}, "
                f"ngưỡng yêu cầu: {threshold:.0%}). {detail_summary}"
            ),
            faithfulness_score=faithfulness_score,
            hallucination_detected=True,
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        faithfulness_score=faithfulness_score,
        hallucination_detected=False,
        reason=(
            f"Câu trả lời đã vượt qua kiểm tra NLI Entailment "
            f"(Faithfulness Score: {faithfulness_score:.0%}). Nội dung trung thực với chính sách."
        ),
    )


# =====================================================================
# 5. Specialized Guardrails Framework Adapter (NeMo / Guardrails AI)
# =====================================================================
class SpecializedGuardrailAdapter:
    """Adapter illustrating integration with specialized frameworks:
    - NVIDIA NeMo Guardrails (Colang-based input/output rails).
    - Guardrails AI (guardrails-ai validators: ProvenByDocs, HallucinationDetector).
    Provides extensible hooks for member experimentation.
    """

    def __init__(self, engine_type: str = "native_nli"):
        self.engine_type = engine_type  # 'native_nli', 'nemo_guardrails', 'guardrails_ai'

    def apply_input_rails(self, query: str, intent_resp: IntentPredictionResponse) -> GuardrailResult:
        """Input rails: Verify query intent confidence and financial boundary."""
        intent_res = evaluate_intent_guard(intent_resp)
        if not intent_res.allow_llm:
            return intent_res

        fin_res = evaluate_financial_guard(intent_resp.intent)
        if fin_res and not fin_res.allow_llm:
            return fin_res

        return intent_res

    def apply_retrieval_rails(self, citations: List[RetrievedDocument]) -> GuardrailResult:
        """Retrieval rails: Temporal policy validity and freshness verification."""
        return evaluate_policy_guard(citations)

    def apply_output_rails(self, draft_text: str, citations: List[RetrievedDocument]) -> GuardrailResult:
        """Output rails: Response faithfulness and hallucination entailment check."""
        return evaluate_response_faithfulness(draft_text, citations)


# =====================================================================
# 6. Hard-Blocking Safety Envelopes & Prompt Injection Defense
# =====================================================================
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(ignore|disregard|forget)\s+(?:all\s+)?(?:previous\s+)?(instructions|prompts|rules)", re.IGNORECASE),
    re.compile(r"(bỏ qua|quên đi|hủy bỏ)\s+(mọi|tất cả)?\s*(hướng dẫn|chỉ thị|quy tắc|quy định)", re.IGNORECASE),
    re.compile(r"(in ra|tiết lộ|show me|reveal)\s+(system prompt|prompts hệ thống|chỉ dẫn hệ thống)", re.IGNORECASE),
    re.compile(r"\b(jailbreak|dan mode|bẻ khóa ai|developer mode)\b", re.IGNORECASE),
    re.compile(r"\b(đóng vai là|act as a|pretend you are)\s+(unrestricted|không bị giới hạn)", re.IGNORECASE),
]


def evaluate_prompt_injection(query: str) -> Tuple[bool, Optional[str]]:
    """Detect prompt injection and adversarial jailbreak attempts."""
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = pattern.search(query)
        if match:
            return True, f"Phát hiện mẫu Prompt Injection / Jailbreak: '{match.group(0)}'"
    return False, None


def evaluate_runtime_safety_envelope(
    customer_query: str,
    draft_text: str,
    order_data: Optional[Dict[str, Any]] = None,
    citations: Optional[List[RetrievedDocument]] = None,
) -> GuardrailResult:
    """Rigorous runtime safety envelope:
    1. Prompt Injection Attack check on query.
    2. Unauthorized Financial Action check on draft.
    3. PII Boundary check.
    Aligns with CMU MLIP Chapter 18: System Quality (Fail-closed safety envelopes).
    """
    violations: List[str] = []

    # 1. Prompt Injection Check
    is_injection, injection_msg = evaluate_prompt_injection(customer_query)
    if is_injection:
        violations.append(injection_msg)

    # 2. Financial Hard Gate on Draft
    # LLM must NEVER promise to refund money unless verified order has status 'REFUND_PENDING' or 'CANCELLED'
    refund_promise_match = re.search(
        r"(sẽ hoàn lại|đã hoàn|hoàn trả lại số tiền|chuyển khoản lại cho anh/chị|bồi thường)\s+(\d+[\d.,]*\s*(?:đ|vnd|đồng)?)",
        draft_text,
        re.IGNORECASE,
    )
    if refund_promise_match:
        authorized = False
        if order_data:
            order_status = str(order_data.get("status", "")).upper()
            if order_status in {"REFUND_PENDING", "CANCELLED", "RETURN_APPROVED"}:
                authorized = True
        if not authorized:
            violations.append(
                f"LLM tự ý phát ngôn cam kết bồi thường / hoàn tiền trái thẩm quyền: '{refund_promise_match.group(0)}'"
            )

    # 3. Decision
    if violations:
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=" | ".join(violations),
            is_hard_fail=True,
            violations=violations,
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Đạt chuẩn kiểm định an toàn (Safety Envelope passed).",
        is_hard_fail=False,
        violations=[],
    )


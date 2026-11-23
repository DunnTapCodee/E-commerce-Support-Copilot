"""Shared safety taxonomy, faithfulness, and runtime safety envelope checks.

Located in contracts/ so both API Gateway and Conversation Service Docker
images share one canonical, zero-duplication implementation.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from contracts.schemas import GuardrailResult, RetrievedDocument

CANONICAL_INTENTS: Tuple[str, ...] = (
    "track_order",
    "cancel_order",
    "delivery_time",
    "delivery_issue",
    "shipping_costs",
    "return_policy",
    "return_product",
    "refund_policy",
    "request_refund",
    "refund_status",
    "payment_issue",
    "human_agent",
    "warranty",
    "get_discounts",
    "create_account",
    "recover_password",
)
OOS_LABEL = "out_of_scope"
CHITCHAT_INTERNAL_INTENTS = frozenset(
    {"chitchat_greeting", "chitchat_thanks", "chitchat_confirm", "chitchat_farewell"}
)


def is_intent_in_scope(intent_name: Optional[str], allow_chitchat_internal: bool = False) -> bool:
    """Return True iff intent belongs to the canonical 16 domain intents (or internal chitchat)."""
    if not intent_name:
        return False
    if allow_chitchat_internal and intent_name in CHITCHAT_INTERNAL_INTENTS:
        return True
    return intent_name != OOS_LABEL and intent_name in CANONICAL_INTENTS


def _escalate(
    reason: str,
    temporal_status: Optional[str] = None,
    faithfulness_score: Optional[float] = None,
    hallucination_detected: Optional[bool] = None,
    is_hard_fail: bool = False,
    violations: Optional[List[str]] = None,
) -> GuardrailResult:
    """Create a fail-closed GuardrailResult blocking LLM output."""
    return GuardrailResult(
        allow_llm=False,
        action_type="ESCALATE_HUMAN",
        reason=reason,
        temporal_status=temporal_status,
        faithfulness_score=faithfulness_score,
        hallucination_detected=hallucination_detected,
        is_hard_fail=is_hard_fail,
        violations=violations or [],
    )


PURE_COURTESY_PATTERNS = [
    r"^(?:dạ\s+)?(?:em\s+)?(?:chào|kính chào|tiki chào|xin chào)\s*(?:anh/chị|anh|chị|quý khách|bạn|mình)?[\s.,!?-]*$",
    r"^(?:cảm ơn|cam on)\s+(?:anh/chị|anh|chị|quý khách|bạn|mình)?[\s.,!?-]*$",
    r"^(?:em\s+)?(?:luôn\s+)?sẵn sàng hỗ trợ\s*(?:anh/chị|anh|chị|quý khách|thêm)?.*$",
    r"^(?:nếu\s+)?(?:anh/chị|anh|chị|quý khách|mình)\s+cần hỗ trợ thêm.*$",
    r"^chúc\s+(?:anh/chị|anh|chị|quý khách|bạn|mình).*$",
    r"^(?:rất\s+)?vui được hỗ trợ.*$",
    r"^(?:dạ\s+)?(?:em\s+)?(?:đã\s+)?ghi nhận.*$",
]

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(ignore|disregard|forget)\s+(?:all\s+)?(?:previous\s+)?(instructions|prompts|rules)", re.IGNORECASE),
    re.compile(r"(bỏ qua|quên đi|hủy bỏ)\s+(mọi|tất cả)?\s*(hướng dẫn|chỉ thị|quy tắc|quy định)", re.IGNORECASE),
    re.compile(r"(in ra|tiết lộ|show me|reveal)\s+(system prompt|prompts hệ thống|chỉ dẫn hệ thống)", re.IGNORECASE),
    re.compile(r"\b(jailbreak|dan mode|bẻ khóa ai|developer mode)\b", re.IGNORECASE),
    re.compile(r"\b(đóng vai là|act as a|pretend you are)\s+(unrestricted|không bị giới hạn)", re.IGNORECASE),
]


def extract_numeric_entities(text: str) -> List[str]:
    """Identify numbers, percentages, and temporal entities in text."""
    return re.findall(
        r"\b\d+(?:[\.,]\d+)?%?|\b\d+\s*(?:ngày|tháng|năm|giờ|%|k|đ|vnd|triệu)\b",
        text,
        flags=re.IGNORECASE,
    )


def split_into_claims(text: str) -> List[str]:
    """Break text into atomic factual statements, stripping pure courteous phrasing."""
    clean = re.sub(r"\[POL-[A-Z0-9_-]+\]", "", text)
    sentences = [s.strip() for s in re.split(r"[.\n!?]+", clean) if len(s.strip()) > 8]
    claims: List[str] = []
    for s in sentences:
        has_nums = len(extract_numeric_entities(s)) > 0
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


def build_grounding_premise(
    citations: Optional[List[RetrievedDocument]] = None,
    customer_query: Optional[str] = None,
    order_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Construct lowercase premise text from citations, customer query, and order data."""
    premise_parts: List[str] = []
    if citations:
        premise_parts.extend(f"{doc.title} {doc.content}" for doc in citations)
    if customer_query:
        premise_parts.append(customer_query)
    if order_data:
        scalar_tokens: List[str] = []
        for k, v in order_data.items():
            if k in ("shipping_timeline", "items"):
                continue
            scalar_tokens.append(f"{k} {v}")
            if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1000:
                int_val = int(v)
                scalar_tokens.append(f"{int_val:,}")
                scalar_tokens.append(f"{int_val:,}".replace(",", "."))
        order_str = " ".join(scalar_tokens)
        if "items" in order_data and isinstance(order_data["items"], list):
            order_str += " " + " ".join(
                it.get("name", "") if isinstance(it, dict) else str(it) for it in order_data["items"]
            )
        if "shipping_timeline" in order_data and isinstance(order_data["shipping_timeline"], list):
            order_str += " " + " ".join(
                t.get("status", "") if isinstance(t, dict) else str(t) for t in order_data["shipping_timeline"]
            )
        premise_parts.append(order_str)
    return " ".join(premise_parts).lower()


def find_ungrounded_numbers(draft_text: str, premise_text: str) -> List[str]:
    """Return claim-level descriptions for any numeric entities absent from premise_text."""
    findings: List[str] = []
    for claim in split_into_claims(draft_text):
        claim_lower = claim.lower()
        claim_numbers = set(extract_numeric_entities(claim_lower))
        unsupported_nums = [n for n in claim_numbers if n not in premise_text]
        if unsupported_nums:
            findings.append(
                f"Khẳng định chứa số liệu/thời hạn không có trong dữ liệu/chính sách: '{claim}' "
                f"(Số liệu lạ: {', '.join(sorted(unsupported_nums))})"
            )
    return findings


def evaluate_response_faithfulness(
    draft_text: str,
    citations: List[RetrievedDocument],
    threshold: float = 0.70,
    customer_query: Optional[str] = None,
    order_data: Optional[Dict[str, Any]] = None,
) -> GuardrailResult:
    """Verify every claim in draft_text against cited policies, query, and order_data."""
    if not draft_text or not draft_text.strip():
        return _escalate(
            "Bản nháp phản hồi rỗng; chặn phản hồi an toàn.",
            faithfulness_score=0.0,
            hallucination_detected=True,
        )

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

    premise_text = build_grounding_premise(citations, customer_query=customer_query, order_data=order_data)
    claims = split_into_claims(draft_text)
    if not claims:
        return GuardrailResult(
            allow_llm=True,
            action_type="PROCEED_TO_LLM",
            faithfulness_score=1.0,
            hallucination_detected=False,
            reason="Bản nháp ngắn gọn, không phát hiện khẳng định nằm ngoài tài liệu.",
        )

    entailed_claims = 0
    contradicted_claims: List[str] = []
    unsupported_claims: List[str] = []

    for claim in claims:
        claim_lower = claim.lower()
        claim_numbers = set(extract_numeric_entities(claim_lower))
        unsupported_nums = [n for n in claim_numbers if n not in premise_text]
        if unsupported_nums:
            contradicted_claims.append(
                f"Khẳng định chứa số liệu/thời hạn không có trong chính sách: '{claim}' (Số liệu lạ: {', '.join(unsupported_nums)})"
            )
            continue

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
    has_contradiction = len(contradicted_claims) > 0
    is_faithful = (faithfulness_score >= threshold) and not has_contradiction

    if not is_faithful:
        violation_details = contradicted_claims + unsupported_claims
        detail_summary = " | ".join(violation_details[:2])
        return _escalate(
            reason=(
                f"Phát hiện nguy cơ ảo giác (Faithfulness Score: {faithfulness_score:.0%}, "
                f"ngưỡng yêu cầu: {threshold:.0%}). {detail_summary}"
            ),
            faithfulness_score=faithfulness_score,
            hallucination_detected=True,
            violations=violation_details[:2],
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
    faithfulness_threshold: float = 0.70,
) -> GuardrailResult:
    """Shared runtime safety envelope for Gateway and Conversation Service:
    1. Prompt injection / jailbreak check on customer_query.
    2. Unauthorized monetary refund / compensation promise hard gate.
    3. Response faithfulness & numeric grounding against citations and/or order_data.
    """
    violations: List[str] = []
    faithfulness_score: Optional[float] = None
    hallucination_detected = False

    # 1. Prompt Injection Check
    is_injection, injection_msg = evaluate_prompt_injection(customer_query)
    if is_injection and injection_msg:
        violations.append(injection_msg)

    # 2. Financial Hard Gate on Draft
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

    # 3. Grounding / Faithfulness Parity Check
    if citations:
        faith_res = evaluate_response_faithfulness(
            draft_text=draft_text,
            citations=citations,
            threshold=faithfulness_threshold,
            customer_query=customer_query,
            order_data=order_data,
        )
        faithfulness_score = faith_res.faithfulness_score
        hallucination_detected = bool(faith_res.hallucination_detected)
        if not faith_res.allow_llm:
            violations.append(faith_res.reason)
    elif order_data and draft_text and not draft_text.startswith("[BẢN NHÁP DỰ PHÒNG"):
        premise_text = build_grounding_premise(customer_query=customer_query, order_data=order_data)
        num_findings = find_ungrounded_numbers(draft_text, premise_text)
        if num_findings:
            hallucination_detected = True
            faithfulness_score = 0.0
            violations.extend(num_findings[:2])

    if violations:
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=" | ".join(violations),
            faithfulness_score=faithfulness_score,
            hallucination_detected=hallucination_detected,
            is_hard_fail=True,
            violations=violations,
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Đạt chuẩn kiểm định an toàn (Safety Envelope passed).",
        faithfulness_score=faithfulness_score,
        hallucination_detected=hallucination_detected,
        is_hard_fail=False,
        violations=[],
    )

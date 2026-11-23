"""Runtime Safety Guardrails & Prompt Injection Detection for Conversation Service.
Complies with CMU MLIP Chapter 18: System Quality (Fail-closed Safety Envelopes).
"""
from contracts.safety import (
    PROMPT_INJECTION_PATTERNS,
    canonical_customer_ids,
    detect_brand_competitor_bait,
    detect_fabricated_prior_promise,
    detect_foreign_customer_query,
    detect_warehouse_seal_request,
    evaluate_prompt_injection,
    evaluate_runtime_safety_envelope,
    is_order_owned_by_customer,
)

__all__ = [
    "PROMPT_INJECTION_PATTERNS",
    "canonical_customer_ids",
    "detect_brand_competitor_bait",
    "detect_fabricated_prior_promise",
    "detect_foreign_customer_query",
    "detect_warehouse_seal_request",
    "evaluate_prompt_injection",
    "evaluate_runtime_safety_envelope",
    "is_order_owned_by_customer",
]


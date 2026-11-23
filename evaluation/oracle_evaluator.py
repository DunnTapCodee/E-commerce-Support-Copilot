"""Tri-tier Test Oracle Suite addressing 'The Test Oracle Problem' in Generative AI.
Aligns with CMU MLIP Chapter 15 & Lecture 5:
- Tier 1: Deterministic Hard Constraints Oracle (Regex, Schema, Entity Verification, Zero Financial Breach).
- Tier 2: Rubric-based Quality Oracle (Tone of Voice, Grounding, Policy Citation, Conciseness).
- Tier 3: NLI Faithfulness & Entailment Oracle (Checking claims against retrieved policy contexts).
"""
import re
from typing import Any, Dict, List, Optional
from contracts.schemas import RetrievedDocument


class TestOracleEvaluator:
    """Evaluates generated LLM responses without relying solely on simple exact string matches."""

    # -------------------------------------------------------------
    # Tier 1: Deterministic Hard Constraints Oracle
    # -------------------------------------------------------------
    @staticmethod
    def verify_hard_constraints(
        draft_text: str,
        expected_entities: Optional[Dict[str, str]] = None,
        disallowed_patterns: Optional[List[str]] = None,
        require_citation: bool = False,
    ) -> Dict[str, Any]:
        """Check absolute non-negotiable constraints on the draft output."""
        violations = []
        text_lower = draft_text.lower()

        # 1. Entity Preservation Check (e.g. order_id, phone must appear accurately)
        if expected_entities:
            for entity_key, expected_val in expected_entities.items():
                if expected_val.lower() not in text_lower:
                    violations.append(f"Missing mandatory entity {entity_key}: '{expected_val}'")

        # 2. Disallowed Pattern Check (e.g. forbidden refund promises, error stacktraces)
        forbidden = disallowed_patterns or [
            r"traceback \(most recent call last\)",
            r"internal server error",
            r"exception in",
            r"undefined",
            r"null",
        ]
        for pat in forbidden:
            if re.search(pat, draft_text, re.IGNORECASE):
                violations.append(f"Violated disallowed pattern: '{pat}'")

        # 3. Citation Tag Check
        has_citation = bool(re.search(r"\[POL-[A-Z0-9-]+\]", draft_text))
        if require_citation and not has_citation:
            violations.append("Draft lacks required [POL-...] policy citation tag")

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "has_citation": has_citation,
        }

    # -------------------------------------------------------------
    # Tier 2: Rubric-based Quality Oracle
    # -------------------------------------------------------------
    @staticmethod
    def evaluate_rubric(
        draft_text: str,
        customer_query: str,
        intent: str,
    ) -> Dict[str, Any]:
        """Score response against e-commerce customer support rubric:
        - Professionalism & Polite tone (30 pts)
        - Grounded Actionability (40 pts)
        - Conciseness & Clarity (30 pts)
        """
        score = 0
        details = []

        # 1. Polite Tone (Dạ, chào, cảm ơn, anh/chị...)
        has_polite_intro = any(w in draft_text.lower() for w in ["dạ", "chào anh", "chào chị", "chào quý khách", "cảm ơn"])
        has_polite_outro = any(w in draft_text.lower() for w in ["nhé ạ", "giúp em nhé", "hỗ trợ thêm", "vui lòng", "ạ"])
        if has_polite_intro:
            score += 15
            details.append("Polite greeting (+15)")
        if has_polite_outro:
            score += 15
            details.append("Polite closing (+15)")

        # 2. Actionability & Grounding (Contains specific guidance, status, or order resolution)
        has_order_info = bool(re.search(r"(đơn hàng|ord-\d+|sản phẩm|giao|vận chuyển|hoàn|đổi trả)", draft_text.lower()))
        if has_order_info:
            score += 25
            details.append("Relevant e-commerce domain guidance (+25)")

        has_next_step = any(w in draft_text.lower() for w in ["bạn vui lòng", "anh/chị vui lòng", "em xin", "dự kiến", "trong vòng", "liên hệ"])
        if has_next_step:
            score += 15
            details.append("Clear actionable next step (+15)")

        # 3. Conciseness (Between 50 and 800 characters - not empty, not endless rambling)
        length = len(draft_text.strip())
        if 60 <= length <= 900:
            score += 30
            details.append("Optimal length & conciseness (+30)")
        elif length > 900:
            score += 10
            details.append("Penalty for verbosity / rambling (+10)")
        else:
            score += 5
            details.append("Penalty for terse / incomplete response (+5)")

        return {
            "rubric_score_percent": score,
            "is_satisfactory": score >= 75,
            "rubric_details": details,
        }

    # -------------------------------------------------------------
    # Tier 3: NLI Faithfulness & Entailment Oracle
    # -------------------------------------------------------------
    @staticmethod
    def evaluate_faithfulness(
        draft_text: str,
        citations: List[RetrievedDocument],
    ) -> Dict[str, Any]:
        """Check if claims in the draft are faithfully supported by citations."""
        from services.gateway.src.guardrails import evaluate_response_faithfulness
        res = evaluate_response_faithfulness(draft_text, citations)
        return {
            "faithfulness_score": res.faithfulness_score or 1.0,
            "hallucination_detected": bool(res.hallucination_detected),
            "reason": res.reason,
            "passed": not res.hallucination_detected,
        }

    # -------------------------------------------------------------
    # Tier 4: Dynamic Order Data Grounding Oracle (Module 3 DB Check)
    # -------------------------------------------------------------
    @staticmethod
    def verify_dynamic_order_grounding(
        draft_text: str,
        order_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Verify dynamic order_id and monetary amounts in draft_text match order_data."""
        violations: List[str] = []
        expected_order_id = str(order_data.get("order_id", "")).upper().strip()
        expected_amount = order_data.get("total_amount")

        mentioned_orders = [m.upper() for m in re.findall(r"ORD-[A-Z0-9]+", draft_text, re.IGNORECASE)]
        if expected_order_id:
            if expected_order_id not in mentioned_orders:
                violations.append(f"Missing expected order_id '{expected_order_id}' in draft")
            for mo in mentioned_orders:
                if mo != expected_order_id:
                    violations.append(f"Hallucinated foreign order_id '{mo}' (expected '{expected_order_id}')")

        if expected_amount is not None:
            expected_int = int(expected_amount)
            money_matches = re.findall(r"(\d[\d\.,]*)\s*(?:đ|vnd|vnđ|đồng)", draft_text, re.IGNORECASE)
            for raw_num in money_matches:
                cleaned = re.sub(r"[^\d]", "", raw_num)
                if cleaned and int(cleaned) != expected_int:
                    violations.append(
                        f"Hallucinated order amount '{raw_num}' (DB total_amount is {expected_int})"
                    )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "checked_order_id": expected_order_id,
        }


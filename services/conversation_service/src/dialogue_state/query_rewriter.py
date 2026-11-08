"""Contextual Query Rewriter & Multi-turn Coreference Resolver.
Rewrites customer utterances using a 4-Scope Architecture:
1. SCOPE_OUT_OF_SERVICE: Chitchat, greetings, acknowledgements, out-of-domain trivia -> Pass-through without modification.
2. SCOPE_ORDER_SPECIFIC: Inquiries about personal order status, tracking, delivery time, pricing, cancellation -> Grounded with Order facts.
3. SCOPE_POLICY_GENERAL: General inquiries about platform policies, vouchers, promotions, VAT, returns -> Clean policy search query, strictly NO order ID injection.
4. SCOPE_ORDER_POLICY_HYBRID: Inquiries checking applicability of policies to a specific order -> Fused order facts + policy target.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx

from contracts.llm_failover import call_chat_completion_with_failover
from services.conversation_service.src.config import OPENAI_BASE_URL, OPENAI_MODEL
from services.conversation_service.src.dialogue_state.state import ConversationState


class QueryRewriter:
    """Production Query Rewriter implementing 4-Scope Contextual Disambiguation."""

    SCOPE_OUT_OF_SERVICE = "out_of_service"
    SCOPE_ORDER_SPECIFIC = "order_specific"
    SCOPE_POLICY_GENERAL = "policy_general"
    SCOPE_ORDER_POLICY_HYBRID = "order_policy_hybrid"

    @classmethod
    def is_conversational_closing_or_ack(cls, text: str) -> bool:
        """Identify short chitchat, greetings, or acknowledgements that do not need rewriting."""
        cleaned = text.strip().lower()
        cleaned_no_punct = re.sub(r"[^\w\s]", "", cleaned).strip()
        short_phrases = {
            "ok", "oke", "okie", "oki", "dạ", "vang", "vâng", "dạ vâng",
            "cảm ơn", "cam on", "thanks", "thank you", "bye", "tạm biệt",
            "được rồi", "hiểu rồi", "da vang", "ok shop", "oke shop",
            "chào", "chào bạn", "chào shop", "chào b", "hi", "hello", "alo", "alo shop",
            "ad ơi", "shop ơi", "cho mình hỏi", "tư vấn giúp", "tư vấn mình",
            "thế à", "thế hả", "vậy à", "vậy hả", "vậy sao", "thế sao", "ừ", "đúng rồi", "chuẩn rồi",
        }
        if cleaned_no_punct in short_phrases:
            return True
        if len(cleaned_no_punct.split()) <= 2 and cleaned_no_punct in short_phrases:
            return True
        return False

    @classmethod
    def detect_query_scope(cls, query: str) -> str:
        """Determine which of the 4 scopes this customer query belongs to."""
        q_clean = query.strip().lower()

        # 1. Scope 1: Out of service / Courtesy / Chitchat / Out-of-domain
        if cls.is_conversational_closing_or_ack(q_clean):
            return cls.SCOPE_OUT_OF_SERVICE

        off_topic_trivia = [
            "ronaldo", "messi", "thời tiết", "phương trình", "toán học", "bóng đá",
            "thơ ca", "lịch sử", "ca sĩ", "diễn viên", "chính trị", "tổng thống", "thủ tướng"
        ]
        if any(w in q_clean for w in off_topic_trivia):
            return cls.SCOPE_OUT_OF_SERVICE

        # Policy & Service keywords (general knowledge & terms)
        has_policy_cues = bool(re.search(
            r"\b(chính sách|quy định|điều kiện|thể lệ|hướng dẫn|thủ tục|đổi trả|trả hàng|hoàn tiền|bảo hành|hóa đơn|hóa đơn đỏ|vat|chính hãng|xuất xứ|ưu đãi|khuyến mãi|khuyến mại|voucher|mã giảm|coupon|tiki xu|giảm giá|freeship|miễn phí vận chuyển)\b",
            q_clean
        ))

        # Explicit order references / anaphoric pronouns referencing a specific order
        has_order_cues = bool(re.search(r"\bORD-\d+\b", query, re.IGNORECASE)) or any(
            p in q_clean for p in [
                "đơn này", "đơn đó", "đơn của mình", "đơn của tôi", "đơn vừa đặt", "đơn vừa mua",
                "món này", "áo này", "sản phẩm này", "gói hàng này", "kiện này", "nó có được"
            ]
        )

        # 4. Scope 4: Hybrid (Asking how a policy applies to a specific order)
        if has_policy_cues and has_order_cues:
            return cls.SCOPE_ORDER_POLICY_HYBRID

        # 3. Scope 3: Policy General (Policy inquiry with NO specific order reference)
        if has_policy_cues and not has_order_cues:
            return cls.SCOPE_POLICY_GENERAL

        # 2. Scope 2: Order Specific (Tracking, price, shipping status, delivery time, cancellation)
        return cls.SCOPE_ORDER_SPECIFIC

    @classmethod
    async def rewrite_query(
        cls,
        user_query: str,
        state: ConversationState,
        order_data: Optional[Dict[str, Any]] = None,
        openai_key: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Rewrite user utterance into a standalone grounded query based on 4 Scopes.
        Returns:
            (rewritten_query, method_used)
        """
        clean_query = user_query.strip()
        if not clean_query:
            return clean_query, "empty_query"

        scope = cls.detect_query_scope(clean_query)

        # SCOPE 1: Out of service / Chitchat -> Passthrough immediately
        if scope == cls.SCOPE_OUT_OF_SERVICE:
            return clean_query, "scope_out_of_service_passthrough"

        # Check if already a standalone full sentence with explicit ORD and clear keywords
        has_explicit_order = bool(re.search(r"\bORD-\d+\b", clean_query, re.IGNORECASE))
        if has_explicit_order and len(clean_query.split()) > 10 and not any(w in clean_query.lower() for w in ["nó", "cái này", "cụ thể"]):
            return clean_query, "direct_standalone"

        api_key = openai_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return cls._heuristic_rewrite(clean_query, scope, state, order_data)

        # Build History Context (last 3 turns)
        history_lines = []
        recent_turns = state.turns[-3:] if state.turns else []
        for t in recent_turns:
            if t.customer_query:
                history_lines.append(f"Khách: {t.customer_query}")
            if t.agent_response and not getattr(t, "is_acknowledgement", False):
                history_lines.append(f"CSKH: {t.agent_response[:100]}...")
        history_str = "\n".join(history_lines) if history_lines else "Lượt trao đổi đầu tiên."

        # SCOPE 3: POLICY GENERAL -> STRICTLY HIDE ORDER DATA
        if scope == cls.SCOPE_POLICY_GENERAL:
            prompt = f"""Bạn là bộ phận tiền xử lý truy vấn tìm kiếm chính sách (Policy Query Rewriter) cho CSKH Tiki.
Nhiệm vụ: Viết lại câu hỏi của khách hàng thành MỘT CÂU truy vấn tra cứu tài liệu/chính sách hoàn chỉnh bằng tiếng Việt, sửa lỗi chính tả hoặc từ viết tắt.

LỊCH SỬ TRAO ĐỔI GẦN ĐÂY:
{history_str}

CÂU HỎI HIỆN TẠI CỦA KHÁCH:
"{clean_query}"

QUY TẮC BẮT BUỘC:
- Đây là câu hỏi về CHÍNH SÁCH / ƯU ĐÃI / DỊCH VỤ CHUNG của sàn Tiki.
- TUYỆT ĐỐI KHÔNG tự tiện bịa hoặc ghép bất kỳ mã đơn hàng (ORD-...) hay tên sản phẩm cá nhân nào vào câu truy vấn.
- Trả về DUY NHẤT 1 câu truy vấn tra cứu chuẩn mực, không thêm dấu ngoặc kép, không thêm lời giải thích."""
            return await cls._call_llm_rewriter(prompt, clean_query, scope, state, order_data, api_key, "llm_policy_rewriter")

        # SCOPE 2 & 4: Prepare Order Context
        order_ctx = "Chưa có thông tin đơn hàng."
        order_id = state.active_order_id or (order_data.get("order_id") if order_data else None)
        if order_data:
            customer_name = order_data.get("customer_name", state.customer_id)
            items = ", ".join(f"{it.get('name')} (x{it.get('quantity', 1)})" for it in order_data.get("items", [])) or "Sản phẩm"
            status = order_data.get("order_status") or order_data.get("status", "N/A")
            order_ctx = f"Mã đơn: {order_id or 'N/A'} | Người nhận: {customer_name} | Sản phẩm: {items} | Trạng thái: {status}"
        elif order_id:
            order_ctx = f"Mã đơn: {order_id}"

        # SCOPE 4: ORDER POLICY HYBRID -> Check policy applicability on a specific order
        if scope == cls.SCOPE_ORDER_POLICY_HYBRID:
            prompt = f"""Bạn là bộ phận tiền xử lý truy vấn đối soát chính sách cho đơn hàng (Hybrid Order-Policy Rewriter) của Tiki.
Nhiệm vụ: Viết lại câu hỏi của khách thành MỘT CÂU truy vấn đầy đủ ngữ cảnh để kiểm tra xem đơn hàng cụ thể có áp dụng được chính sách sàn hay không.

HỒ SƠ ĐƠN HÀNG CỦA KHÁCH:
{order_ctx}

LỊCH SỬ TRAO ĐỔI GẦN ĐÂY:
{history_str}

CÂU HỎI HIỆN TẠI CỦA KHÁCH:
"{clean_query}"

QUY TẮC BẮT BUỘC:
- Kết hợp rõ ràng mã đơn hàng ({order_id or 'đơn hàng đã đặt'}), trạng thái đơn và chính sách khách hàng đang muốn đối soát.
- Trả về DUY NHẤT 1 câu truy vấn bằng tiếng Việt, không kèm giải thích, không kèm markdown."""
            return await cls._call_llm_rewriter(prompt, clean_query, scope, state, order_data, api_key, "llm_hybrid_rewriter")

        # SCOPE 2: ORDER SPECIFIC -> Tracking, price, delivery time, cancellation
        prompt = f"""Bạn là bộ phận tiền xử lý truy vấn thông tin đơn hàng (Order Query Rewriter) cho CSKH Tiki.
Nhiệm vụ: Viết lại câu hỏi tỉnh lược của khách hàng thành MỘT CÂU truy vấn hoàn chỉnh, giải quyết các đại từ (nó, đơn của mình, khi nào tới, bao nhiêu tiền...), bổ sung mã đơn hàng ({order_id or 'ORD-1001'}) và tên sản phẩm/khách hàng.

HỒ SƠ ĐƠN HÀNG:
{order_ctx}

LỊCH SỬ TRAO ĐỔI GẦN ĐÂY:
{history_str}

CÂU NÓI HIỆN TẠI CỦA KHÁCH:
"{clean_query}"

QUY TẮC BẮT BUỘC:
- Trả về DUY NHẤT 1 câu truy vấn hoàn chỉnh bằng tiếng Việt để tra cứu hành trình hoặc xử lý đơn hàng.
- Tuyệt đối không thêm giải thích, không thêm dấu ngoặc kép hay markdown."""
        return await cls._call_llm_rewriter(prompt, clean_query, scope, state, order_data, api_key, "llm_order_rewriter")

    @classmethod
    async def _call_llm_rewriter(
        cls,
        prompt: str,
        fallback_query: str,
        scope: str,
        state: ConversationState,
        order_data: Optional[Dict[str, Any]],
        api_key: str,
        method_name: str,
    ) -> Tuple[str, str]:
        """Execute LLM chat completion call with automatic multi-key failover."""
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1500,
        }

        try:
            res_data = await call_chat_completion_with_failover(payload, timeout=12.0)
            if res_data and "choices" in res_data and res_data["choices"]:
                candidate = res_data["choices"][0].get("message", {}).get("content", "").strip()
                candidate = candidate.strip('"\n\r ')
                if candidate and len(candidate) > 4 and not candidate.startswith("```"):
                    return candidate, method_name
        except Exception as exc:
            print(f"[QueryRewriter] LLM call failed ({method_name}): {exc}")

        return cls._heuristic_rewrite(fallback_query, scope, state, order_data)

    @classmethod
    def _heuristic_rewrite(
        cls,
        query: str,
        scope: str,
        state: ConversationState,
        order_data: Optional[Dict[str, Any]],
    ) -> Tuple[str, str]:
        """Deterministic heuristic fallback when LLM is unavailable."""
        if scope in (cls.SCOPE_OUT_OF_SERVICE, cls.SCOPE_POLICY_GENERAL):
            return query, "heuristic_passthrough"

        order_id = state.active_order_id or (order_data.get("order_id") if order_data else None)
        item_names = ""
        if order_data and "items" in order_data and isinstance(order_data["items"], list):
            item_names = ", ".join(it.get("name", "") for it in order_data["items"][:2])

        q_lower = query.lower()
        if order_id and order_id.lower() not in q_lower:
            extra = f" cho đơn hàng {order_id}"
            if item_names:
                extra += f" ({item_names})"
            return f"{query}{extra}", "heuristic_order_expansion"

        return query, "heuristic_direct"

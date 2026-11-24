"""Copilot Draft Engine (Phần 3: Bản thảo câu trả lời gợi ý của Copilot cho Nhân viên).
Assembles full 6-layer context (Input, Intent, Facts, Order Data, Memory, Policy Citations)
and generates a polite, grounded agent draft response ready for staff review and approval.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from contracts.llm_failover import (
    DEFAULT_OPENAI_BASE_URL,
    call_chat_completion_with_failover,
    get_available_api_keys,
    get_default_openai_model,
    get_tls_verify_for_httpx,
    stream_chat_completion_with_failover,
)
from services.conversation_service.src.policies.offline_fallback import OfflineDraftFallback

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")
OPENAI_MODEL = get_default_openai_model()


class CopilotDraftEngine:
    """Full-Context Draft Engine generating ready-to-approve agent responses."""

    @classmethod
    async def _call_openai_compatible(cls, prompt: str, api_key: str = "") -> Optional[str]:
        """Generate response via OpenAI-compatible API endpoint with automatic multi-key failover."""
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Bạn là trợ lý AI Copilot CSKH Tiki. Hãy suy nghĩ ngắn gọn và trả lời trực tiếp bằng tiếng Việt chuẩn mực CSKH."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }

        try:
            res_data = await call_chat_completion_with_failover(payload, timeout=25.0)
            if res_data and "choices" in res_data and res_data["choices"]:
                msg = res_data["choices"][0].get("message", {})
                content = (msg.get("content") or "").strip()
                if content:
                    return content
        except Exception as exc:
            print(f"[CopilotDraftEngine] OpenAI-compatible call error: {exc}")
        return None

    @classmethod
    async def _stream_openai_compatible(cls, prompt: str, api_key: str = "") -> AsyncGenerator[str, None]:
        """Stream response tokens via OpenAI-compatible API endpoint with automatic multi-key failover."""
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Bạn là trợ lý AI Copilot CSKH Tiki. Hãy suy nghĩ ngắn gọn và trả lời trực tiếp bằng tiếng Việt chuẩn mực CSKH.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }

        try:
            async for token in stream_chat_completion_with_failover(payload, timeout=30.0):
                yield token
        except Exception as exc:
            print(f"[CopilotDraftEngine] Stream error: {exc}")

    @classmethod
    async def _call_gemini(cls, prompt: str, api_key: str) -> Optional[str]:
        """Generate response via Google Gemini API with multi-model resilience."""
        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                },
            }
            candidate_models = [
                os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
                "gemini-3.8-flash",
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
            ]
            async with httpx.AsyncClient(timeout=10.0, verify=get_tls_verify_for_httpx()) as client:
                for model in dict.fromkeys(candidate_models):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    try:
                        resp = await client.post(url, json=payload)
                        if resp.status_code == 200:
                            candidates = resp.json().get("candidates", [])
                            if candidates:
                                raw_draft = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                                if raw_draft:
                                    return raw_draft
                        elif resp.status_code in (400, 404, 429, 500, 503):
                            continue
                    except Exception:
                        continue
        except Exception as exc:
            print(f"[CopilotDraftEngine] Gemini generation call failed: {exc}")
        return None

    @staticmethod
    def _format_multi_order_candidates(multi_order_context: Optional[Dict[str, Any]], max_items: int = 15) -> str:
        """Format candidate orders (including payment, carrier, amount) for LLM prompt or fallback."""
        if not multi_order_context:
            return ""
        candidates = multi_order_context.get("candidates") or []
        if not candidates:
            return ""
        lines: List[str] = []
        for idx, o in enumerate(candidates[:max_items], 1):
            oid = o.get("order_id", "N/A")
            status = o.get("order_status") or o.get("status") or "Đang xử lý"
            items = ", ".join(f"{it.get('name')} (x{it.get('quantity', 1)})" for it in o.get("items", [])) or "Sản phẩm đặt mua"
            amount = f"{int(o.get('total_amount')):,.0f} VNĐ" if o.get("total_amount") else ""
            pm = o.get("payment_method") or ""
            carrier = o.get("carrier") or ""
            eta = o.get("promised_delivery_date") or o.get("estimated_delivery")
            meta_parts = [p for p in [amount, pm, carrier, f"Dự kiến: {eta}" if eta else ""] if p]
            meta_str = f" | {' | '.join(meta_parts)}" if meta_parts else ""
            lines.append(f"{idx}. #{oid} ({status}) — {items}{meta_str}")
        return "\n".join(lines)

    @staticmethod
    def build_full_context_prompt(
        user_query: str,
        intent: str,
        facts: Dict[str, Any],
        order_data: Optional[Dict[str, Any]],
        context_summary: Optional[str],
        recent_turns_text: str,
        citations: List[Any],
        multi_order_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Assemble all 6 context layers into a structured prompt."""
        # 1. Order details
        order_str = "Chưa có thông tin đơn hàng cụ thể."
        if multi_order_context and multi_order_context.get("candidates"):
            reason = multi_order_context.get("reason", "multiple_customer_orders")
            filter_label = multi_order_context.get("filter_label")
            candidates_str = CopilotDraftEngine._format_multi_order_candidates(multi_order_context)
            summary = multi_order_context.get("computed_summary")
            summary_str = ""
            if isinstance(summary, dict):
                summary_str = (
                    f"\nTỔNG HỢP HỆ THỐNG ĐÃ TÍNH SẴN: "
                    f"Tổng số đơn={summary.get('total_orders', 0)} | "
                    f"Số đơn tính tiền hợp lệ={summary.get('paid_order_count', 0)} | "
                    f"Tổng tiền đã thanh toán/hợp lệ={summary.get('total_paid_amount', 0):,} VNĐ | "
                    f"Số đơn hủy/lỗi thanh toán={summary.get('excluded_count', 0)}"
                )
            order_str = (
                f"KHÁCH HÀNG CÓ NHIỀU ĐƠN HÀNG PHÙ HỢP (Lý do: {reason}"
                f"{f', bộ lọc: {filter_label}' if filter_label else ''}):{summary_str}\n{candidates_str}"
            )
        elif order_data:
            order_id = order_data.get("order_id", "N/A")
            status = order_data.get("order_status") or order_data.get("status", "N/A")
            amount = f"{order_data.get('total_amount', 0):,} VNĐ" if order_data.get("total_amount") else "N/A"
            payment_method = order_data.get("payment_method", "N/A")
            carrier = order_data.get("carrier") or order_data.get("shipper_name") or "Đơn vị vận chuyển Tiki"
            tracking_code = order_data.get("tracking_code", "")
            est_delivery = order_data.get("promised_delivery_date") or order_data.get("estimated_delivery") or "chưa có lịch hẹn cụ thể"
            customer_name = order_data.get("customer_name", "Khách hàng")
            phone = order_data.get("phone", "")
            items = ", ".join(f"{it.get('name')} (x{it.get('quantity', 1)})" for it in order_data.get("items", [])) or "Sản phẩm đặt mua"
            order_str = (
                f"Mã đơn: {order_id} | Người nhận: {customer_name} (SĐT: {phone}) | Trạng thái: {status} | "
                f"Sản phẩm: {items} | Giá trị: {amount} | Thanh toán: {payment_method} | "
                f"Đơn vị giao: {carrier} (Vận đơn: {tracking_code}) | Dự kiến giao: {est_delivery}"
            )

        # 2. Policy citations
        docs_str = "\n".join(
            [f"--- [{d.doc_id}] {d.title} ---\n{d.content}" for d in citations if getattr(d, "is_active", True)]
        )
        if not docs_str:
            docs_str = "Không có tài liệu trích xuất."

        # 3. Facts
        facts_str = ", ".join([f"{k}: {v}" for k, v in facts.items()]) if facts else "Chưa có"

        prompt = f"""Bạn là AI Copilot thông minh hỗ trợ nhân viên Chăm sóc Khách hàng (CSKH) của sàn thương mại điện tử Tiki.
Nhiệm vụ: Soạn sẵn một BẢN THẢO CÂU TRẢ LỜI HOÀN CHỈNH, LỊCH SỰ, CHUẨN XÁC để nhân viên CSKH duyệt và gửi cho khách hàng.

=== HỒ SƠ NGỮ CẢNH HỘI THOẠI ===
1. CÂU HỎI HIỆN TẠI CỦA KHÁCH:
"{user_query}"

2. Ý ĐỊNH ĐÃ XÁC ĐỊNH:
{intent}

3. THỰC THỂ ĐÃ BÓC TÁCH (FACTS):
{facts_str}

4. DỮ LIỆU ĐƠN HÀNG HỆ THỐNG:
{order_str}

5. TÓM TẮT BỐI CẢNH PHIÊN CHAT:
{context_summary or 'Chưa có tóm tắt trước đó.'}

6. LỊCH SỬ TRAO ĐỔI GẦN NHẤT:
{recent_turns_text or 'Lượt trao đổi đầu tiên.'}

7. TÀI LIỆU CHÍNH SÁCH THAM CHIẾU (NẾU CÓ):
{docs_str}

=== QUY TẮC BẮT BUỘC KHI SOẠN THẢO BẢN THẢO CSKH ===
1. QUY TẮC XƯNG HÔ: Luôn xưng "em" và gọi khách hàng là "anh/chị" (hoặc "mình"). TUYỆT ĐỐI KHÔNG dùng từ "bạn" khi xưng hô với khách hàng. Luôn mở đầu tự nhiên bằng "Dạ em chào anh/chị [Tên khách nếu có]...".
2. TRẢ LỜI TRỰC DIỆN & HÀNH ĐỘNG NGAY: Đưa thông tin khách đang cần (trạng thái, ngày nhận hàng, số tiền, cách xử lý) ngay trong 1-2 câu đầu tiên.
3. TẬN DỤNG TRIỆT ĐỂ DỮ LIỆU ĐƠN HÀNG: Khi hồ sơ có thông tin đơn hàng cụ thể, BẮT BUỘC nêu rõ mã đơn, tên sản phẩm, trạng thái và ngày giao dự kiến. TUYỆT ĐỐI KHÔNG hướng dẫn khách "vào mục Đơn hàng của tôi trên App để tự kiểm tra", vì khách đang yêu cầu nhân viên tra cứu trực tiếp!
4. NẾU THIẾU MÃ ĐƠN HÀNG: Khi khách hỏi về đơn mà chưa có mã đơn trong hệ thống, hãy ân cần xin mã: "Dạ anh/chị cho em xin mã đơn hàng hoặc số điện thoại để em kiểm tra ngay giúp mình nhé ạ."
5. CĂN CỨ PHÁP LÝ & CHÍNH SÁCH: Khi nêu thời hạn đổi trả, điều kiện hoàn tiền hay voucher, BẮT BUỘC trích dẫn mã tài liệu ở cuối câu theo định dạng [POL-XXX].
6. ĐỘ DÀI & ĐỊNH DẠNG: Tối đa 150 từ, súc tích, mạch lạc (nếu là các bước thực hiện thì dùng tối đa 3 gạch đầu dòng rõ ràng).
7. NẾU KHÁCH HỎI ƯU ĐÃI/VOUCHER: Giải đáp các chương trình ưu đãi, mã giảm giá, voucher freeship (trích dẫn [POL-PROMO-001] hoặc liên quan). TUYỆT ĐỐI KHÔNG lạc đề sang bưu tá hay vận chuyển khi khách hỏi khuyến mãi!
8. CÂU HỎI NGOÀI PHẠM VI (Out of Scope): Nếu khách hỏi thời tiết, toán học, tin tức bên ngoài, hãy từ chối khéo léo, lịch sự và hỏi xem khách có cần hỗ trợ gì về mua sắm Tiki không.
9. NẾU HỒ SƠ CÓ DANH SÁCH NHIỀU ĐƠN HÀNG PHÙ HỢP: Hãy liệt kê ngắn gọn mã đơn, tên sản phẩm và trạng thái của từng đơn (tối đa 5 đơn), đồng thời mời anh/chị xác nhận chính xác mã đơn (ví dụ ORD-1026) muốn kiểm tra hoặc thao tác tiếp.
10. TUYỆT ĐỐI KHÔNG xuất ra tiêu đề, nhãn hệ thống (ví dụ: "**BẢN THẢO CÂU TRẢ LỜI**" hay "Dưới đây là bản thảo"). Hãy bắt đầu trực tiếp bằng lời chào lịch sự gửi cho khách hàng.
"""
        return prompt

    @classmethod
    async def generate_draft(
        cls,
        user_query: str,
        intent: str,
        facts: Dict[str, Any],
        order_data: Optional[Dict[str, Any]],
        context_summary: Optional[str],
        recent_turns_text: str,
        citations: List[Any],
        is_live_chat: bool = False,
        multi_order_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate response draft via hybrid AI generation + smart macro safety."""

        # Case 0: Live chat handover
        if intent == "human_agent" or is_live_chat:
            return (
                "Dạ em chào anh/chị, em là chuyên viên CSKH phụ trách hỗ trợ trực tiếp cho mình đây ạ. "
                "Em đã nắm được thông tin anh/chị đang cần hỗ trợ từ hệ thống. "
                "Anh/chị chia sẻ chi tiết giúp em vấn đề để em xử lý ngay cho mình nhé ạ!"
            )

        # Case 0b: Explicit out-of-scope from Intent Service when no order portfolio context applies
        if not multi_order_context and intent == "out_of_scope":
            return (
                "Dạ em chào anh/chị! Câu hỏi này hiện nằm ngoài phạm vi hỗ trợ thông tin đơn hàng và mua sắm của Tiki rồi ạ 😊. "
                "Anh/chị có cần em hỗ trợ thêm thông tin gì về đơn hàng, vận chuyển hay các chính sách mua sắm trên sàn Tiki không ạ?"
            )

        # Case 1: Financial risk (Refund / Payment Issue) - Smart Macro for 100% legal & audit compliance
        if intent in ("request_refund", "payment_issue") and order_data:
            order_id = order_data.get("order_id", "của mình")
            amount_val = order_data.get("total_amount", 0)
            amount_str = f"{amount_val:,}đ" if amount_val else "giá trị đơn hàng"
            gateway = order_data.get("payment_method", "tài khoản nguồn")
            return (
                f"Dạ em chào anh/chị, em đã kiểm tra đơn hàng {order_id} của mình trên hệ thống. "
                f"Số tiền {amount_str} sẽ được hoàn trả trực tiếp về {gateway} trong vòng 1-3 ngày làm việc "
                f"theo đúng quy định hoàn tiền [POL-REFUND-001] ạ. Anh/chị chú ý kiểm tra thông báo tài khoản giúp em nhé!"
            )

        # Case 2: LLM Generation with Full Multi-layer Context
        prompt = cls.build_full_context_prompt(
            user_query=user_query,
            intent=intent,
            facts=facts,
            order_data=order_data,
            context_summary=context_summary,
            recent_turns_text=recent_turns_text,
            citations=citations,
            multi_order_context=multi_order_context,
        )

        provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        gemini_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)

        # 1. Primary: OpenAI-compatible (CKEY.VN via api.xah.io/v1 with multi-key failover)
        if provider in ("openai_compatible", "openai", "auto") and get_available_api_keys():
            draft = await cls._call_openai_compatible(prompt)
            if draft:
                from contracts.safety import clean_draft_header
                return clean_draft_header(draft)

        # 2. Secondary: Gemini API only when provider explicitly allows Gemini
        if provider in ("gemini", "auto") and gemini_key:
            draft = await cls._call_gemini(prompt, gemini_key)
            if draft:
                from contracts.safety import clean_draft_header
                return clean_draft_header(draft)

        # 3. Grounded Semantic Fallback Draft when LLMs are unavailable
        return cls._build_semantic_fallback_draft(
            user_query, intent, facts, order_data, citations, multi_order_context=multi_order_context
        )

    @classmethod
    async def generate_draft_stream(
        cls,
        user_query: str,
        intent: str,
        facts: Dict[str, Any],
        order_data: Optional[Dict[str, Any]],
        context_summary: Optional[str],
        recent_turns_text: str,
        citations: List[Any],
        is_live_chat: bool = False,
        multi_order_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream drafted response tokens in real-time (~0.8s TTFT)."""
        # Case 0: Live chat handover
        if intent == "human_agent" or is_live_chat:
            yield (
                "Dạ em chào anh/chị, em là nhân viên CSKH Tiki trực tuyến đây ạ. "
                "Em đã tiếp nhận yêu cầu của mình và sẵn sàng hỗ trợ trực tiếp ngay bây giờ ạ!"
            )
            return

        # Case 1: Trivial closing/gratitude
        if intent in ("chitchat_greeting", "chitchat_farewell", "chitchat"):
            closing_res = (
                "Dạ em cảm ơn anh/chị! Nếu mình có bất kỳ thắc mắc hoặc cần hỗ trợ thêm thông tin nào khác về đơn hàng, "
                "anh/chị cứ nhắn lại cho em bất cứ lúc nào nhé. Chúc anh/chị một ngày mua sắm vui vẻ cùng Tiki ạ!"
            )
            yield closing_res
            return

        prompt = cls.build_full_context_prompt(
            user_query=user_query,
            intent=intent,
            facts=facts,
            order_data=order_data,
            context_summary=context_summary,
            recent_turns_text=recent_turns_text,
            citations=citations,
            multi_order_context=multi_order_context,
        )

        provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        yielded_any = False
        if provider in ("openai_compatible", "openai", "auto") and get_available_api_keys():
            async for token in cls._stream_openai_compatible(prompt):
                yielded_any = True
                yield token

        if not yielded_any:
            # Fallback to static drafted text
            static_draft = await cls.generate_draft(
                user_query=user_query,
                intent=intent,
                facts=facts,
                order_data=order_data,
                context_summary=context_summary,
                recent_turns_text=recent_turns_text,
                citations=citations,
                is_live_chat=is_live_chat,
                multi_order_context=multi_order_context,
            )
            yield static_draft

    @classmethod
    def _build_semantic_fallback_draft(cls, user_query: str, intent: str, facts: Dict[str, Any], order_data: Optional[Dict[str, Any]], citations: List[Any], multi_order_context: Optional[Dict[str, Any]] = None) -> str:
        return OfflineDraftFallback.build_draft(user_query=user_query, intent=intent, facts=facts, order_data=order_data, citations=citations, multi_order_context=multi_order_context)

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
    call_chat_completion_with_failover,
    stream_chat_completion_with_failover,
    get_available_api_keys,
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai-gpt-oss-20b")


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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
    def build_full_context_prompt(
        user_query: str,
        intent: str,
        facts: Dict[str, Any],
        order_data: Optional[Dict[str, Any]],
        context_summary: Optional[str],
        recent_turns_text: str,
        citations: List[Any],
    ) -> str:
        """Assemble all 6 context layers into a structured prompt."""
        # 1. Order details
        order_str = "Chưa có thông tin đơn hàng cụ thể."
        if order_data:
            order_id = order_data.get("order_id", "N/A")
            status = order_data.get("order_status") or order_data.get("status", "N/A")
            amount = f"{order_data.get('total_amount', 0):,} VNĐ" if order_data.get("total_amount") else "N/A"
            payment_method = order_data.get("payment_method", "N/A")
            carrier = order_data.get("carrier") or order_data.get("shipper_name", "Đơn vị vận chuyển Tiki")
            tracking_code = order_data.get("tracking_code", "")
            est_delivery = order_data.get("estimated_delivery", "N/A")
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

        prompt = f"""Bạn là AI Copilot chuyên nghiệp hỗ trợ nhân viên Chăm sóc Khách hàng (CSKH) của sàn thương mại điện tử Tiki.
Nhiệm vụ của bạn là soạn sẵn một BẢN THẢO CÂU TRẢ LỜI HOÀN CHỈNH để nhân viên CSKH kiểm tra, đối soát và bấm DUYỆT gửi cho khách hàng.

=== HỒ SƠ NGỮ CẢNH TOÀN DIỆN ===
1. CÂU HỎI HIỆN TẠI CỦA KHÁCH:
"{user_query}"

2. Ý ĐỊNH ĐÃ XÁC ĐỊNH:
{intent}

3. CÁC THỰC THỂ ĐÃ BÓC TÁCH (FACTS):
{facts_str}

4. DỮ LIỆU ĐƠN HÀNG TỪ HỆ THỐNG:
{order_str}

5. TÓM TẮT BỐI CẢNH TỪ ĐẦU CUỘC CHAT:
{context_summary or 'Chưa có tóm tắt trước đó.'}

6. LỊCH SỬ TRAO ĐỔI GẦN NHẤT:
{recent_turns_text or 'Lượt trao đổi đầu tiên.'}

7. TÀI LIỆU CHÍNH SÁCH THAM CHIẾU:
{docs_str}

=== YÊU CẦU BẮT BUỘC ĐỐI VỚI BẢN THẢO CSKH ===
1. Quy tắc xưng hô BẮT BUỘC: Nhân viên CSKH luôn xưng "em" và gọi khách hàng là "anh/chị" (hoặc "mình"). TUYỆT ĐỐI KHÔNG dùng từ "bạn" khi xưng hô với khách hàng. Luôn mở đầu tự nhiên bằng "Dạ em chào anh/chị...".
2. TẬN DỤNG TRỰC TIẾP DỮ LIỆU ĐƠN HÀNG: Khi hồ sơ ở mục 4 đã có thông tin đơn hàng cụ thể (tên khách hàng, mã đơn, sản phẩm, trạng thái giao hàng), BẠN BẮT BUỘC PHẢI TRẢ LỜI CỤ THỂ CHI TIẾT ĐƠN ĐÓ (tên sản phẩm, số tiền, ngày giao/trạng thái). TUYỆT ĐỐI KHÔNG hướng dẫn khách "vào mục Đơn hàng của tôi trên App để tra cứu", vì khách đang yêu cầu nhân viên tra cứu trực tiếp!
3. Nếu khách hàng hỏi về tiến độ đơn hàng mà hệ thống chưa có bất kỳ mã đơn hoặc thông tin đơn nào trong hồ sơ, hãy lịch sự đề nghị: "Dạ anh/chị cho em xin mã đơn hàng hoặc số điện thoại đặt hàng để em tra cứu ngay giúp mình nhé ạ."
4. Căn cứ chính sách: Mỗi khi đưa ra điều kiện, thời hạn hoặc quy định, hãy trích dẫn mã tài liệu tương ứng ở ngay phía sau câu đó theo định dạng [POL-XXX].
5. Nếu khách hàng chỉ chào hỏi xã giao hoặc cảm ơn/xác nhận ("ok", "oce", "cảm ơn"), hãy đáp lễ lịch sự, thân thiện và sẵn sàng hỗ trợ thêm nếu khách cần.
6. Độ dài chuẩn mực: Viết ngắn gọn, súc tích trong khoảng 3 - 5 câu (hoặc gạch đầu dòng rõ ràng nếu hướng dẫn các bước), sẵn sàng để nhân viên chỉ cần đọc lướt và nhấn nút gửi cho khách.
7. XỬ LÝ CÂU HỎI NGOÀI PHẠM VI (Out of Scope): Nếu câu hỏi của khách hàng không liên quan đến thương mại điện tử, đơn hàng hay mua sắm (ví dụ hỏi thời tiết, toán học, người nổi tiếng, thể thao...), BẠN TUYỆT ĐỐI KHÔNG tìm cách suy diễn hay lôi đơn hàng vào câu trả lời. Hãy soạn một câu từ chối khéo léo, lịch sự, thân thiện và hỏi xem khách có cần hỗ trợ gì về đơn hàng hay chính sách Tiki không.
8. NẾU KHÁCH HỎI VỀ ƯU ĐÃI / KHUYẾN MÃI / VOUCHER: Hãy giải đáp trực tiếp về các chương trình ưu đãi, mã giảm giá, voucher freeship áp dụng cho đơn hàng/sản phẩm của khách (tham chiếu chính sách [POL-PROMO-001] hoặc chính sách liên quan). TUYỆT ĐỐI KHÔNG trả lời lạc đề sang lộ trình vận chuyển hay bưu tá khi khách đang hỏi về khuyến mãi, ưu đãi!
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
    ) -> str:
        """Generate response draft via hybrid AI generation + smart macro safety."""

        # Case 0: Live chat handover
        if intent == "human_agent" or is_live_chat:
            return (
                "Dạ em chào anh/chị, em là chuyên viên CSKH phụ trách hỗ trợ trực tiếp cho mình đây ạ. "
                "Em đã nắm được thông tin anh/chị đang cần hỗ trợ từ hệ thống. "
                "Anh/chị chia sẻ chi tiết giúp em vấn đề để em xử lý ngay cho mình nhé ạ!"
            )

        # Case 0: Short conversational acknowledgements / thanks / closings
        q_clean = user_query.strip().lower()
        if q_clean in {"oce", "ok", "oke", "oki", "dạ", "vâng", "cảm ơn", "cam on", "thanks", "thank you", "được rồi", "hiểu rồi"}:
            return (
                "Dạ em cảm ơn anh/chị! Nếu mình có bất kỳ thắc mắc hay cần hỗ trợ gì thêm trong quá trình mua sắm tại Tiki, "
                "anh/chị cứ nhắn tin để em hỗ trợ ngay nhé. Chúc anh/chị một ngày nhiều niềm vui ạ!"
            )

        # Case 0b: Out-of-scope / off-topic question gentle refusal
        if intent == "out_of_scope" or any(k in q_clean for k in ["ronaldo", "messi", "thời tiết", "phương trình", "toán học", "bóng đá", "thơ ca"]):
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
        )

        gemini_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)

        # 1. Primary: OpenAI-compatible (openai-gpt-oss-20b via api.xah.io with failover)
        if get_available_api_keys():
            draft = await cls._call_openai_compatible(prompt)
            if draft:
                return draft

        # 2. Secondary: Gemini API if OpenAI is degraded / quota exceeded
        if gemini_key:
            draft = await cls._call_gemini(prompt, gemini_key)
            if draft:
                return draft

        # 3. Grounded Semantic Fallback Draft when LLMs are unavailable
        return cls._build_semantic_fallback_draft(user_query, intent, facts, order_data, citations)

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
        )

        yielded_any = False
        if get_available_api_keys():
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
            )
            yield static_draft

    @classmethod
    def _build_semantic_fallback_draft(
        cls,
        user_query: str,
        intent: str,
        facts: Dict[str, Any],
        order_data: Optional[Dict[str, Any]],
        citations: List[Any],
    ) -> str:
        """Clean, grounded fallback draft without dumping full documents."""
        citation_tags = " ".join([f"[{d.doc_id}]" for d in citations if getattr(d, "is_active", True)]) or "[POL-INFO]"
        order_id = facts.get("order_id") or (order_data.get("order_id") if order_data else None)

        if intent in ("track_order", "delivery_time"):
            if order_data:
                amount_str = f"{order_data.get('total_amount', 0):,} VNĐ" if order_data.get("total_amount") else "N/A"
                if any(w in user_query.lower() for w in ["bao nhiêu tiền", "hết bao nhiêu", "tổng tiền", "giá bao nhiêu", "thanh toán bao nhiêu", "bao tien"]):
                    return (
                        f"Dạ em chào anh/chị, em đã kiểm tra thông tin đơn hàng {order_id or ''} của mình. "
                        f"Tổng giá trị thanh toán cho đơn hàng là {amount_str} (bao gồm đầy đủ thuế và phụ phí) {citation_tags} ạ. "
                        f"Nếu anh/chị cần em hỗ trợ kiểm tra thêm chi tiết các món trong đơn, cứ nhắn lại cho em nhé!"
                    )

                shipper = order_data.get("shipper_name") or "bưu tá"
                phone = f" ({order_data.get('shipper_phone')})" if order_data.get("shipper_phone") else ""
                status = order_data.get("status", "đang được vận chuyển")
                est = order_data.get("estimated_delivery", "trong ngày hôm nay")
                return (
                    f"Dạ em chào anh/chị, em đã kiểm tra thông tin đơn hàng {order_id or ''} của mình. "
                    f"Hiện đơn hàng {status} bởi {shipper}{phone} và dự kiến giao đến mình {est} {citation_tags} ạ. "
                    f"Anh/chị chú ý giữ điện thoại để nhận hàng giúp em nhé!"
                )
            return (
                f"Dạ Tiki chào anh/chị, để em hỗ trợ kiểm tra chi tiết lộ trình đơn hàng cho mình, "
                f"Bạn vui lòng cho shop xin mã đơn hàng hoặc thông tin đơn hàng nhé ạ!"
            )

        if intent in ("return_policy", "return_product"):
            return (
                f"Dạ em chào anh/chị, theo chính sách đổi trả của Tiki, quý khách được hỗ trợ đổi trả sản phẩm "
                f"trong vòng 30 ngày kể từ ngày nhận hàng đối với sản phẩm còn nguyên tem mác hoặc có lỗi kỹ thuật {citation_tags} ạ. "
                f"Anh/chị chỉ cần giữ lại hộp và phụ kiện ban đầu, bên em sẽ cho bưu tá đến tận nhà để thu hồi miễn phí cho mình ạ!"
            )

        if intent == "shipping_costs":
            return (
                f"Dạ em chào anh/chị, về cước phí vận chuyển, Tiki áp dụng biểu phí giao hàng tiêu chuẩn "
                f"và hỗ trợ miễn phí vận chuyển cho các đơn hàng đạt giá trị tối thiểu theo quy định {citation_tags} ạ. "
                f"Anh/chị có thể áp dụng thêm mã Freeship tại bước thanh toán để được giảm phí ship tối đa nhé!"
            )

        if intent in ("get_discounts", "promotion_policy"):
            return (
                f"Dạ em chào anh/chị, về chính sách ưu đãi cho đơn hàng {order_id or ''}, Tiki hiện hỗ trợ áp dụng đồng thời "
                f"nhiều loại mã ưu đãi bao gồm mã giảm giá từ sàn/nhà bán, mã miễn phí vận chuyển Freeship và điểm tích lũy Tiki Xu {citation_tags} ạ. "
                f"Nếu đơn hàng đã chuyển sang trạng thái vận chuyển, các mã giảm giá đã áp dụng sẽ được giữ nguyên theo đơn hàng anh/chị nhé!"
            )

        return (
            f"Dạ em chào anh/chị, em đã kiểm tra thông tin về yêu cầu của mình. "
            f"Dựa trên quy định hiện hành của Tiki {citation_tags}, trường hợp này sẽ được hỗ trợ xử lý nhanh chóng. "
            f"Anh/chị hỗ trợ kiểm tra lại thông báo đơn hàng hoặc phản hồi lại nếu cần em hỗ trợ thêm nhé ạ!"
        )

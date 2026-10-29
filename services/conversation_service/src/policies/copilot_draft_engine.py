"""Copilot Draft Engine (Phần 3: Bản thảo câu trả lời gợi ý của Copilot cho Nhân viên).
Assembles full 6-layer context (Input, Intent, Facts, Order Data, Memory, Policy Citations)
and generates a polite, grounded agent draft response ready for staff review and approval.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import httpx

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
    async def _call_openai_compatible(cls, prompt: str, api_key: str) -> Optional[str]:
        """Generate response via OpenAI-compatible API endpoint (e.g. ckey.vn / xah.io)."""
        base_url = os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL).rstrip("/")
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "").strip()
                        if content:
                            return content
                else:
                    print(f"[CopilotDraftEngine] OpenAI-compatible call returned status {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            print(f"[CopilotDraftEngine] OpenAI-compatible call error: {exc}")
        return None

    @classmethod
    async def _call_gemini(cls, prompt: str, api_key: str) -> Optional[str]:
        """Generate response via Google Gemini API."""
        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                    "thinkingConfig": {
                        "thinkingBudget": 0
                    },
                },
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    f"{GEMINI_URL}?key={api_key}",
                    json=payload,
                )
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates", [])
                    if candidates:
                        raw_draft = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        if raw_draft:
                            return raw_draft
                else:
                    print(f"[CopilotDraftEngine] Gemini returned status {resp.status_code}: {resp.text[:200]}")
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
2. Giải quyết trúng đích: Tận dụng trực tiếp dữ liệu đơn hàng ở mục 4 (tên khách hàng, SĐT, trạng thái, bưu cục/dự kiến giao) và lịch sử trao đổi để giải đáp cụ thể. ĐÃ CÓ ĐẦY ĐỦ THÔNG TIN ĐƠN HÀNG, TUYỆT ĐỐI KHÔNG hỏi lại những thông tin đã có (như SĐT, email, mã đơn...).
3. Căn cứ chính sách: Mỗi khi đưa ra điều kiện, thời hạn hoặc quy định, hãy trích dẫn mã tài liệu tương ứng ở ngay phía sau câu đó theo định dạng [POL-XXX].
4. Độ dài chuẩn mực: Viết ngắn gọn, súc tích trong khoảng 3 - 5 câu (hoặc gạch đầu dòng rõ ràng nếu hướng dẫn các bước), sẵn sàng để nhân viên chỉ cần đọc lướt và nhấn nút gửi cho khách.
5. Tuyệt đối không bịa đặt những điều không có trong tài liệu hoặc dữ liệu đơn hàng.
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

        provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        openai_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
        gemini_key = os.getenv("GEMINI_API_KEY", "") or GEMINI_API_KEY

        # If configured for OpenAI-compatible (e.g. ckey.vn openai-gpt-oss-20b)
        if provider == "openai_compatible" and openai_key:
            draft = await cls._call_openai_compatible(prompt, openai_key)
            if draft:
                return draft

        # If configured for Gemini or fallback
        if gemini_key and gemini_key != "your_gemini_api_key_here":
            draft = await cls._call_gemini(prompt, gemini_key)
            if draft:
                return draft

        # Secondary fallback: if Gemini was primary and failed, try OpenAI if key exists
        if openai_key and provider != "openai_compatible":
            draft = await cls._call_openai_compatible(prompt, openai_key)
            if draft:
                return draft

        # Case 3: Semantic Fallback Draft when LLMs are unavailable
        return cls._build_semantic_fallback_draft(user_query, intent, facts, order_data, citations)

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

        if intent in ("track_order", "delivery_time") and order_data:
            shipper = order_data.get("shipper_name") or "bưu tá"
            phone = f" ({order_data.get('shipper_phone')})" if order_data.get("shipper_phone") else ""
            status = order_data.get("status", "đang được vận chuyển")
            est = order_data.get("estimated_delivery", "trong ngày hôm nay")
            return (
                f"Dạ em chào anh/chị, em đã kiểm tra thông tin đơn hàng {order_id or ''} của mình. "
                f"Hiện đơn hàng {status} bởi {shipper}{phone} và dự kiến giao đến mình {est} {citation_tags} ạ. "
                f"Anh/chị chú ý giữ điện thoại để nhận hàng giúp em nhé!"
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

        return (
            f"Dạ em chào anh/chị, em đã kiểm tra thông tin về yêu cầu của mình. "
            f"Dựa trên quy định hiện hành của Tiki {citation_tags}, trường hợp này sẽ được hỗ trợ xử lý nhanh chóng. "
            f"Anh/chị hỗ trợ kiểm tra lại thông báo đơn hàng hoặc phản hồi lại nếu cần em hỗ trợ thêm nhé ạ!"
        )

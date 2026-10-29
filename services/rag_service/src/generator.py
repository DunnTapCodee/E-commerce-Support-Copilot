"""LLM Draft Generator with strict [doc_id] citation grounding and Gemini integration."""
import asyncio
import os
import time
from typing import List
import httpx

from contracts.schemas import RAGGenerateResponse, RetrievedDocument

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai-gpt-oss-20b")


class LLMGenerator:
    """Production response generator with OpenAI-compatible & Gemini support, citation requirements, and timeout."""

    def __init__(self, timeout_seconds: int = 12):
        self.timeout_seconds = timeout_seconds
    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
        ) -> RAGGenerateResponse:
        """Generate a draft and explicitly report whether fallback was used."""
        start_time = time.perf_counter()

        if not citations or any(
            not doc.is_active or not doc.content.strip()
            for doc in citations
        ):
            raise ValueError(
                "Không thể tạo bản nháp khi tài liệu rỗng, "
                "thiếu nội dung hoặc đã hết hiệu lực."
            )

        try:
            return await asyncio.wait_for(
                self._perform_generation(query, citations, start_time),
                timeout=float(self.timeout_seconds),
            )
        except asyncio.TimeoutError:
            return self._build_template_draft(
                query,
                citations,
                start_time,
                fallback_reason="llm_timeout",
            )
    
    async def _perform_generation(
        self,
        query: str,
        citations: List[RetrievedDocument],
        start_time: float,
    ) -> RAGGenerateResponse:
        """Generate with OpenAI-compatible or Gemini, falling back transparently on failure."""
        provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        openai_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
        gemini_key = os.getenv("GEMINI_API_KEY", "") or GEMINI_API_KEY

        # Strategy 1: OpenAI-compatible (ckey.vn / openai-gpt-oss-20b)
        if provider == "openai_compatible" and openai_key:
            try:
                draft_text = await self._call_openai_compatible(query, citations, openai_key)
                if draft_text:
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        generation_mode="openai_compatible",
                        fallback_reason=None,
                    )
            except Exception as exc:
                print(f"[LLMGenerator] OpenAI-compatible call failed: {exc}")

        # Strategy 2: Gemini
        if gemini_key and gemini_key != "your_gemini_api_key_here":
            try:
                draft_text = await self._call_gemini(query, citations, gemini_key)
                if draft_text:
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        generation_mode="gemini",
                        fallback_reason=None,
                    )
            except Exception as exc:
                print(f"[LLMGenerator] Gemini failed: {exc}")

        # Secondary fallback if OpenAI key exists
        if openai_key and provider != "openai_compatible":
            try:
                draft_text = await self._call_openai_compatible(query, citations, openai_key)
                if draft_text:
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        generation_mode="openai_compatible",
                        fallback_reason=None,
                    )
            except Exception as exc:
                print(f"[LLMGenerator] OpenAI fallback failed: {exc}")

        return self._build_template_draft(
            query,
            citations,
            start_time,
            fallback_reason="all_llm_providers_failed",
        )

    async def _call_openai_compatible(
        self, query: str, citations: List[RetrievedDocument], api_key: str
    ) -> str:
        """Call OpenAI-compatible chat completion."""
        base_url = os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL).rstrip("/")
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        url = f"{base_url}/chat/completions"

        docs_context = "\n\n".join(
            f"--- Tài liệu [{doc.doc_id}] ({doc.title}) ---\n{doc.content}"
            for doc in citations
        )
        prompt = (
            "Bạn là trợ lý AI chuyên nghiệp hỗ trợ nhân viên CSKH của sàn thương mại điện tử Tiki.\n"
            "Dựa trên các tài liệu chính sách dưới đây, hãy soạn thảo câu trả lời hoàn chỉnh, lịch sự bằng tiếng Việt:\n\n"
            f"{docs_context}\n\n"
            f"CÂU HỎI KHÁCH HÀNG: \"{query}\"\n\n"
            "QUY TẮC XƯNG HÔ BẮT BUỘC: Nhân viên CSKH luôn xưng 'em' và gọi khách hàng là 'anh/chị' (hoặc 'mình'). TUYỆT ĐỐI KHÔNG dùng từ 'bạn' khi xưng hô với khách hàng. Luôn mở đầu bằng 'Dạ em chào anh/chị...'.\n"
            "YÊU CẦU: Trích dẫn mã tài liệu [POL-XXX] sau mỗi thông tin/điều kiện đưa ra. Viết súc tích, lịch sự."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_seconds - 1)) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
        return ""

    async def _call_gemini(
        self, query: str, citations: List[RetrievedDocument], api_key: str
    ) -> str:
        """Send grounded prompt to Gemini 2.5 Flash."""
        docs_context = "\n\n".join(
            f"--- Tài liệu [{doc.doc_id}] ({doc.title}) ---\n{doc.content}"
            for doc in citations
        )

        prompt = f"""Bạn là trợ lý AI chuyên nghiệp hỗ trợ nhân viên Chăm sóc Khách hàng (CSKH) của sàn thương mại điện tử Tiki.
Nhiệm vụ của bạn là soạn thảo một câu trả lời hoàn chỉnh, lịch sự, chuẩn xác gửi cho khách hàng dựa trên các tài liệu chính sách được cung cấp.

TÀI LIỆU CHÍNH SÁCH ĐƯỢC CUNG CẤP:
{docs_context}

CÂU HỎI CỦA KHÁCH HÀNG:
"{query}"

YÊU CẦU BẮT BUỘC:
1. Quy tắc xưng hô BẮT BUỘC: Nhân viên CSKH luôn xưng "em" và gọi khách hàng là "anh/chị" (hoặc "mình"). TUYỆT ĐỐI KHÔNG dùng từ "bạn" khi xưng hô với khách hàng. Luôn mở đầu bằng "Dạ em chào anh/chị...".
2. Chỉ trả lời dựa trên thông tin có trong tài liệu trên. Tuyệt đối không tự suy diễn hoặc bịa đặt thông tin.
3. Với mỗi thông tin hoặc điều kiện đưa ra, hãy trích dẫn mã tài liệu tương ứng ở ngay sau thông tin đó theo định dạng [POL-XXX].
4. Giọng điệu thân thiện, nhiệt tình, chuyên nghiệp bằng tiếng Việt.
5. Trình bày rõ ràng, súc tích (có gạch đầu dòng nếu cần liệt kê các bước hoặc điều kiện).
"""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
                "thinkingConfig": {
                    "thinkingBudget": 0
                },
            }
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_seconds - 1)) as client:
            resp = await client.post(
                f"{GEMINI_API_URL}?key={api_key}",
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()

        return ""

    def _build_template_draft(
        self,
        query: str,
        citations: List[RetrievedDocument],
        start_time: float,
        fallback_reason: str = "fallback",
    ) -> RAGGenerateResponse:
        """Build a clearly labelled fallback draft from active policy documents."""
        if not citations or any(
            not doc.is_active or not doc.content.strip()
            for doc in citations
        ):
            raise ValueError(
                "Fallback bị từ chối vì tài liệu không hợp lệ."
            )

        citation_tags = " ".join(
            f"[{doc.doc_id}]" for doc in citations
        )
        policy_summaries = "\n\n".join(
            doc.content for doc in citations
        )

        draft_text = (
            "[BẢN NHÁP DỰ PHÒNG — NHÂN VIÊN PHẢI KIỂM TRA]\n"
            f"Dạ em chào anh/chị, về yêu cầu: '{query}'.\n\n"
            f"Thông tin từ tài liệu chính sách:\n{policy_summaries}\n\n"
            "Vui lòng kiểm tra nội dung và xác nhận thông tin phù hợp "
            "trước khi phản hồi khách hàng.\n"
            f"Nguồn tham khảo: {citation_tags}"
        )

        return RAGGenerateResponse(
            draft_text=draft_text,
            citations=citations,
            latency_ms=int(
                (time.perf_counter() - start_time) * 1000
            ),
            generation_mode="template_fallback",
            fallback_reason=fallback_reason,
        )

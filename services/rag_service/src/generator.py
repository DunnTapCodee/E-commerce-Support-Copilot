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


class LLMGenerator:
    """Production response generator with Gemini 2.5 Flash, citation requirements, and timeout."""

    def __init__(self, timeout_seconds: int = 8):
        self.timeout_seconds = timeout_seconds

    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
    ) -> RAGGenerateResponse:
        """Generate response with [doc_id] citations wrapped in timeout."""
        start_time = time.perf_counter()

        # Run with asyncio timeout protection
        try:
            return await asyncio.wait_for(
                self._perform_generation(query, citations, start_time),
                timeout=float(self.timeout_seconds),
            )
        except asyncio.TimeoutError:
            # Fallback to local grounded template if Gemini times out
            return self._build_template_draft(query, citations, start_time)

    async def _perform_generation(
        self, query: str, citations: List[RetrievedDocument], start_time: float
    ) -> RAGGenerateResponse:
        """Call Gemini 2.5 Flash API with grounded policy context."""
        if not citations:
            raise ValueError("Không thể tạo bản nháp khi không có tài liệu làm căn cứ.")

        # Try Gemini API if key is available
        if GEMINI_API_KEY:
            try:
                draft_text = await self._call_gemini(query, citations)
                if draft_text:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=latency_ms,
                    )
            except Exception as e:
                print(f"[LLMGenerator] Gemini call failed, falling back to local template: {e}")

        # Fallback to deterministic template generator
        return self._build_template_draft(query, citations, start_time)

    async def _call_gemini(self, query: str, citations: List[RetrievedDocument]) -> str:
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
1. Chỉ trả lời dựa trên thông tin có trong tài liệu trên. Tuyệt đối không tự suy diễn hoặc bịa đặt thông tin.
2. Với mỗi thông tin hoặc điều kiện bạn đưa ra, hãy trích dẫn mã tài liệu tương ứng ở ngay sau thông tin đó theo định dạng [POL-XXX].
3. Giọng điệu thân thiện, nhiệt tình, chuyên nghiệp bằng tiếng Việt.
4. Trình bày rõ ràng, súc tích (có gạch đầu dòng nếu cần liệt kê các bước hoặc điều kiện).
"""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 800,
            }
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_seconds - 1)) as client:
            resp = await client.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
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
        self, query: str, citations: List[RetrievedDocument], start_time: float
    ) -> RAGGenerateResponse:
        """Deterministic grounded template fallback."""
        citation_tags = " ".join(f"[{doc.doc_id}]" for doc in citations)
        policy_summaries = " ".join(f"{doc.content}" for doc in citations)

        draft_text = (
            f"Chào bạn, về yêu cầu: '{query}'. "
            f"{policy_summaries} "
            f"Nhân viên CSKH sẽ kiểm tra thêm nếu cần hỗ trợ đặc biệt. {citation_tags}"
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return RAGGenerateResponse(
            draft_text=draft_text,
            citations=citations,
            latency_ms=latency_ms,
        )


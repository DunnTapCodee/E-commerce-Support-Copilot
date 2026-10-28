"""LLM Draft Generator with strict [doc_id] citation grounding and Gemini integration."""
import asyncio
import os
import time
from typing import List
import httpx

from contracts.schemas import RAGGenerateResponse, RetrievedDocument

def get_gemini_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key and not key.startswith("your_") and len(key) > 10:
        return key
    return ""


def get_candidate_models() -> List[str]:
    configured = os.getenv("GEMINI_MODEL", "").strip()
    models = []
    if configured:
        models.append(configured)
    models.extend([
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ])
    seen = set()
    result = []
    for m in models:
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result


def get_gemini_api_url(model: str = "gemini-1.5-flash") -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMGenerator:
    """Production response generator with Gemini models, citation requirements, and resilient timeout."""

    def __init__(self, timeout_seconds: int = 15):
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
            print("[LLMGenerator] Generation timed out, falling back to template.")
            return self._build_template_draft(
                query,
                citations,
                start_time,
                fallback_reason="gemini_timeout",
            )

    async def _perform_generation(
        self,
        query: str,
        citations: List[RetrievedDocument],
        start_time: float,
    ) -> RAGGenerateResponse:
        """Generate with Gemini, falling back transparently on failure."""
        api_key = get_gemini_api_key()
        if api_key:
            try:
                draft_text = await self._call_gemini(query, citations, api_key)
                if draft_text:
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=int(
                            (time.perf_counter() - start_time) * 1000
                        ),
                        generation_mode="gemini",
                        fallback_reason=None,
                    )
                reason = "gemini_empty_response"
            except Exception as exc:
                print(f"[LLMGenerator] Gemini call failed: {exc}")
                reason = "gemini_api_error"
        else:
            reason = "api_key_not_configured"

        return self._build_template_draft(
            query,
            citations,
            start_time,
            fallback_reason=reason,
        )

    async def _call_gemini(
        self, query: str, citations: List[RetrievedDocument], api_key: str
    ) -> str:
        """Send grounded prompt to Gemini API."""
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

        async with httpx.AsyncClient(timeout=float(max(self.timeout_seconds - 2, 5))) as client:
            for model_name in get_candidate_models():
                api_url = get_gemini_api_url(model_name)
                try:
                    resp = await client.post(
                        f"{api_url}?key={api_key}",
                        json=payload,
                    )
                except Exception as req_err:
                    print(f"[LLMGenerator] Error connecting to {model_name}: {req_err}")
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                elif resp.status_code in (403, 404, 429, 500, 502, 503, 504):
                    print(f"[LLMGenerator] Model {model_name} returned {resp.status_code} (overloaded or unavailable), trying next...")
                    continue
                else:
                    print(f"[LLMGenerator] Gemini ({model_name}) returned status {resp.status_code}: {resp.text[:150]}")
                    continue

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
            f"Chào bạn, về yêu cầu: '{query}'.\n\n"
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

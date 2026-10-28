"""LLM Draft Generator with strict [doc_id] citation grounding and Gemini/DeepSeek integration."""
import asyncio
import os
import time
from pathlib import Path
from typing import List, Optional
import httpx

from contracts.schemas import RAGGenerateResponse, RetrievedDocument

# Auto-load .env if not in environment
_env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_file.exists():
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    if _k.strip() not in os.environ:
                        os.environ[_k.strip()] = _v.strip()
    except Exception:
        pass


class LLMGenerator:
    """Production response generator with Gemini Flash Lite, DeepSeek, citation requirements, and timeout."""

    def __init__(self, timeout_seconds: Optional[int] = None):
        if timeout_seconds is None:
            self.timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        else:
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
            print("[LLMGenerator] Generation timed out, falling back to local template.")
            return self._build_template_draft(query, citations, start_time)

    async def _perform_generation(
        self, query: str, citations: List[RetrievedDocument], start_time: float
    ) -> RAGGenerateResponse:
        """Call Gemini or OpenAI-compatible (DeepSeek) API with grounded policy context."""
        if not citations:
            raise ValueError("Không thể tạo bản nháp khi không có tài liệu làm căn cứ.")

        provider = os.getenv("LLM_PROVIDER", "auto").lower()
        api_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or ""
        )

        draft_text = ""
        if api_key and not api_key.startswith("your_"):
            try:
                # Detect Gemini vs OpenAI-compatible key
                is_gemini = (
                    provider == "gemini"
                    or api_key.startswith("AQ.")
                    or api_key.startswith("AIzaSy")
                )

                if is_gemini:
                    gemini_key = os.getenv("GEMINI_API_KEY") or api_key
                    draft_text = await self._call_gemini(query, citations, gemini_key)
                else:
                    draft_text = await self._call_openai_compatible(query, citations, api_key)

                if draft_text:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=latency_ms,
                    )
            except Exception as e:
                print(f"[LLMGenerator] Remote LLM call failed, falling back to local template: {e}")

        # Fallback to deterministic template generator
        return self._build_template_draft(query, citations, start_time)

    async def _call_gemini(
        self, query: str, citations: List[RetrievedDocument], api_key: str
    ) -> str:
        """Send grounded prompt to Google Gemini API."""
        model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

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
            },
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_seconds - 1), verify=False) as client:
            resp = await client.post(endpoint, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            else:
                print(f"[LLMGenerator] Gemini HTTP Error {resp.status_code}: {resp.text}")

        return ""

    async def _call_openai_compatible(
        self, query: str, citations: List[RetrievedDocument], api_key: str
    ) -> str:
        """Call DeepSeek, OpenAI or OpenAI-compatible endpoint with grounded context."""
        docs_context = "\n\n".join(
            f"--- Tài liệu [{doc.doc_id}] ({doc.title}) ---\n{doc.content}"
            for doc in citations
        )

        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp hỗ trợ nhân viên Chăm sóc Khách hàng (CSKH) của sàn thương mại điện tử Tiki.\n"
            "Nhiệm vụ của bạn là soạn thảo một câu trả lời hoàn chỉnh, lịch sự, chuẩn xác gửi cho khách hàng dựa trên các tài liệu chính sách được cung cấp.\n\n"
            "YÊU CẦU BẮT BUỘC:\n"
            "1. Chỉ trả lời dựa trên thông tin có trong tài liệu chính sách. Tuyệt đối không tự suy diễn hoặc bịa đặt thông tin.\n"
            "2. Với mỗi thông tin hoặc điều kiện đưa ra, hãy trích dẫn mã tài liệu tương ứng ở ngay sau thông tin đó theo định dạng [POL-XXX].\n"
            "3. Giọng điệu thân thiện, nhiệt tình, chuyên nghiệp bằng tiếng Việt.\n"
            "4. Trình bày rõ ràng, súc tích."
        )

        user_content = f"TÀI LIỆU CHÍNH SÁCH ĐƯỢC CUNG CẤP:\n{docs_context}\n\nCÂU HỎI CỦA KHÁCH HÀNG:\n\"{query}\""

        base_url = os.getenv("LLM_BASE_URL", "")
        model = os.getenv("LLM_MODEL", "deepseek-chat")

        if not base_url:
            if "deepseek" in model.lower() or (api_key.startswith("sk-") and len(api_key) == 67):
                base_url = "https://api.deepseek.com"
            else:
                base_url = "https://api.openai.com/v1"

        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        async with httpx.AsyncClient(timeout=float(self.timeout_seconds - 1), verify=False) as client:
            resp = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
            else:
                print(f"[LLMGenerator] OpenAI-compatible HTTP Error {resp.status_code}: {resp.text}")

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

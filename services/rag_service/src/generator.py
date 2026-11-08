"""LLM Draft Generator with strict [doc_id] citation grounding and Gemini/OpenAI integration."""
import asyncio
import os
import time
from pathlib import Path
from typing import List, Optional
import httpx

from contracts.schemas import RAGGenerateResponse, RetrievedDocument
from contracts.llm_failover import call_chat_completion_with_failover, get_available_api_keys

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
                        os.environ[_k.strip()] = _v.strip().strip('"').strip("'")
    except Exception:
        pass

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
        "gemini-flash-lite-latest",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
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


def get_gemini_api_url(model: str = "gemini-flash-lite-latest") -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "openai-gpt-oss-20b"


class LLMGenerator:
    """Production response generator with OpenAI-compatible & Gemini support, citation requirements, and timeout."""

    def __init__(self, timeout_seconds: Optional[int] = None):
        if timeout_seconds is None:
            self.timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        else:
            self.timeout_seconds = timeout_seconds

    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
    ) -> RAGGenerateResponse:
        """Entry point for draft generation with fallback."""
        start_time = time.perf_counter()

        if not citations:
            return self._build_template_draft(
                query,
                citations,
                start_time,
                fallback_reason="no_citations_available",
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
        openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or OPENAI_API_KEY
        gemini_key = get_gemini_api_key() or os.getenv("GEMINI_API_KEY", "")

        # Strategy 1: OpenAI-compatible (ckey.vn / xah.io) with multi-key failover
        if (provider in ("openai_compatible", "openai", "auto")) and (get_available_api_keys() or openai_key):
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
                print(f"[LLMGenerator] OpenAI-compatible call failed: {exc}. Trying fallback...")

        # Strategy 2: Gemini Direct Generation with candidate model fallback
        if (provider in ("gemini", "auto", "openai_compatible")) and gemini_key:
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
                print(f"[LLMGenerator] Gemini call failed: {exc}. Trying fallback...")

        # Secondary fallback if OpenAI key exists
        if (openai_key or get_available_api_keys()) and provider == "gemini":
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

        # Strategy 3: Template-based fallback
        return self._build_template_draft(
            query,
            citations,
            start_time,
            fallback_reason="all_llm_providers_failed",
        )

    async def _call_openai_compatible(
        self, query: str, citations: List[RetrievedDocument], api_key: str = ""
    ) -> str:
        """Call OpenAI-compatible chat completion with automatic multi-key failover."""
        model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or OPENAI_MODEL
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

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Bạn là trợ lý AI Copilot CSKH Tiki. Hãy suy nghĩ ngắn gọn và trả lời trực tiếp bằng tiếng Việt chuẩn mực CSKH."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }

        try:
            res_data = await call_chat_completion_with_failover(payload, timeout=25.0)
            if res_data and "choices" in res_data and res_data["choices"]:
                return res_data["choices"][0].get("message", {}).get("content", "").strip()
        except Exception as exc:
            print(f"[LLMGenerator] OpenAI-compatible call error: {exc}")
        return ""

    async def _call_gemini(
        self, query: str, citations: List[RetrievedDocument], api_key: str
    ) -> str:
        """Send grounded prompt to Gemini with resilient multi-model failover."""
        docs_context = "\n\n".join(
            f"--- Tài liệu [{doc.doc_id}] ({doc.title}) ---\n{doc.content}"
            for doc in citations
        )

        prompt = f"""Bạn là trợ lý AI chuyên nghiệp hỗ trợ nhân viên chăm sóc khách hàng sàn thương mại điện tử.
Hãy soạn thảo một câu trả lời hoàn chỉnh, chuẩn xác và chuyên nghiệp cho câu hỏi của khách hàng, dựa HOÀN TOÀN vào các tài liệu chính sách được cung cấp dưới đây.

CÁC TÀI LIỆU CHÍNH SÁCH ĐƯỢC CUNG CẤP:
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
            }
        }

        async with httpx.AsyncClient(timeout=float(max(self.timeout_seconds - 2, 5)), verify=False) as client:
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
                    print(f"[LLMGenerator] Model {model_name} returned {resp.status_code}, trying next...")
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
        fallback_reason: Optional[str] = None,
    ) -> RAGGenerateResponse:
        """Deterministic, citation-grounded fallback template."""
        policy_summaries = "\n".join(
            f"• [{doc.doc_id}] {doc.title}: {doc.content[:150]}..."
            for doc in citations
        )

        draft_text = (
            "[BẢN NHÁP DỰ PHÒNG — NHÂN VIÊN PHẢI KIỂM TRA]\n"
            f"Dạ em chào anh/chị, về yêu cầu: '{query}'.\n\n"
            f"Thông tin từ tài liệu chính sách:\n{policy_summaries}\n\n"
            "Vui lòng kiểm tra nội dung và xác nhận thông tin phù hợp "
            "trước khi phản hồi khách hàng.\n"
            "Trân trọng hỗ trợ!"
        )

        return RAGGenerateResponse(
            draft_text=draft_text,
            citations=citations,
            latency_ms=int((time.perf_counter() - start_time) * 1000),
            generation_mode="template_fallback",
            fallback_reason=fallback_reason,
        )

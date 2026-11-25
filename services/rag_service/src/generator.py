"""LLM Draft Generator with strict `[doc_id]` citation grounding via OpenAI-compatible CKEY.VN endpoint."""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import List, Optional

from contracts.llm_failover import (
    DEFAULT_OPENAI_BASE_URL,
    call_chat_completion_with_failover,
    get_available_api_keys,
    get_default_openai_model,
)
from contracts.schemas import RAGGenerateResponse, RetrievedDocument

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

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
OPENAI_MODEL = get_default_openai_model()


class LLMGenerator:
    """Production RAG draft generator using OpenAI-compatible failover and citation-grounded fallback."""

    def __init__(self, timeout_seconds: Optional[int] = None):
        if timeout_seconds is None:
            self.timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        else:
            self.timeout_seconds = timeout_seconds

    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
    ) -> RAGGenerateResponse:
        """Entry point for draft generation with deterministic fallback."""
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
        """Generate grounded draft via OpenAI-compatible CKEY.VN endpoint, falling back cleanly on failure."""
        provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        if provider in ("openai_compatible", "openai", "auto") and get_available_api_keys():
            try:
                draft_text = await self._call_openai_compatible(query, citations)
                if draft_text:
                    return RAGGenerateResponse(
                        draft_text=draft_text,
                        citations=citations,
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        generation_mode="openai_compatible",
                        fallback_reason=None,
                    )
            except Exception as exc:
                print(f"[LLMGenerator] OpenAI-compatible call failed: {exc}. Using grounded template fallback.")

        return self._build_template_draft(
            query,
            citations,
            start_time,
            fallback_reason="all_llm_providers_failed",
        )

    async def _call_openai_compatible(
        self, query: str, citations: List[RetrievedDocument]
    ) -> str:
        """Call OpenAI-compatible chat completion with automatic multi-key failover."""
        model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or OPENAI_MODEL
        docs_context = "\n\n".join(
            f"--- Tài liệu [{doc.doc_id}] ({doc.title}) ---\n{doc.content}"
            for doc in citations
        )
        prompt = (
            "Bạn là trợ lý AI chuyên nghiệp hỗ trợ nhân viên CSKH của sàn thương mại điện tử Tiki.\n"
            "Dựa trên các tài liệu chính sách dưới đây, hãy soạn thảo một câu trả lời hoàn chỉnh, chuẩn xác, lịch sự bằng tiếng Việt:\n\n"
            f"{docs_context}\n\n"
            f'CÂU HỎI CỦA KHÁCH HÀNG: "{query}"\n\n'
            "QUY TẮC BẮT BUỘC:\n"
            "1. XƯNG HÔ: Luôn xưng 'em' và gọi khách là 'anh/chị' (hoặc 'mình'). TUYỆT ĐỐI KHÔNG dùng từ 'bạn'. Luôn mở đầu: 'Dạ em chào anh/chị...'.\n"
            "2. CĂN CỨ TÀI LIỆU (GROUNDING): Mỗi thông tin, mốc thời gian, tỷ lệ hoàn tiền hoặc điều kiện đưa ra BẮT BUỘC kèm mã tài liệu tương ứng [POL-XXX] ngay phía sau.\n"
            "3. ĐỘ DÀI: Súc tích, dưới 130 từ, trình bày gạch đầu dòng rõ ràng nếu có từ 2 điều kiện trở lên.\n"
            "4. CHỐNG BỊA ĐẶT (NO HALLUCINATION): Nếu thông tin không có trong tài liệu, thông báo rõ ràng: 'Dạ hiện tại tài liệu chưa có quy định cụ thể cho trường hợp này, em xin phép kiểm tra lại và phản hồi mình sau nhé ạ'. Tuyệt đối không tự suy diễn chính sách."
        )

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
            "max_tokens": 1200,
        }

        try:
            res_data = await call_chat_completion_with_failover(payload, timeout=25.0)
            if res_data and "choices" in res_data and res_data["choices"]:
                return (res_data["choices"][0].get("message", {}).get("content") or "").strip()
        except Exception as exc:
            print(f"[LLMGenerator] OpenAI-compatible call error: {exc}")
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

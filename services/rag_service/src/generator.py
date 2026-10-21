"""LLM Draft Generator with strict [doc_id] citation grounding and 8s timeout guarantee."""
import asyncio
import time
from typing import List

from contracts.schemas import RAGGenerateResponse, RetrievedDocument


class LLMGenerator:
    """Production response generator with citation requirements and strict timeout."""

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
            raise TimeoutError(f"LLM generation exceeded timeout of {self.timeout_seconds} seconds")

    async def _perform_generation(
        self, query: str, citations: List[RetrievedDocument], start_time: float
    ) -> RAGGenerateResponse:
        """Simulate fast, grounded generation citing all retrieved documents."""
        if not citations:
            raise ValueError("Không thể tạo bản nháp khi không có tài liệu làm căn cứ.")

        # Grounded response format with explicit [doc_id] tags
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

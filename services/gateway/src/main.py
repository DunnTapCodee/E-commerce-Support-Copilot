"""API Gateway & Central Ingress Router on Port 8000."""
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import (
    AuditLogCreate,
    GatewayResponse,
    GuardrailResult,
    HumanActionUpdate,
    IntentPredictionResponse,
    QueryRequest,
    RetrievedDocument,
    RawPolicyFilterRequest,
    PolicyCreateRequest,
    PolicyRollbackRequest,
    ToolCallRecord,
)
from services.gateway.src.clients import MicroserviceClients
from services.gateway.src.config import (
    CONVERSATION_SERVICE_URL,
    FALLBACK_EXPIRED_POLICY_MESSAGE,
    FALLBACK_FINANCIAL_MESSAGE,
    FALLBACK_HALLUCINATION_MESSAGE,
    FALLBACK_HUMAN_MESSAGE,
    FALLBACK_NO_ACTIVE_POLICY_MESSAGE,
    FALLBACK_UNCERTAIN_MESSAGE,
)
from services.gateway.src.guardrails import (
    evaluate_financial_guard,
    evaluate_intent_guard,
    evaluate_policy_guard,
    evaluate_response_faithfulness,
)

app = FastAPI(
    title="API Gateway Orchestrator",
    description="Central Gateway coordinating distributed ML, RAG, Safety, Telemetry, and Conversation Service",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

clients = MicroserviceClients()


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "gateway",
        "port": int(os.getenv("PORT", 8000)),
    }


@app.post("/api/v1/copilot/query", response_model=GatewayResponse)
async def process_copilot_query(
    request: QueryRequest, background_tasks: BackgroundTasks
):
    """Central Ingress endpoint:
    1. Primary path: Delegate 100% of multi-turn dialogue to Conversation Service.
    2. Fallback path: Standalone degraded response if Conversation Service is unreachable.
    """
    start_time = time.perf_counter()
    interaction_id = str(uuid.uuid4())
    customer_query = request.query.strip()
    customer_id = request.customer_id or "demo-customer"
    generation_mode = "not_generated"
    citations: List[RetrievedDocument] = []
    draft_text = ""
    order_data: Optional[Dict[str, Any]] = None

    # Delegate to Conversation Service (Primary Path)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as http_client:
            resp = await http_client.post(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/chat",
                json=request.model_dump(),
            )
            if resp.status_code == 200:
                return GatewayResponse(**resp.json())
    except Exception as exc:
        print(f"[Gateway] Conversation Service unreachable: {exc}. Running graceful gateway fallback.")

    # Graceful Fallback Pipeline (if Conversation Service is down)
    intent_service_error = None
    try:
        intent_resp: IntentPredictionResponse = await clients.predict_intent(customer_query)
    except Exception as exc:
        intent_service_error = str(exc)
        print(f"[Gateway] Intent service unavailable: {exc}")
        intent_resp = IntentPredictionResponse(
            intent="unknown_query",
            confidence=0.0,
            is_in_scope=False,
            all_probabilities={},
        )

    # Order lookup fallback
    tool_records: List[ToolCallRecord] = []
    order_match = re.search(r"\bORD-[A-Za-z0-9-]+\b", customer_query, re.IGNORECASE)
    lookup_key = order_match.group(0) if order_match else customer_id
    if lookup_key:
        try:
            order_data = await clients.lookup_order(lookup_key)
        except Exception:
            pass

    # Intent Guardrail Check
    intent_guard = evaluate_intent_guard(intent_resp)
    if intent_service_error:
        intent_guard = GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=(
                "Intent Service không khả dụng. "
                "Không thể xác định ý định an toàn; "
                "cần nhân viên xử lý. "
                f"Chi tiết lỗi: {intent_service_error}"
            ),
        )

    if not intent_guard.allow_llm:
        guardrail_decision = intent_guard
        if intent_service_error:
            draft_text = (
                "[CẦN NHÂN VIÊN XỬ LÝ: Không thể xác định ý định "
                "do dịch vụ phân loại đang gặp sự cố.]"
            )
        elif intent_resp.intent == "human_agent":
            draft_text = FALLBACK_HUMAN_MESSAGE
        else:
            draft_text = FALLBACK_UNCERTAIN_MESSAGE

        audit_payload = AuditLogCreate(
            interaction_id=interaction_id,
            customer_query=customer_query,
            predicted_intent=intent_resp.intent,
            intent_confidence=intent_resp.confidence,
            guardrail_action=guardrail_decision.action_type,
            retrieved_doc_ids="",
            raw_draft_text=draft_text,
            latency_ms=int((time.perf_counter() - start_time) * 1000),
        )
        background_tasks.add_task(clients.record_audit_log, audit_payload)

        return GatewayResponse(
            interaction_id=interaction_id,
            intent=intent_resp,
            guardrail=guardrail_decision,
            citations=[],
            draft_text=draft_text,
            order_data=order_data,
            tool_calls=tool_records,
            generation_mode=generation_mode,
            suggested_reply=draft_text,
        )

    # Financial Guard Check
    financial_guard = evaluate_financial_guard(intent_resp.intent)
    if financial_guard and not financial_guard.allow_llm:
        guardrail_decision = financial_guard
        draft_text = FALLBACK_FINANCIAL_MESSAGE
        generation_mode = "blocked_financial"
        if order_data:
            order_summary = "; ".join(f"{k}: {v}" for k, v in order_data.items() if k not in ("items", "shipping_timeline"))
            draft_text += f"\n\n[Dữ liệu đơn đối soát]: {order_summary}"

        audit_payload = AuditLogCreate(
            interaction_id=interaction_id,
            customer_query=customer_query,
            predicted_intent=intent_resp.intent,
            intent_confidence=intent_resp.confidence,
            guardrail_action=guardrail_decision.action_type,
            retrieved_doc_ids="",
            raw_draft_text=draft_text,
            latency_ms=int((time.perf_counter() - start_time) * 1000),
        )
        background_tasks.add_task(clients.record_audit_log, audit_payload)

        return GatewayResponse(
            interaction_id=interaction_id,
            intent=intent_resp,
            guardrail=guardrail_decision,
            citations=[],
            draft_text=draft_text,
            order_data=order_data,
            tool_calls=tool_records,
            generation_mode=generation_mode,
            suggested_reply=draft_text,
        )

    # Retrieval
    try:
        citations = await clients.retrieve_policies(
            query=customer_query,
            intent=intent_resp.intent,
            top_k=3,
        )
    except Exception as exc:
        print(f"[Gateway] RAG retrieve error: {exc}")
        citations = []

    # Policy Guardrail Check
    policy_guard = evaluate_policy_guard(citations)
    if not policy_guard.allow_llm:
        guardrail_decision = policy_guard
        draft_text = (
            FALLBACK_EXPIRED_POLICY_MESSAGE
            if policy_guard.temporal_status == "EXPIRED"
            else FALLBACK_NO_ACTIVE_POLICY_MESSAGE
        )
        generation_mode = "blocked_policy"

        audit_payload = AuditLogCreate(
            interaction_id=interaction_id,
            customer_query=customer_query,
            predicted_intent=intent_resp.intent,
            intent_confidence=intent_resp.confidence,
            guardrail_action=guardrail_decision.action_type,
            retrieved_doc_ids=",".join(d.doc_id for d in citations),
            raw_draft_text=draft_text,
            latency_ms=int((time.perf_counter() - start_time) * 1000),
        )
        background_tasks.add_task(clients.record_audit_log, audit_payload)

        return GatewayResponse(
            interaction_id=interaction_id,
            intent=intent_resp,
            guardrail=guardrail_decision,
            citations=citations,
            draft_text=draft_text,
            order_data=order_data,
            tool_calls=tool_records,
            generation_mode=generation_mode,
            suggested_reply=draft_text,
        )

    # Generation via RAG Service
    try:
        rag_resp = await clients.generate_draft(
            query=customer_query, citations=citations
        )
        draft_text = rag_resp.draft_text
        generation_mode = rag_resp.generation_mode
    except Exception as exc:
        print(f"[Gateway] RAG generate error: {exc}")
        draft_text = FALLBACK_UNCERTAIN_MESSAGE
        generation_mode = "error_fallback"

    # Faithfulness Check
    faithfulness_guard = evaluate_response_faithfulness(
        draft_text=draft_text,
        citations=citations,
        customer_query=customer_query,
        order_data=order_data,
    )
    if not faithfulness_guard.allow_llm:
        guardrail_decision = faithfulness_guard
        generation_mode = "blocked_hallucination"
        draft_text = (
            f"{FALLBACK_HALLUCINATION_MESSAGE}\n"
            f"[Chi tiết kiểm tra an toàn NLI]: {faithfulness_guard.reason}"
        )
    else:
        guardrail_decision = GuardrailResult(
            allow_llm=True,
            action_type="APPROVED_BY_GUARDRAILS",
            reason="Tất cả các trạm kiểm soát guardrail đã thông qua thành công.",
        )

    # Async audit log
    audit_payload = AuditLogCreate(
        interaction_id=interaction_id,
        customer_query=customer_query,
        predicted_intent=intent_resp.intent,
        intent_confidence=intent_resp.confidence,
        guardrail_action=guardrail_decision.action_type,
        retrieved_doc_ids=",".join(d.doc_id for d in citations),
        raw_draft_text=draft_text,
        latency_ms=int((time.perf_counter() - start_time) * 1000),
    )
    background_tasks.add_task(clients.record_audit_log, audit_payload)

    return GatewayResponse(
        interaction_id=interaction_id,
        intent=intent_resp,
        guardrail=guardrail_decision,
        citations=citations,
        draft_text=draft_text,
        order_data=order_data,
        tool_calls=tool_records,
        generation_mode=generation_mode,
        suggested_reply=draft_text,
    )


@app.post("/api/v1/copilot/action")
async def record_human_action(payload: HumanActionUpdate):
    """Forward CS Support agent action review to telemetry service."""
    try:
        return await clients.record_human_action(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record human action update: {exc}",
        )


@app.get("/api/v1/copilot/stats")
async def get_dashboard_stats():
    """Proxy audit statistics from telemetry service for the UI dashboard."""
    return await clients.get_audit_stats()


async def _proxy_rag_call(coro):
    """Safely execute downstream calls to rag_service with structured error mapping."""
    try:
        return await coro
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể kết nối đến RAG Service (port 8002). Vui lòng kiểm tra RAG service đang chạy.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Quá thời gian chờ phản hồi từ RAG Service (Timeout).",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi downstream: {str(exc)}",
        )


@app.post("/api/v1/copilot/policy/filter")
async def proxy_policy_filter(request: RawPolicyFilterRequest):
    """Proxy: extract structured policy from raw text via rag_service LLM parser."""
    return await _proxy_rag_call(clients.filter_policy(request))


@app.post("/api/v1/copilot/policy/create")
async def proxy_policy_create(request: PolicyCreateRequest):
    """Proxy: persist a confirmed policy into KB and re-index via rag_service."""
    return await _proxy_rag_call(clients.create_policy(request))


@app.get("/api/v1/copilot/policies")
async def proxy_list_policies():
    """Proxy: list all policies in the Knowledge Base from rag_service."""
    return await _proxy_rag_call(clients.list_policies())


@app.patch("/api/v1/copilot/policies/{doc_id}")
async def proxy_update_policy(doc_id: str, updates: dict):
    """Proxy: partially update a policy (e.g. flip to superseded) via rag_service."""
    return await _proxy_rag_call(clients.update_policy(doc_id, updates))


@app.get("/api/v1/copilot/policies/audit-logs")
async def proxy_list_policy_audit_logs():
    """Proxy: list all policy audit log entries from rag_service."""
    return await _proxy_rag_call(clients.list_policy_audit_logs())


@app.post("/api/v1/copilot/policies/rollback")
async def proxy_rollback_policy(request: PolicyRollbackRequest):
    """Proxy: rollback a policy change via rag_service."""
    return await _proxy_rag_call(clients.rollback_policy(request))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("services.gateway.src.main:app", host="0.0.0.0", port=port, reload=False)

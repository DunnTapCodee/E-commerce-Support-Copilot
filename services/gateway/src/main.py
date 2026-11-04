"""API Gateway & Central Ingress Router on Port 8000."""
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
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
    ToolCallRecord,
)
from services.gateway.src.clients import MicroserviceClients
from services.gateway.src.config import (
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
    """Gateway health check."""
    return {"status": "healthy", "service": "gateway", "port": 8000}


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
    citations: list[RetrievedDocument] = []
    draft_text = ""
    order_data: Optional[Dict[str, Any]] = None

    # Delegate to Conversation Service (Primary Path)
    try:
        import httpx
        from services.gateway.src.config import CONVERSATION_SERVICE_URL
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
    tool_context: str = ""
    if customer_id:
        try:
            order_data = await clients.lookup_order(customer_id)
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
    financial_guard = evaluate_financial_guard(intent_resp.intent, order_data)
    if not financial_guard.allow_llm:
        guardrail_decision = financial_guard
        draft_text = FALLBACK_FINANCIAL_MESSAGE
        generation_mode = "blocked_financial"

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
        draft=draft_text,
        citations=citations,
        order_data=order_data,
    )
    if not faithfulness_guard.allow_llm:
        guardrail_decision = faithfulness_guard
        draft_text = FALLBACK_HALLUCINATION_MESSAGE
        generation_mode = "blocked_hallucination"
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
    """Update telemetry record with actual CS support human agent decision."""
    success = await clients.record_human_action(payload)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record human action update",
        )
    return {"status": "recorded", "interaction_id": payload.interaction_id}

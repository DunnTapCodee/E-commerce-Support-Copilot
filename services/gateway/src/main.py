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
    CONVERSATION_SERVICE_URL,
    FALLBACK_FINANCIAL_MESSAGE,
    FALLBACK_HUMAN_MESSAGE,
    FALLBACK_UNCERTAIN_MESSAGE,
    INTENT_CONFIDENCE_THRESHOLD,
)
from services.gateway.src.guardrails import (
    evaluate_financial_guard,
    evaluate_intent_guard,
    evaluate_policy_guard,
    evaluate_response_faithfulness,
)
from services.gateway.src.routers.policy_router import router as policy_router

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

# Mount Modular Routers
app.include_router(policy_router)


@app.get("/health")
def health_check():
    """Health check for API Gateway."""
    return {
        "status": "healthy",
        "service": "api_gateway",
        "ingress_target": "conversation_service",
        "policy_target": "document_service",
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
    customer_id = request.customer_id
    generation_mode = "unknown"
    citations: List[RetrievedDocument] = []
    draft_text = ""
    order_data: Optional[Dict[str, Any]] = None

    # Delegate to Conversation Service (Primary Path)
    try:
        import httpx
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
                "Intent classification service unavailable. "
                "Fail-closed safe escalation. "
                f"Chi tiết lỗi: {intent_service_error}"
            ),
        )

    if not intent_guard.allow_llm:
        guardrail_decision = intent_guard
        if intent_service_error:
            draft_text = (
                "[CẦN NHÂN VIÊN XỬ LÝ: Không thể xác định ý định "
                "do dịch vụ AI tạm gián đoạn. Vui lòng hỗ trợ khách hàng.]"
            )
        elif intent_resp.intent == "human_agent":
            draft_text = FALLBACK_HUMAN_MESSAGE
        else:
            draft_text = (
                f"{FALLBACK_UNCERTAIN_MESSAGE} "
                f"(Dự đoán: {intent_resp.intent}, Tin cậy: {intent_resp.confidence:.0%})"
            )
        generation_mode = "blocked_intent_guard"
    else:
        # Financial Guard Check
        financial_guard = evaluate_financial_guard(intent_resp.intent)
        if financial_guard and not financial_guard.allow_llm:
            guardrail_decision = financial_guard
            draft_text = FALLBACK_FINANCIAL_MESSAGE
            generation_mode = "blocked_financial_guard"
        else:
            # Policy Retrieval
            try:
                citations = await clients.retrieve_policies(
                    customer_query, intent=intent_resp.intent, top_k=3, filter_active_only=True
                )
            except Exception as exc:
                print(f"[Gateway] RAG retrieve failed: {exc}")
                citations = []

            policy_guard = evaluate_policy_guard(citations)
            if not policy_guard.allow_llm:
                guardrail_decision = policy_guard
                draft_text = f"[Cần nhân viên xử lý: {policy_guard.reason}]"
                generation_mode = "blocked_policy_guard"
            else:
                try:
                    gen_resp = await clients.generate_draft(customer_query, citations)
                    draft_text = gen_resp.draft_text
                    generation_mode = gen_resp.generation_mode

                    output_guard = evaluate_response_faithfulness(
                        draft_text, citations, order_data=order_data
                    )
                    guardrail_decision = output_guard
                    if not output_guard.allow_llm:
                        draft_text = f"[Cần nhân viên xử lý: {output_guard.reason}]"
                        generation_mode = "blocked_faithfulness_guard"
                except Exception as exc:
                    guardrail_decision = GuardrailResult(
                        allow_llm=False,
                        action_type="ESCALATE_HUMAN",
                        reason=f"LLM Generation service error: {str(exc)}",
                    )
                    draft_text = "[Cần nhân viên xử lý: Lỗi dịch vụ sinh bản nháp an toàn.]"

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
    background_tasks.add_task(clients.log_telemetry, audit_payload)

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


@app.get("/api/v1/copilot/stats")
async def get_dashboard_stats():
    """Proxy audit statistics from telemetry service for the UI dashboard."""
    return await clients.get_audit_stats()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("services.gateway.src.main:app", host="0.0.0.0", port=port, reload=False)

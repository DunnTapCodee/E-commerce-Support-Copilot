"""API Gateway & Central State Machine Orchestrator on Port 8000."""
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
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
)
from services.gateway.src.clients import MicroserviceClients
from services.gateway.src.config import (
    FALLBACK_FINANCIAL_MESSAGE,
    FALLBACK_HUMAN_MESSAGE,
    FALLBACK_NO_ACTIVE_POLICY_MESSAGE,
    FALLBACK_UNCERTAIN_MESSAGE,
)
from services.gateway.src.guardrails import (
    evaluate_financial_guard,
    evaluate_intent_guard,
    evaluate_policy_guard,
)

app = FastAPI(
    title="API Gateway Orchestrator",
    description="Central Gateway coordinating distributed ML, RAG, Safety and Telemetry services",
    version="1.0.0",
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
    """Central Orchestrator endpoint executing state machine:
    1. Call intent_service:8001/predict.
    2. Guardrail 1: Confidence (< 0.60) / scope check -> ESCALATE_HUMAN.
    3. Guardrail 2: Refund / payment check -> DIRECT_REFUND_FORM + fetch mock order.
    4. Call rag_service:8002/retrieve.
    5. Guardrail 3: Policy validity / active version check -> ESCALATE_HUMAN if expired.
    6. Call rag_service:8002/generate.
    7. Async telemetry audit log via telemetry_service:8003.
    """
    start_time = time.perf_counter()
    interaction_id = str(uuid.uuid4())
    customer_query = request.query.strip()
    customer_id = request.customer_id or "demo-customer"

    # Step 1: Predict Intent
    try:
        intent_resp: IntentPredictionResponse = await clients.predict_intent(customer_query)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Intent service unavailable: {str(exc)}",
        )

    guardrail_decision: GuardrailResult
    citations: list[RetrievedDocument] = []
    draft_text: str = ""
    order_data: Optional[Dict[str, Any]] = None

    # Step 2: Intent Guardrail Check
    intent_guard = evaluate_intent_guard(intent_resp)
    if not intent_guard.allow_llm:
        guardrail_decision = intent_guard
        if intent_resp.intent == "human_agent":
            draft_text = FALLBACK_HUMAN_MESSAGE
        else:
            draft_text = FALLBACK_UNCERTAIN_MESSAGE

    else:
        # Step 3: Financial Guardrail Check
        financial_guard = evaluate_financial_guard(intent_resp.intent)
        if financial_guard and not financial_guard.allow_llm:
            guardrail_decision = financial_guard
            # Extract specific order_id if customer mentioned one in query
            lookup_key = customer_id
            for token in customer_query.split():
                clean_tok = token.strip(",.?!:;\"'()[]{}")
                if clean_tok.upper().startswith("ORD-"):
                    lookup_key = clean_tok
                    break
            order_data = await clients.lookup_order(lookup_key)
            draft_text = FALLBACK_FINANCIAL_MESSAGE
            if order_data:
                order_summary = "; ".join(f"{k}: {v}" for k, v in order_data.items() if k not in ("items", "shipping_timeline"))
                draft_text += f"\n\n[Dữ liệu đơn đối soát]: {order_summary}"

        else:
            # Step 4: Knowledge Retrieval
            try:
                citations = await clients.retrieve_policies(
                    query=customer_query, intent=intent_resp.intent, top_k=3
                )
            except Exception as exc:
                citations = []

            # Step 5: Policy Guardrail Check
            policy_guard = evaluate_policy_guard(citations)
            if not policy_guard.allow_llm:
                guardrail_decision = policy_guard
                draft_text = FALLBACK_NO_ACTIVE_POLICY_MESSAGE
            else:
                # Step 6: LLM Generation
                guardrail_decision = policy_guard
                try:
                    gen_resp = await clients.generate_draft(customer_query, citations)
                    draft_text = gen_resp.draft_text
                except Exception as exc:
                    guardrail_decision = GuardrailResult(
                        allow_llm=False,
                        action_type="ESCALATE_HUMAN",
                        reason=f"LLM Generation service error: {str(exc)}",
                    )
                    draft_text = "[Cần nhân viên xử lý: Lỗi dịch vụ sinh bản nháp an toàn.]"

    total_latency_ms = int((time.perf_counter() - start_time) * 1000)

    # Step 7: Asynchronous Telemetry Audit Log
    log_record = AuditLogCreate(
        interaction_id=interaction_id,
        customer_query=customer_query,
        predicted_intent=intent_resp.intent,
        intent_confidence=intent_resp.confidence,
        guardrail_action=guardrail_decision.action_type,
        retrieved_doc_ids=",".join(doc.doc_id for doc in citations),
        raw_draft_text=draft_text,
        latency_ms=total_latency_ms,
    )
    background_tasks.add_task(clients.log_telemetry, log_record)

    return GatewayResponse(
        interaction_id=interaction_id,
        intent=intent_resp,
        guardrail=guardrail_decision,
        citations=citations,
        draft_text=draft_text,
        order_data=order_data,
    )


@app.post("/api/v1/copilot/action")
async def record_human_action(action_payload: HumanActionUpdate):
    """Forward CS Support agent action review to telemetry service."""
    return await clients.record_human_action(action_payload)


@app.get("/api/v1/copilot/stats")
async def get_dashboard_stats():
    """Proxy audit statistics from telemetry service for the UI dashboard."""
    return await clients.get_audit_stats()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("services.gateway.src.main:app", host="0.0.0.0", port=port, reload=False)

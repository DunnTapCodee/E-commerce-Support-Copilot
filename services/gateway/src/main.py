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
    5. Guardrail 3 (Temporal Policy Guard): Policy validity / expiration check -> ESCALATE_HUMAN if expired.
    6. Call rag_service:8002/generate.
    6.5. Guardrail 4 (Output Guardrail): Response Faithfulness / NLI Entailment Hallucination check.
    7. Async telemetry audit log via telemetry_service:8003.
    """
    start_time = time.perf_counter()
    interaction_id = str(uuid.uuid4())
    customer_query = request.query.strip()
    customer_id = request.customer_id or "demo-customer"
    generation_mode = "not_generated"
    citations: list[RetrievedDocument] = []
    draft_text = ""
    order_data: Optional[Dict[str, Any]] = None

    # Delegate to Conversation Service if available
    try:
        import httpx
        from services.gateway.src.config import CONVERSATION_SERVICE_URL
        async with httpx.AsyncClient(timeout=12.0) as http_client:
            resp = await http_client.post(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/chat",
                json=request.model_dump(),
            )
            if resp.status_code == 200:
                return GatewayResponse(**resp.json())
    except Exception as exc:
        pass  # Fall back to local gateway orchestration pipeline

    # Step 1: Predict Intent
    intent_service_error = None

    try:
        intent_resp: IntentPredictionResponse = (
            await clients.predict_intent(customer_query)
        )
    except Exception as exc:
        intent_service_error = str(exc)
        print(f"[Gateway] Intent service unavailable: {exc}")

        # Fail closed: không có dự đoán tin cậy thì không gọi LLM.
        intent_resp = IntentPredictionResponse(
            intent="unknown_query",
            confidence=0.0,
            is_in_scope=False,
            all_probabilities={},
        )

    # Step 2: Intent Guardrail Check
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

    else:
        # Chỉ tra cứu đơn hàng khi intent đã vượt qua guardrail.
        # Ưu tiên mã đơn hàng có dạng ORD-... trong câu hỏi.
        import re

        order_match = re.search(
            r"\bORD-[A-Za-z0-9-]+\b",
            customer_query,
            re.IGNORECASE,
        )

        lookup_key = order_match.group(0) if order_match else customer_id

        try:
            order_data = await clients.lookup_order(lookup_key)
        except Exception as exc:
            print(f"[Gateway] Order lookup failed: {exc}")
            order_data = None

        # Step 3: Financial Guardrail Check
        financial_guard = evaluate_financial_guard(intent_resp.intent)
        if financial_guard and not financial_guard.allow_llm:
            guardrail_decision = financial_guard
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

            # Step 5: Temporal Policy Guardrail Check
            policy_guard = evaluate_policy_guard(citations)
            if not policy_guard.allow_llm:
                guardrail_decision = policy_guard
                if policy_guard.temporal_status == "EXPIRED":
                    draft_text = f"{FALLBACK_EXPIRED_POLICY_MESSAGE}\n[Lý do]: {policy_guard.reason}"
                else:
                    draft_text = FALLBACK_NO_ACTIVE_POLICY_MESSAGE
            else:
                # Step 6: LLM Generation
                guardrail_decision = policy_guard
                try:
                    generation_prompt = customer_query
                    if order_data:
                        order_details = "; ".join(f"{k}: {v}" for k, v in order_data.items() if k not in ("items", "shipping_timeline"))
                        generation_prompt += f"\n[Thông tin thực tế của đơn hàng từ hệ thống: {order_details}]"

                    gen_resp = await clients.generate_draft(generation_prompt, citations,)
                    draft_text = gen_resp.draft_text
                    generation_mode = gen_resp.generation_mode

                    if generation_mode == "template_fallback":
                        print(
                            "[Gateway] RAG dùng bản nháp dự phòng. "
                            f"Lý do: {gen_resp.fallback_reason}"
                        )

                    # Step 6.5: Response Faithfulness & Hallucination Guardrail Check (NLI Entailment)
                    faithfulness_guard = evaluate_response_faithfulness(draft_text, citations)
                    if not faithfulness_guard.allow_llm:
                        guardrail_decision = faithfulness_guard
                        generation_mode = "blocked_hallucination"
                        draft_text = (
                            f"{FALLBACK_HALLUCINATION_MESSAGE}\n"
                            f"[Chi tiết kiểm tra an toàn NLI]: {faithfulness_guard.reason}"
                        )
                    else:
                        guardrail_decision = faithfulness_guard

                except Exception as exc:
                    generation_mode = "not_generated"
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
        generation_mode=generation_mode,
        suggested_reply=draft_text,
        customer_acknowledgement="Dạ em đã ghi nhận thông tin của bạn và đang kiểm tra hỗ trợ ngay đây ạ!",
    )


@app.post("/api/v1/copilot/action")
async def record_human_action(action_payload: HumanActionUpdate):
    """Forward CS Support agent action review to telemetry service."""
    return await clients.record_human_action(action_payload)


@app.get("/api/v1/copilot/stats")
async def get_dashboard_stats():
    """Proxy audit statistics from telemetry service for the UI dashboard."""
    return await clients.get_audit_stats()


@app.post("/api/v1/copilot/handover")
async def toggle_live_chat_handover(payload: dict):
    """Proxy live chat handover toggle to conversation service."""
    session_id = payload.get("session_id", "default")
    is_live_chat = payload.get("is_live_chat", False)
    agent_id = payload.get("agent_id", "agent_01")
    return await clients.handover_session(session_id, is_live_chat, agent_id)


@app.get("/api/v1/copilot/session/{session_id}")
async def get_copilot_session(session_id: str):
    """Proxy session state lookup to conversation service."""
    return await clients.get_session_state(session_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("services.gateway.src.main:app", host="0.0.0.0", port=port, reload=False)

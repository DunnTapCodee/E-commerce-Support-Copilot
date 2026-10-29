"""FastAPI Conversation Service running on Port 8001.
Orchestrates multi-turn sessions, context memory, and response policies.
"""
from __future__ import annotations

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
    ConversationSessionState,
    GatewayResponse,
    GuardrailResult,
    IntentPredictionResponse,
    QueryRequest,
    RetrievedDocument,
)
from services.conversation_service.src.config import (
    DISABLE_CONFIDENCE_GUARD,
    FAITHFULNESS_THRESHOLD,
    INTENT_CONFIDENCE_THRESHOLD,
    PORT,
)
from services.conversation_service.src.clients import (
    IntentServiceClient,
    RAGServiceClient,
    TelemetryServiceClient,
)
from services.conversation_service.src.dialogue_state import (
    ConversationState,
    IntentTracker,
    state_store,
)
from services.conversation_service.src.input_pipeline import (
    InputClassifier,
    extract_facts,
)
from services.conversation_service.src.memory import (
    ContextSummaryManager,
    MemoryWorker,
    TurnBuffer,
)
from services.conversation_service.src.policies import (
    ResponsePolicyDispatcher,
    CustomerAcknowledgementEngine,
    CopilotDraftEngine,
)


app = FastAPI(
    title="Conversation & Copilot Orchestration Service",
    description="Multi-turn dialogue state tracker and grounded response engine on Port 8001",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

intent_client = IntentServiceClient()
rag_client = RAGServiceClient()
telemetry_client = TelemetryServiceClient()
input_classifier = InputClassifier()
turn_buffer = TurnBuffer(max_turns=5)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "conversation_service",
        "port": PORT,
        "active_sessions": len(state_store.list_sessions()),
    }


@app.get("/api/v1/conversation/session/{session_id}", response_model=ConversationSessionState)
async def get_session_state(session_id: str):
    state = state_store.get_or_create(session_id)
    return ConversationSessionState(
        session_id=state.session_id,
        customer_id=state.customer_id,
        active_intent=state.active_intent,
        active_order_id=state.active_order_id,
        facts=state.facts,
        is_live_chat=state.is_live_chat,
        turns=state.turns,
        context_summary=state.context_summary,
        updated_at=state.last_updated,
    )


@app.post("/api/v1/conversation/chat", response_model=GatewayResponse)
async def process_chat_turn(request: QueryRequest, background_tasks: BackgroundTasks):
    """Central dialogue execution: Input classification -> Context intent -> Policy routing -> Draft."""
    start_time = time.perf_counter()
    interaction_id = str(uuid.uuid4())
    customer_query = request.query.strip()
    session_id = request.session_id
    customer_id = request.customer_id or "demo-customer"

    # Step 0: Retrieve / initialize session state
    state = state_store.get_or_create(session_id, customer_id)

    # Step 1: Input Classification & Fact Extraction (Tier 1 regex + Tier 2 Gemini)
    input_type, new_facts, input_conf = await input_classifier.classify_utterance(
        customer_query,
        active_intent=state.active_intent,
        context_summary=state.context_summary,
    )
    # Merge extracted facts
    merged_facts = dict(state.facts)
    merged_facts.update(new_facts)
    state.facts = merged_facts
    if "order_id" in merged_facts:
        state.active_order_id = merged_facts["order_id"]

    # Step 2: Context-Augmented Intent Prediction
    ml_intent_resp: Optional[IntentPredictionResponse] = None
    if input_type != "chitchat":
        augmented_query = IntentTracker.build_context_augmented_query(customer_query, state)
        try:
            ml_intent_resp = await intent_client.predict_intent(augmented_query)
        except Exception as exc:
            print(f"[ConversationService] Intent Service error: {exc}")
            ml_intent_resp = IntentPredictionResponse(
                intent=state.active_intent or "unknown_query",
                confidence=0.50 if state.active_intent else 0.0,
                is_in_scope=bool(state.active_intent),
                all_probabilities={},
            )

    # Step 3: Intent Transition & Arbitration
    effective_intent, effective_conf, switched = IntentTracker.resolve_intent_transition(
        customer_query,
        input_type,
        new_facts,
        ml_intent_resp,
        state,
    )
    state.active_intent = effective_intent

    # Create uniform IntentPredictionResponse for contracts
    final_intent_resp = IntentPredictionResponse(
        intent=effective_intent,
        confidence=round(effective_conf, 4),
        is_in_scope=True if DISABLE_CONFIDENCE_GUARD else (effective_conf >= 0.50),
        all_probabilities=ml_intent_resp.all_probabilities if ml_intent_resp else {effective_intent: effective_conf},
        language="vi",
        model_name="hybrid_dialogue_tracker",
    )

    # Step 4: Order Lookup
    order_data: Optional[Dict[str, Any]] = None
    lookup_key = state.active_order_id or customer_id
    if lookup_key:
        try:
            order_data = await telemetry_client.lookup_order(lookup_key)
        except Exception as exc:
            print(f"[ConversationService] Order lookup error: {exc}")

    # Step 5: Knowledge Retrieval (if question or happy path candidate)
    citations: List[RetrievedDocument] = []
    has_expired_policy = False
    if input_type not in {"chitchat"} and not state.is_live_chat:
        try:
            citations = await rag_client.retrieve_policies(
                query=customer_query,
                intent=effective_intent,
                top_k=3,
            )
            has_expired_policy = any(not doc.is_active for doc in citations)
        except Exception as exc:
            print(f"[ConversationService] RAG retrieve error: {exc}")

    # Step 6: Response Policy Dispatch (Evaluates guardrails & agent guidance)
    guard, draft_fallback, suggested_macro, agent_guidance, gen_mode = ResponsePolicyDispatcher.dispatch(
        user_query=customer_query,
        input_type=input_type,
        intent_resp=final_intent_resp,
        order_data=order_data,
        citations=citations,
        has_expired_policy=has_expired_policy,
        is_live_chat=state.is_live_chat,
    )

    # Step 7: Generate Phần 1 - Immediate Customer Acknowledgement (Trả lời dạo trước cho User)
    last_ack = state.turns[-1].agent_response if state.turns else None
    customer_ack = CustomerAcknowledgementEngine.generate(
        intent=effective_intent,
        facts=state.facts,
        input_type=input_type,
        user_query=customer_query,
        last_ack=last_ack,
    )

    # Step 8: Generate Phần 3 - Full-Context Copilot Draft for Agent (Bản thảo câu trả lời cho nhân viên duyệt)
    recent_turns_ctx = turn_buffer.format_as_context(state.turns)
    current_context_summary = state.context_summary or ContextSummaryManager.build_summary(state, order_data)

    agent_draft = await CopilotDraftEngine.generate_draft(
        user_query=customer_query,
        intent=effective_intent,
        facts=state.facts,
        order_data=order_data,
        context_summary=current_context_summary,
        recent_turns_text=recent_turns_ctx,
        citations=citations,
        is_live_chat=state.is_live_chat,
    )

    if not agent_draft.strip():
        agent_draft = suggested_macro or draft_fallback

    # Step 9: Background Tasks (Non-blocking async memory & audit persistence)
    # Store customer acknowledgement in turn buffer so far
    background_tasks.add_task(
        MemoryWorker.update_memory_task,
        session_id=session_id,
        customer_query=customer_query,
        agent_response=customer_ack,
        intent=effective_intent,
        confidence=effective_conf,
        new_facts=new_facts,
        order_data=order_data,
    )

    audit_payload = AuditLogCreate(
        interaction_id=interaction_id,
        customer_query=customer_query,
        predicted_intent=effective_intent,
        intent_confidence=effective_conf,
        guardrail_action=guard.action_type,
        retrieved_doc_ids=",".join(d.doc_id for d in citations),
        raw_draft_text=agent_draft,
        latency_ms=int((time.perf_counter() - start_time) * 1000),
    )
    background_tasks.add_task(telemetry_client.record_audit_log, audit_payload)

    # Format session turns for UI inspector
    ui_turns = [
        {"turn_id": t.turn_id, "user": t.customer_query, "agent": t.agent_response}
        for t in turn_buffer.get_recent_turns(state.turns)
    ]

    return GatewayResponse(
        interaction_id=interaction_id,
        intent=final_intent_resp,
        guardrail=guard,
        citations=citations,
        draft_text=agent_draft,
        order_data=order_data,
        generation_mode="copilot_gemini" if "Dạ em chào" in agent_draft else gen_mode,
        suggested_reply=agent_draft,
        customer_acknowledgement=customer_ack,
        agent_guidance=agent_guidance,
        input_type=input_type,
        active_facts=state.facts,
        is_live_chat=state.is_live_chat,
        session_turns=ui_turns,
        context_summary=current_context_summary,
    )


@app.post("/api/v1/conversation/handover")
async def toggle_live_chat_handover(session_id: str, enable_live_chat: bool = True):
    state = state_store.get_or_create(session_id)
    state.is_live_chat = enable_live_chat
    state_store.save(state)
    return {"session_id": session_id, "is_live_chat": state.is_live_chat}

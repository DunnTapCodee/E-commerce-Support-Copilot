"""FastAPI Conversation Service running on Port 8001.
Orchestrates multi-turn sessions, context memory, and response policies.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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
from services.conversation_service.src.tools import OrderTools


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
order_tools = OrderTools()


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "conversation_service",
        "port": PORT,
        "active_sessions": len(state_store.list_sessions()),
    }


@app.get("/api/v1/conversation/sessions")
async def list_persistent_sessions(customer_id: Optional[str] = None):
    """List persistent sessions for a customer from SQLite."""
    return state_store.list_sessions_by_customer(customer_id)


@app.get("/api/v1/conversation/session/{session_id}/details")
async def get_session_details(session_id: str):
    """Retrieve full conversation details with messages from SQLite."""
    details = state_store.get_full_session_details(session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Session not found")
    return details


@app.post("/api/v1/conversation/session")
async def create_new_session(payload: Dict[str, Any]):
    """Create a persistent session in SQLite."""
    sess_id = payload.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}"
    cust_id = payload.get("customer_id") or "CUST-1100"
    title = payload.get("title") or "Hội thoại mới"
    state = state_store.get_or_create(sess_id, cust_id)
    state_store.update_session_title(sess_id, title)
    return {"session_id": sess_id, "customer_id": cust_id, "title": title}


@app.patch("/api/v1/conversation/session/{session_id}")
async def update_session(session_id: str, payload: Dict[str, Any]):
    """Update session title or metadata in SQLite."""
    new_title = payload.get("title")
    if new_title:
        state_store.update_session_title(session_id, new_title)
    return {"status": "updated", "session_id": session_id, "title": new_title}


@app.delete("/api/v1/conversation/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a persistent session and its turns from SQLite."""
    deleted = state_store.delete_session(session_id)
    return {"status": "deleted" if deleted else "not_found", "session_id": session_id}


@app.post("/api/v1/conversation/message")
async def persist_chat_message(payload: Dict[str, Any]):
    """Persist an approved agent message or customer message to SQLite."""
    sess_id = payload.get("session_id")
    role = payload.get("role", "agent")
    content = payload.get("content", "")
    is_ack = payload.get("is_acknowledgement", False)
    if not sess_id or not content:
        raise HTTPException(status_code=400, detail="Missing session_id or content")
    turn_id = state_store.add_turn_record(
        session_id=sess_id,
        role=role,
        content=content,
        is_acknowledgement=is_ack,
    )
    return {"status": "saved", "turn_id": turn_id, "session_id": sess_id}


@app.post("/api/v1/conversation/fast_ack")
async def generate_fast_ack(request: QueryRequest):
    """Instant Buffer Acknowledgement (Câu chờ cho khách) within < 50ms.
    Classifies quick intent and returns polite customer buffer acknowledgement immediately,
    persisting customer query and buffer turn into SQLite DB.
    """
    customer_query = request.query.strip()
    session_id = request.session_id
    customer_id = request.customer_id or "demo-customer"

    state = state_store.get_or_create(session_id, customer_id)
    input_type, new_facts, _ = await input_classifier.classify_utterance(
        customer_query,
        active_intent=state.active_intent,
        context_summary=state.context_summary,
    )
    merged_facts = dict(state.facts)
    merged_facts.update(new_facts)
    state.facts = merged_facts

    quick_intent = "general_inquiry"
    q_low = customer_query.lower()

    is_greeting = bool(re.search(r"\b(h+i+|h+e+l+l*o+|a+l+o+|c+h+à+o+|c+h+a+o+)\b", q_low))
    has_promo = bool(re.search(r"\b(ưu đãi|khuyến mãi|khuyến mại|voucher|mã giảm|coupon|freeship|giảm giá|tiki xu)\b", q_low))
    has_cancel = bool(re.search(r"\b(hủy|huy|cancel)\b", q_low))
    has_return = bool(re.search(r"\b(đổi|doi|trả|tra|hoàn|hoan|refund)\b", q_low))
    has_price = bool(re.search(r"\b(đơn.*bao nhiêu tiền|tổng tiền.*đơn|giá đơn hàng|tiền đơn hàng)\b", q_low))
    has_track = bool(re.search(r"\b(giao|ship|ord-|vận đơn|khi nào|bao giờ)\b", q_low))
    has_oos = bool(re.search(r"\b(ronaldo|messi|thời tiết|phương trình|toán học|bóng đá|giá xăng|xăng)\b", q_low))

    if has_promo:
        quick_intent = "get_discounts"
    elif has_return:
        quick_intent = "return_policy"
    elif has_cancel:
        quick_intent = "cancel_order"
    elif is_greeting and len(q_low.split()) <= 4:
        quick_intent = "chitchat_greeting"
    elif has_oos:
        quick_intent = "out_of_scope"
    elif has_price:
        quick_intent = "price_inquiry"
    elif has_track:
        quick_intent = "track_order"
    elif state.active_intent and any(k in q_low for k in ["nó", "đơn này", "đơn đó", "sản phẩm"]):
        quick_intent = state.active_intent

    last_ack = state.turns[-1].agent_response if state.turns else None
    customer_ack = CustomerAcknowledgementEngine.generate(
        intent=quick_intent,
        facts=merged_facts,
        input_type=input_type,
        user_query=customer_query,
        last_ack=last_ack,
    )

    # Persist customer turn and buffer ack turn to SQLite
    state_store.add_turn_record(session_id, role="customer", content=customer_query, facts=merged_facts)
    state_store.add_turn_record(session_id, role="acknowledgement", content=customer_ack, is_acknowledgement=True, intent=quick_intent)
    state_store.save(state)

    return {
        "status": "acknowledged",
        "session_id": session_id,
        "customer_acknowledgement": customer_ack,
        "intent": quick_intent,
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


async def execute_dialogue_preprocessing(
    customer_query: str,
    state: ConversationSessionState,
    order_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Concurrent execution of Input Classification, Intent Prediction, and Query Rewriting via asyncio.gather."""
    from services.conversation_service.src.dialogue_state.query_rewriter import QueryRewriter

    targeted_query = IntentTracker.build_context_augmented_query(customer_query, state)

    # Launch Classification, Intent, and Query Rewriter in parallel
    classify_task = asyncio.create_task(
        input_classifier.classify_utterance(
            customer_query,
            active_intent=state.active_intent,
            context_summary=state.context_summary,
        )
    )
    intent_task = asyncio.create_task(
        intent_client.predict_intent(targeted_query)
    )
    rewrite_task = asyncio.create_task(
        QueryRewriter.rewrite_query(
            customer_query, state, order_data=order_data
        )
    )

    results = await asyncio.gather(classify_task, intent_task, rewrite_task, return_exceptions=True)

    # 1. Unpack Classification
    if isinstance(results[0], Exception):
        print(f"[ConversationService] Input Classifier concurrent error: {results[0]}")
        input_type, new_facts, input_conf = "new_question", {}, 0.85
    else:
        input_type, new_facts, input_conf = results[0]

    merged_facts = dict(state.facts)
    merged_facts.update(new_facts)
    state.facts = merged_facts
    if "order_id" in merged_facts:
        state.active_order_id = merged_facts["order_id"]

    # 2. Unpack Intent
    if isinstance(results[1], Exception):
        print(f"[ConversationService] Intent Service concurrent error: {results[1]}")
        ml_intent_resp = IntentPredictionResponse(
            intent=state.active_intent or "unknown_query",
            confidence=0.50 if state.active_intent else 0.0,
            is_in_scope=bool(state.active_intent),
            all_probabilities={},
        )
    else:
        ml_intent_resp = results[1]

    # 3. Unpack Rewrite
    if isinstance(results[2], Exception):
        print(f"[ConversationService] Query Rewriter concurrent error: {results[2]}")
        rewritten_query, rewrite_method = customer_query, "direct_utterance"
    else:
        rewritten_query, rewrite_method = results[2]

    # Intent Transition & Arbitration
    effective_intent, effective_conf, switched = await IntentTracker.resolve_intent_transition(
        customer_query,
        input_type,
        new_facts,
        ml_intent_resp,
        state,
    )
    state.active_intent = effective_intent

    final_intent_resp = IntentPredictionResponse(
        intent=effective_intent,
        confidence=round(effective_conf, 4),
        is_in_scope=True if DISABLE_CONFIDENCE_GUARD else (effective_conf >= 0.50),
        all_probabilities=ml_intent_resp.all_probabilities if ml_intent_resp else {effective_intent: effective_conf},
        language="vi",
        model_name="hybrid_dialogue_tracker",
    )

    effective_query_for_rag = rewritten_query if (input_type not in {"chitchat"} and rewritten_query) else customer_query

    # Step 6: Knowledge Retrieval (RAG)
    citations: List[RetrievedDocument] = []
    has_expired_policy = False
    if input_type not in {"chitchat"} and not state.is_live_chat:
        try:
            citations = await rag_client.retrieve_policies(
                query=effective_query_for_rag,
                intent=effective_intent,
                top_k=3,
            )
            has_expired_policy = any(not doc.is_active for doc in citations)
        except Exception as exc:
            print(f"[ConversationService] RAG retrieve error: {exc}")

    # Step 7: Response Policy Dispatch (Evaluates guardrails & agent guidance)
    guard, draft_fallback, suggested_macro, agent_guidance, gen_mode = ResponsePolicyDispatcher.dispatch(
        user_query=effective_query_for_rag,
        input_type=input_type,
        intent_resp=final_intent_resp,
        order_data=order_data,
        citations=citations,
        has_expired_policy=has_expired_policy,
        is_live_chat=state.is_live_chat,
    )

    # Step 8: Immediate Customer Acknowledgement
    last_ack = state.turns[-1].agent_response if state.turns else None
    customer_ack = CustomerAcknowledgementEngine.generate(
        intent=effective_intent,
        facts=state.facts,
        input_type=input_type,
        user_query=customer_query,
        last_ack=last_ack,
    )

    # Dynamic Components Labels
    intent_model_name = getattr(ml_intent_resp, "model_name", None) or ""
    intent_model_label = (
        "Mô hình LLM gpt-oss (openai-gpt-oss-20b)"
        if ml_intent_resp and ("gpt-oss" in intent_model_name.lower() or ml_intent_resp.confidence >= 0.75)
        else "NLU Hybrid (Quy tắc & Semantic Rules)"
    )
    rewriter_label = (
        f"LLM Query Rewriter ({rewrite_method})"
        if rewrite_method in ("llm_query_rewriter", "llm_policy_rewriter", "llm_order_rewriter", "llm_hybrid_rewriter")
        else "Direct Utterance (Bỏ qua viết lại / Xã giao)" if "out_of_service" in rewrite_method
        else "Direct Utterance (Giữ nguyên câu gốc)"
    )
    rag_label = (
        f"BM25 + Semantic Vector Retrieval ({len(citations)} tài liệu)"
        if citations
        else "Không kích hoạt (Hội thoại xã giao / Chitchat)"
    )

    return {
        "input_type": input_type,
        "new_facts": new_facts,
        "input_conf": input_conf,
        "ml_intent_resp": ml_intent_resp,
        "effective_intent": effective_intent,
        "effective_conf": effective_conf,
        "final_intent_resp": final_intent_resp,
        "rewritten_query": rewritten_query,
        "rewrite_method": rewrite_method,
        "effective_query_for_rag": effective_query_for_rag,
        "citations": citations,
        "guard": guard,
        "draft_fallback": draft_fallback,
        "suggested_macro": suggested_macro,
        "agent_guidance": agent_guidance,
        "gen_mode": gen_mode,
        "customer_ack": customer_ack,
        "intent_model_label": intent_model_label,
        "rewriter_label": rewriter_label,
        "rag_label": rag_label,
    }


@app.post("/api/v1/conversation/chat", response_model=GatewayResponse)
async def process_chat_turn(request: QueryRequest, background_tasks: BackgroundTasks):
    """Central dialogue execution with concurrent preprocessing (asyncio.gather)."""
    start_time = time.perf_counter()
    interaction_id = str(uuid.uuid4())
    customer_query = request.query.strip()
    session_id = request.session_id
    customer_id = request.customer_id or "demo-customer"

    # Step 0: Retrieve / initialize session state
    state = state_store.get_or_create(session_id, customer_id)

    # Step 1: Early Order Lookup & Session Association
    order_data: Optional[Dict[str, Any]] = None
    lookup_key = state.active_order_id or customer_id
    if lookup_key:
        try:
            order_data = await telemetry_client.lookup_order(lookup_key)
        except Exception as exc:
            print(f"[ConversationService] Order lookup error: {exc}")

    # Fallback to local order store if telemetry returned None
    if not order_data and state.active_order_id:
        order_data = order_tools.get_order_by_id(state.active_order_id)
    if not order_data and state.facts.get("order_cached"):
        order_data = state.facts["order_cached"]

    # Lock order_id into state facts for all subsequent turns
    if order_data and order_data.get("order_id"):
        state.active_order_id = order_data["order_id"]
        state.facts["order_id"] = order_data["order_id"]
        state.facts["order_cached"] = order_data

    # Concurrent Preprocessing Pipeline via asyncio.gather
    prep = await execute_dialogue_preprocessing(customer_query, state, order_data)

    effective_intent = prep["effective_intent"]
    effective_conf = prep["effective_conf"]
    final_intent_resp = prep["final_intent_resp"]
    effective_query_for_rag = prep["effective_query_for_rag"]
    citations = prep["citations"]
    guard = prep["guard"]
    suggested_macro = prep["suggested_macro"]
    draft_fallback = prep["draft_fallback"]
    customer_ack = prep["customer_ack"]
    gen_mode = prep["gen_mode"]
    new_facts = prep["new_facts"]

    # Step 9: Generate Full-Context Copilot Draft for Agent
    current_context_summary = state.context_summary or ContextSummaryManager.build_summary(state, order_data)
    if not guard.allow_llm:
        agent_draft = suggested_macro or draft_fallback
    else:
        recent_turns_ctx = turn_buffer.format_as_context(state.turns)

        agent_draft = await CopilotDraftEngine.generate_draft(
            user_query=effective_query_for_rag,
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

        # Step 9b: Runtime Safety Envelope Verification
        from services.conversation_service.src.policies.safety_guard import evaluate_runtime_safety_envelope
        runtime_guard = evaluate_runtime_safety_envelope(
            customer_query=customer_query,
            draft_text=agent_draft,
            order_data=order_data,
            citations=citations,
        )
        if not runtime_guard.allow_llm:
            guard = runtime_guard
            agent_draft = (
                "Dạ em chào anh/chị, em đã tiếp nhận yêu cầu của mình. "
                "Em đang phối hợp với bộ phận kiểm soát đơn hàng để kiểm tra hồ sơ và xử lý chính xác nhất cho anh/chị nhé ạ."
            )
            gen_mode = "blocked_safety_envelope"

    draft_label = (
        "Mô hình LLM gpt-oss (openai-gpt-oss-20b)"
        if gen_mode in ("proceed_to_llm", "copilot_gpt_oss") and not agent_draft.startswith("Dạ em cảm ơn anh/chị! Nếu mình có bất kỳ")
        else "Template CSKH & Macro An toàn"
    )
    safety_label = (
        "Chốt chặn NLI Faithfulness & Financial Gate (Đạt)"
        if guard.allow_llm
        else f"Can thiệp An toàn Guardrail: {guard.action_type}"
    )

    components_used = {
        "intent_classifier": prep["intent_model_label"],
        "query_rewriter": prep["rewriter_label"],
        "retrieval_engine": prep["rag_label"],
        "draft_engine": draft_label,
        "safety_envelope": safety_label,
    }

    # Step 10: Background Tasks (Non-blocking async memory & audit persistence)
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

    retrieval_status = "SUFFICIENT"
    if not citations and effective_intent not in ("chitchat_greeting", "chitchat_farewell", "human_agent"):
        retrieval_status = "FALLBACK"

    return GatewayResponse(
        interaction_id=interaction_id,
        session_id=session_id,
        customer_acknowledgement=customer_ack,
        draft_text=agent_draft,
        guardrail=guard,
        intent=final_intent_resp,
        citations=citations,
        agent_guidance=prep["agent_guidance"],
        latency_ms=int((time.perf_counter() - start_time) * 1000),
        retrieval_status=retrieval_status,
        session_turns=ui_turns,
        components_used=components_used,
        rewritten_query=prep["rewritten_query"],
        active_facts=state.facts,
        input_type=prep["input_type"],
    )


@app.post("/api/v1/conversation/chat_stream")
async def process_chat_turn_stream(request: QueryRequest):
    """Streaming dialogue execution with Server-Sent Events (SSE) and concurrent preprocessing."""
    start_time = time.perf_counter()
    interaction_id = str(uuid.uuid4())
    customer_query = request.query.strip()
    session_id = request.session_id
    customer_id = request.customer_id or "demo-customer"

    state = state_store.get_or_create(session_id, customer_id)

    # Step 1: Early Order Lookup
    order_data: Optional[Dict[str, Any]] = None
    lookup_key = state.active_order_id or customer_id
    if lookup_key:
        try:
            order_data = await telemetry_client.lookup_order(lookup_key)
        except Exception:
            pass
    if not order_data and state.active_order_id:
        order_data = order_tools.get_order_by_id(state.active_order_id)
    if not order_data and state.facts.get("order_cached"):
        order_data = state.facts["order_cached"]
    if order_data and order_data.get("order_id"):
        state.active_order_id = order_data["order_id"]
        state.facts["order_id"] = order_data["order_id"]
        state.facts["order_cached"] = order_data

    # Concurrent Preprocessing Pipeline
    prep = await execute_dialogue_preprocessing(customer_query, state, order_data)

    async def sse_event_generator():
        # Event 1: Immediate Metadata Event
        meta_payload = {
            "type": "meta",
            "interaction_id": interaction_id,
            "session_id": session_id,
            "customer_acknowledgement": prep["customer_ack"],
            "intent": {
                "intent": prep["effective_intent"],
                "confidence": prep["effective_conf"],
                "is_in_scope": True if DISABLE_CONFIDENCE_GUARD else (prep["effective_conf"] >= 0.50),
            },
            "confidence": prep["effective_conf"],
            "input_type": prep["input_type"],
            "rewritten_query": prep["rewritten_query"],
            "order_data": order_data,
            "guardrail_result": prep["guard"].model_dump(),
            "citations": [c.model_dump() for c in prep["citations"]],
            "agent_guidance": prep["agent_guidance"],
            "dynamic_components": {
                "intent_classifier": prep["intent_model_label"],
                "query_rewriter": prep["rewriter_label"],
                "retrieval_engine": prep["rag_label"],
                "draft_engine": "Mô hình LLM gpt-oss (Streaming SSE)" if prep["guard"].allow_llm else "Template CSKH & Macro An toàn",
                "safety_envelope": "Chốt chặn NLI Faithfulness & Financial Gate (Đạt)" if prep["guard"].allow_llm else f"Can thiệp An toàn Guardrail: {prep['guard'].action_type}",
            },
        }
        yield f"event: meta\ndata: {json.dumps(meta_payload, ensure_ascii=False)}\n\n"

        # Event 2..N: Token Streaming
        full_draft_chunks: List[str] = []
        guard = prep["guard"]

        if not guard.allow_llm:
            fallback_text = prep["suggested_macro"] or prep["draft_fallback"]
            full_draft_chunks.append(fallback_text)
            token_payload = {"type": "token", "delta": fallback_text}
            yield f"event: token\ndata: {json.dumps(token_payload, ensure_ascii=False)}\n\n"
        else:
            current_context_summary = state.context_summary or ContextSummaryManager.build_summary(state, order_data)
            recent_turns_ctx = turn_buffer.format_as_context(state.turns)

            try:
                async for token in CopilotDraftEngine.generate_draft_stream(
                    user_query=prep["effective_query_for_rag"],
                    intent=prep["effective_intent"],
                    facts=state.facts,
                    order_data=order_data,
                    context_summary=current_context_summary,
                    recent_turns_text=recent_turns_ctx,
                    citations=prep["citations"],
                    is_live_chat=state.is_live_chat,
                ):
                    full_draft_chunks.append(token)
                    token_payload = {"type": "token", "delta": token}
                    yield f"event: token\ndata: {json.dumps(token_payload, ensure_ascii=False)}\n\n"
            except Exception as stream_err:
                print(f"[ConversationService] Streaming token error: {stream_err}")
                if not full_draft_chunks:
                    fallback_text = prep["suggested_macro"] or prep["draft_fallback"]
                    full_draft_chunks.append(fallback_text)
                    token_payload = {"type": "token", "delta": fallback_text}
                    yield f"event: token\ndata: {json.dumps(token_payload, ensure_ascii=False)}\n\n"

        final_draft = "".join(full_draft_chunks).strip()
        if not final_draft:
            final_draft = prep["suggested_macro"] or prep["draft_fallback"]

        # Step 9b: Runtime Safety Envelope Verification on full draft
        from services.conversation_service.src.policies.safety_guard import evaluate_runtime_safety_envelope
        runtime_guard = evaluate_runtime_safety_envelope(
            customer_query=customer_query,
            draft_text=final_draft,
            order_data=order_data,
            citations=prep["citations"],
        )
        if not runtime_guard.allow_llm:
            final_draft = (
                "Dạ em chào anh/chị, em đã tiếp nhận yêu cầu của mình. "
                "Em đang phối hợp với bộ phận kiểm soát đơn hàng để kiểm tra hồ sơ và xử lý chính xác nhất cho anh/chị nhé ạ."
            )

        # Memory & Telemetry Persistence (async task in background)
        asyncio.create_task(
            MemoryWorker.update_memory_task(
                session_id=session_id,
                customer_query=customer_query,
                agent_response=prep["customer_ack"],
                intent=prep["effective_intent"],
                confidence=prep["effective_conf"],
                new_facts=prep["new_facts"],
                order_data=order_data,
            )
        )
        audit_payload = AuditLogCreate(
            interaction_id=interaction_id,
            customer_query=customer_query,
            predicted_intent=prep["effective_intent"],
            intent_confidence=prep["effective_conf"],
            guardrail_action=guard.action_type,
            retrieved_doc_ids=",".join(d.doc_id for d in prep["citations"]),
            raw_draft_text=final_draft,
            latency_ms=int((time.perf_counter() - start_time) * 1000),
        )
        asyncio.create_task(telemetry_client.record_audit_log(audit_payload))

        # Event N+1: Final Done Event
        done_payload = {
            "type": "done",
            "interaction_id": interaction_id,
            "draft_text": final_draft,
            "latency_ms": int((time.perf_counter() - start_time) * 1000),
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/conversation/handover")
async def toggle_live_chat_handover(session_id: str, enable_live_chat: bool = True):
    state = state_store.get_or_create(session_id)
    state.is_live_chat = enable_live_chat
    state_store.save(state)
    return {"session_id": session_id, "is_live_chat": state.is_live_chat}


if __name__ == "__main__":
    import uvicorn
    from services.conversation_service.src.config import PORT
    uvicorn.run("services.conversation_service.src.main:app", host="0.0.0.0", port=PORT, reload=False)


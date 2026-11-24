"""API Gateway & Central Ingress Router on Port 8000."""
import json
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
from fastapi.responses import StreamingResponse

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
from services.gateway.src.circuit_breaker import CircuitBreaker, CircuitState
from services.gateway.src.clients import TELEMETRY_SERVICE_URL, MicroserviceClients
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
from services.gateway.src.routers.rbac_router import router as rbac_router

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
conversation_circuit_breaker = CircuitBreaker("conversation_service")

# Mount Modular Routers
app.include_router(policy_router)
app.include_router(rbac_router)


@app.get("/health")
def health_check():
    """Health check for API Gateway."""
    return {
        "status": "healthy",
        "service": "api_gateway",
        "port": int(os.getenv("PORT", 8000)),
        "ingress_target": "conversation_service",
        "policy_target": "document_service",
        "circuit_breakers": {
            "conversation_service": conversation_circuit_breaker.get_status(),
        },
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
    generation_mode = "unknown"
    citations: List[RetrievedDocument] = []
    draft_text = ""
    order_data: Optional[Dict[str, Any]] = None
    guardrail_decision = GuardrailResult(
        allow_llm=True, action_type="PROCEED_TO_LLM", reason="Default initialization"
    )

    # Delegate to Conversation Service (Primary Path guarded by CircuitBreaker)
    cb_tripped = False
    if conversation_circuit_breaker.can_execute():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as http_client:
                resp = await http_client.post(
                    f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/chat",
                    json=request.model_dump(),
                )
                if resp.status_code == 200:
                    conversation_circuit_breaker.record_success()
                    return GatewayResponse(**resp.json())
                conversation_circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                cb_tripped = conversation_circuit_breaker.state == CircuitState.OPEN
        except Exception as exc:
            conversation_circuit_breaker.record_failure(str(exc))
            cb_tripped = conversation_circuit_breaker.state == CircuitState.OPEN
            print(f"[Gateway] Conversation Service unreachable: {exc}. Running graceful gateway fallback.")
    else:
        cb_tripped = True
        print("[Gateway] CircuitBreaker OPEN for conversation_service. Fast-failing to gateway fallback.")

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

    # Check for cross-customer IDOR query before lookup fallback
    from contracts.safety import (
        detect_brand_competitor_bait,
        detect_fabricated_prior_promise,
        detect_foreign_customer_query,
        detect_warehouse_seal_request,
        evaluate_runtime_safety_envelope,
        is_order_owned_by_customer,
    )

    foreign_cid = detect_foreign_customer_query(customer_query, customer_id)

    # Order lookup fallback (strictly scoped to session customer_id)
    tool_records: List[ToolCallRecord] = []
    order_match = re.search(r"\bORD-[A-Za-z0-9-]+\b", customer_query, re.IGNORECASE)
    requested_oid = order_match.group(0).upper() if order_match else None
    unauthorized_order_reason: Optional[str] = (
        f"Truy vấn đề cập mã khách hàng '{foreign_cid}' không thuộc tài khoản đang đăng nhập."
        if foreign_cid
        else None
    )
    if not unauthorized_order_reason:
        lookup_key = requested_oid or customer_id
        if lookup_key:
            try:
                order_data = await clients.lookup_order(lookup_key, customer_id=customer_id)
                if order_data and not is_order_owned_by_customer(order_data, customer_id):
                    order_data = None
                    unauthorized_order_reason = (
                        f"Đơn hàng {requested_oid or lookup_key} không thuộc quyền sở hữu của tài khoản hiện tại."
                    )
                elif requested_oid and not order_data:
                    # Check unscoped to distinguish nonexistent vs cross-customer IDOR
                    unscoped = await clients.lookup_order(requested_oid)
                    if unscoped and not is_order_owned_by_customer(unscoped, customer_id):
                        unauthorized_order_reason = (
                            f"Đơn hàng {requested_oid} thuộc khách hàng khác; từ chối tiết lộ PII."
                        )
            except Exception:
                pass

    manipulation_msg = detect_fabricated_prior_promise(customer_query)
    seal_msg = detect_warehouse_seal_request(customer_query)
    brand_msg = detect_brand_competitor_bait(customer_query)

    # Intent Guardrail Check
    intent_guard = evaluate_intent_guard(intent_resp)
    if intent_service_error:
        intent_guard = GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=(
                "Dịch vụ AI tạm gián đoạn. Đã chuyển tiếp an toàn để nhân viên hỗ trợ."
            ),
        )

    if unauthorized_order_reason:
        guardrail_decision = GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=unauthorized_order_reason,
            is_hard_fail=True,
            violations=[unauthorized_order_reason],
        )
        draft_text = (
            "Dạ Tiki chào anh/chị! Để đảm bảo bảo mật thông tin tài khoản và đơn hàng cá nhân, "
            "em chỉ có thể tra cứu các đơn hàng thuộc đúng tài khoản đang đăng nhập của anh/chị ạ."
        )
        generation_mode = "blocked_unauthorized_order_access"
    elif manipulation_msg or seal_msg or brand_msg:
        msg = manipulation_msg or seal_msg or brand_msg
        guardrail_decision = GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=msg,
            is_hard_fail=bool(manipulation_msg or seal_msg),
            violations=[msg],
        )
        if manipulation_msg:
            draft_text = (
                "Dạ Tiki chào anh/chị! Do các khoản cấp bù voucher hoặc bồi thường đều cần kiểm tra lịch sử xác thực trên hệ thống, "
                "em xin phép chuyển thông tin này tới chuyên viên CSKH cấp cao kiểm tra và phản hồi chính xác nhất cho anh/chị ạ."
            )
            generation_mode = "blocked_manipulation_guard"
        elif seal_msg:
            draft_text = (
                "Dạ Tiki chào anh/chị! Theo quy trình niêm phong và an toàn kho vận của Tiki, "
                "hệ thống không thể mở kiện hàng đã đóng gói hoặc chèn thêm giấy tờ bên ngoài vào kiện hàng."
            )
            generation_mode = "blocked_warehouse_guard"
        else:
            draft_text = (
                "Dạ Tiki chào anh/chị! Tiki luôn lắng nghe và trân trọng mọi góp ý của quý khách [POL-BRAND-001]. "
                "Em xin phép giữ lập trường trung lập, không bình luận hay so sánh với các sàn khác; "
                "nếu anh/chị cần hỗ trợ kiểm tra đơn hàng tại Tiki, em rất sẵn sàng hỗ trợ ngay ạ!"
            )
            generation_mode = "blocked_brand_sensitivity"
    elif not intent_guard.allow_llm:
        guardrail_decision = intent_guard
        if intent_resp.intent == "human_agent":
            draft_text = (
                "Dạ em chào anh/chị! Em là chuyên viên CSKH Tiki trực tuyến. "
                "Em đã tiếp nhận yêu cầu và sẵn sàng hỗ trợ trực tiếp ngay bây giờ ạ."
            )
        elif intent_resp.intent == "out_of_scope":
            draft_text = (
                "Dạ em chào anh/chị! Câu hỏi này hiện nằm ngoài phạm vi hỗ trợ đơn hàng và mua sắm của Tiki rồi ạ 😊. "
                "Anh/chị có cần em hỗ trợ thêm thông tin gì về đơn hàng hay các chính sách mua sắm trên sàn Tiki không ạ?"
            )
        else:
            draft_text = (
                "Dạ em chào anh/chị! Em đã ghi nhận yêu cầu của mình. "
                "Em đang kiểm tra thông tin trên hệ thống để hỗ trợ giải đáp cho anh/chị ngay nhé ạ."
            )
        generation_mode = "blocked_intent_guard"
    else:
        # Financial Guard Check
        financial_guard = evaluate_financial_guard(intent_resp.intent)
        if financial_guard and not financial_guard.allow_llm:
            guardrail_decision = financial_guard
            order_id_hint = (order_data.get("order_id") if order_data else None) or "của mình"
            draft_text = (
                f"Dạ em chào anh/chị, em đã tiếp nhận yêu cầu liên quan đến đơn hàng {order_id_hint}. "
                "Để đảm bảo an toàn giao dịch tài chính, em đang đối soát chi tiết tình trạng đơn và sẽ xử lý hoàn tất cho anh/chị ngay ạ."
            )
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
                draft_text = (
                    "Dạ em chào anh/chị, về vấn đề này em đang kiểm tra lại văn bản quy định hiện hành mới nhất của Tiki "
                    "để thông tin chính xác nhất đến anh/chị nhé ạ."
                )
                generation_mode = "blocked_policy_guard"
            else:
                try:
                    gen_resp = await clients.generate_draft(customer_query, citations)
                    from contracts.safety import clean_draft_header
                    draft_text = clean_draft_header(gen_resp.draft_text)
                    generation_mode = gen_resp.generation_mode

                    runtime_guard = evaluate_runtime_safety_envelope(
                        customer_query=customer_query,
                        draft_text=draft_text,
                        order_data=order_data,
                        citations=citations,
                    )
                    guardrail_decision = runtime_guard
                    if not runtime_guard.allow_llm:
                        generation_mode = "blocked_safety_envelope"
                        draft_text = (
                            "Dạ em chào anh/chị, em đã tiếp nhận yêu cầu của mình. "
                            "Em đang phối hợp với bộ phận kiểm soát đơn hàng để kiểm tra hồ sơ và xử lý chính xác nhất cho anh/chị nhé ạ."
                        )
                except Exception as exc:
                    generation_mode = "blocked_generation_error"
                    guardrail_decision = GuardrailResult(
                        allow_llm=False,
                        action_type="ESCALATE_HUMAN",
                        reason=f"LLM Generation service error: {str(exc)}",
                    )
                    draft_text = (
                        "Dạ em chào anh/chị, em đã nhận được câu hỏi của mình và đang kiểm tra thông tin chi tiết để phản hồi anh/chị ngay nhé ạ!"
                    )

    from contracts.order_actions import extract_order_action_proposal

    pending_action = None
    if not unauthorized_order_reason and order_data:
        pending_action = extract_order_action_proposal(
            customer_query=customer_query,
            intent=intent_resp.intent,
            order_data=order_data,
            customer_id=customer_id,
            session_id=request.session_id,
            interaction_id=interaction_id,
        )

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
        pending_action=pending_action,
        tool_calls=tool_records,
        generation_mode=generation_mode,
        suggested_reply=draft_text,
        agent_guidance=guardrail_decision.reason if not guardrail_decision.allow_llm else None,
        circuit_breaker_tripped=cb_tripped,
        components_used={
            "intent_classifier": (
                "Gateway Safe Escalation (Intent Service Unavailable)"
                if intent_service_error
                else f"Intent Service ({intent_resp.model_name or intent_resp.intent})"
            ),
            "query_rewriter": "Direct Customer Query",
            "retrieval_engine": f"Direct Policy Retrieval ({len(citations)} tài liệu)" if citations else "Không kích hoạt",
            "draft_engine": "Gateway Fallback Pipeline",
            "safety_envelope": f"Guardrail: {guardrail_decision.action_type}",
        },
    )


# Alias for backwards compatibility
query_copilot = process_copilot_query


def _sse_fallback_events(fallback_resp: GatewayResponse):
    """Build SSE meta/token/done chunks from a GatewayResponse fallback."""
    intent_name = (
        fallback_resp.intent.intent
        if hasattr(fallback_resp.intent, "intent")
        else str(fallback_resp.intent)
    )
    intent_conf = (
        fallback_resp.intent.confidence
        if hasattr(fallback_resp.intent, "confidence")
        else 0.0
    )
    guard_dict = (
        fallback_resp.guardrail.model_dump()
        if hasattr(fallback_resp, "guardrail") and fallback_resp.guardrail
        else None
    )
    citations_list = [
        (c.model_dump() if hasattr(c, "model_dump") else c)
        for c in (fallback_resp.citations or [])
    ]
    meta_payload = {
        "type": "meta",
        "interaction_id": fallback_resp.interaction_id,
        "customer_acknowledgement": getattr(fallback_resp, "customer_acknowledgement", None) or fallback_resp.draft_text,
        "intent": intent_name,
        "confidence": intent_conf,
        "guardrail_result": guard_dict,
        "citations": citations_list,
        "circuit_breaker_tripped": fallback_resp.circuit_breaker_tripped,
        "dynamic_components": getattr(fallback_resp, "components_used", {}),
    }
    return [
        f"event: meta\ndata: {json.dumps(meta_payload, ensure_ascii=False)}\n\n".encode("utf-8"),
        f"event: token\ndata: {json.dumps({'type': 'token', 'delta': fallback_resp.draft_text}, ensure_ascii=False)}\n\n".encode("utf-8"),
        f"event: done\ndata: {json.dumps({'type': 'done', 'draft_text': fallback_resp.draft_text, 'interaction_id': fallback_resp.interaction_id}, ensure_ascii=False)}\n\n".encode("utf-8"),
    ]


@app.post("/api/v1/copilot/query_stream")
async def query_copilot_stream(request: QueryRequest):
    """Proxy SSE streaming dialogue execution from Conversation Service to web clients."""

    async def event_stream_proxy():
        url = f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/chat_stream"
        if conversation_circuit_breaker.can_execute():
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as http_client:
                    async with http_client.stream("POST", url, json=request.model_dump()) as resp:
                        if resp.status_code == 200:
                            conversation_circuit_breaker.record_success()
                            async for chunk in resp.aiter_bytes():
                                yield chunk
                            return
                        conversation_circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        print(f"[Gateway] Stream proxy returned status {resp.status_code}")
            except Exception as exc:
                conversation_circuit_breaker.record_failure(str(exc))
                print(f"[Gateway] Stream proxy exception: {exc}")

        fallback_resp = await process_copilot_query(request, BackgroundTasks())
        for chunk in _sse_fallback_events(fallback_resp):
            yield chunk

    return StreamingResponse(
        event_stream_proxy(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


@app.post("/api/v1/copilot/fast_ack")
async def fast_acknowledgement_proxy(request: QueryRequest):
    """Fast buffer acknowledgement proxy to Conversation Service (< 50ms)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.post(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/fast_ack",
                json=request.model_dump(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] fast_ack proxy error: {exc}")

    # Fallback instant buffer message
    return {
        "status": "acknowledged",
        "session_id": request.session_id,
        "customer_acknowledgement": "Dạ anh/chị chờ em một xíu, nhân viên đang chuẩn bị thông tin cho mình ngay đây ạ!",
        "intent": "general_inquiry",
    }


@app.get("/api/v1/copilot/sessions")
async def list_sessions_proxy(customer_id: Optional[str] = None):
    """Proxy persistent sessions list from Conversation Service."""
    try:
        import httpx
        params = {"customer_id": customer_id} if customer_id else {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.get(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/sessions",
                params=params,
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] list_sessions proxy error: {exc}")
    return []


@app.get("/api/v1/copilot/session/{session_id}/details")
async def get_session_details_proxy(session_id: str):
    """Proxy persistent session details and turn history."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.get(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/session/{session_id}/details"
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] get_session_details proxy error: {exc}")
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/api/v1/copilot/session")
async def create_session_proxy(payload: Dict[str, Any]):
    """Proxy new session creation."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.post(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/session",
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] create_session proxy error: {exc}")
    return payload


@app.delete("/api/v1/copilot/session/{session_id}")
async def delete_session_proxy(session_id: str):
    """Proxy session deletion."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.delete(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/session/{session_id}"
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] delete_session proxy error: {exc}")
    return {"status": "deleted", "session_id": session_id}


@app.patch("/api/v1/copilot/session/{session_id}")
async def update_session_proxy(session_id: str, payload: Dict[str, Any]):
    """Proxy session update (e.g. rename title)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.patch(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/session/{session_id}",
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] update_session proxy error: {exc}")
    return {"status": "updated", "session_id": session_id}


@app.post("/api/v1/copilot/message")
async def save_message_proxy(payload: Dict[str, Any]):
    """Proxy message persistence."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as http_client:
            resp = await http_client.post(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/message",
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        print(f"[Gateway] save_message proxy error: {exc}")
    return {"status": "saved"}


@app.get("/api/v1/copilot/evaluation/summary")
def get_evaluation_summary():
    """Retrieve the latest automated evaluation results and KPI metrics."""
    try:
        from evaluation.evaluation_runner import EvaluationRunner
        return EvaluationRunner.get_latest_summary()
    except Exception as exc:
        print(f"[Gateway] get_evaluation_summary error: {exc}")
        return {
            "overall_status": "ERROR",
            "overall_pass_rate": None,
            "modules": [],
            "error": str(exc),
        }


@app.post("/api/v1/copilot/evaluation/run")
def run_evaluation_suite():
    """Execute the full live MLIP evaluation suite synchronously."""
    try:
        from evaluation.evaluation_runner import EvaluationRunner
        return EvaluationRunner.run_full_suite()
    except Exception as exc:
        print(f"[Gateway] run_evaluation_suite error: {exc}")
        return {
            "overall_status": "ERROR",
            "overall_pass_rate": None,
            "error": str(exc),
            "modules": [],
        }


@app.post("/api/v1/copilot/evaluation/probe")
def probe_evaluation_query(payload: Dict[str, Any]):
    """Run deterministic guardrails, IDOR, multi-order, and intent probes on a single query."""
    try:
        from evaluation.evaluation_runner import EvaluationRunner

        query = str(payload.get("query") or "").strip()
        customer_id = str(payload.get("customer_id") or "demo-customer").strip()
        if not query:
            return {"error": "Query không được để trống."}
        return EvaluationRunner.probe_query(query=query, customer_id=customer_id)
    except Exception as exc:
        print(f"[Gateway] probe_evaluation_query error: {exc}")
        return {"error": str(exc)}


@app.post("/api/v1/copilot/orders/actions/propose")
async def propose_order_action_proxy(payload: Dict[str, Any]):
    """Proxy order action proposal persistence to Telemetry Service."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/orders/actions/propose", json=payload)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.get("/api/v1/copilot/orders/actions")
async def list_order_actions_proxy(
    order_id: Optional[str] = None,
    session_id: Optional[str] = None,
    action_status: Optional[str] = None,
):
    """Proxy order action proposals listing from Telemetry Service."""
    params = {k: v for k, v in {"order_id": order_id, "session_id": session_id, "action_status": action_status}.items() if v}
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.get(f"{TELEMETRY_SERVICE_URL}/orders/actions", params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.post("/api/v1/copilot/orders/actions/{action_id}/decide")
async def decide_order_action_proxy(action_id: str, payload: Dict[str, Any]):
    """Proxy CS Staff APPROVE/REJECT decision on an order action proposal."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/orders/actions/{action_id}/decide", json=payload)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return resp.json()


@app.post("/api/v1/copilot/proactive/delay/scan")
async def scan_proactive_delay_proxy(reference_date: Optional[str] = None, min_overdue_days: int = 3):
    """Proxy proactive overdue-shipping scan."""
    params: Dict[str, Any] = {"min_overdue_days": min_overdue_days}
    if reference_date:
        params["reference_date"] = reference_date
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/proactive/delay/scan", params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.get("/api/v1/copilot/proactive/delay/notifications")
async def list_proactive_delay_proxy(notif_status: Optional[str] = None):
    """Proxy proactive overdue notifications list."""
    params = {"notif_status": notif_status} if notif_status else {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.get(f"{TELEMETRY_SERVICE_URL}/proactive/delay/notifications", params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.post("/api/v1/copilot/proactive/delay/dispatch")
async def dispatch_proactive_delay_proxy(payload: Optional[Dict[str, Any]] = None):
    """Proxy bulk dispatch of queued overdue delay notifications."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/proactive/delay/dispatch", json=payload or {})
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.get("/api/v1/copilot/incidents/clusters")
async def get_incident_clusters_proxy(window_hours: int = 24, min_cluster_size: int = 3):
    """Proxy incident clustering dashboard endpoint."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.get(
            f"{TELEMETRY_SERVICE_URL}/incidents/clusters",
            params={"window_hours": window_hours, "min_cluster_size": min_cluster_size},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.post("/api/v1/copilot/incidents/broadcast")
async def broadcast_incident_proxy(payload: Dict[str, Any]):
    """Proxy bulk incident broadcast audit log."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/incidents/broadcast", json=payload)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.get("/api/v1/copilot/ops/releases")
async def list_releases_proxy():
    """Proxy runtime config snapshots & rollback history."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.get(f"{TELEMETRY_SERVICE_URL}/ops/releases")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.post("/api/v1/copilot/ops/releases/snapshot")
async def create_release_snapshot_proxy(payload: Optional[Dict[str, Any]] = None):
    """Proxy release snapshot creation."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/ops/releases/snapshot", json=payload or {})
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.post("/api/v1/copilot/ops/releases/rollback")
async def rollback_release_proxy(payload: Dict[str, Any]):
    """Proxy versioned runtime config rollback."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.post(f"{TELEMETRY_SERVICE_URL}/ops/releases/rollback", json=payload)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@app.get("/api/v1/copilot/ops/releases/health-gate")
async def release_health_gate_proxy(limit: int = 100):
    """Proxy drift + release rollback recommendation check."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as http_client:
        resp = await http_client.get(
            f"{TELEMETRY_SERVICE_URL}/ops/releases/health-gate", params={"limit": limit}
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("services.gateway.src.main:app", host="0.0.0.0", port=port, reload=False)

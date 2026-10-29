"""FastAPI Service for Knowledge Retrieval & LLM Generation on Port 8002."""
import os
import sys
import json
from pathlib import Path
import copy
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import (
    RAGGenerateRequest,
    RAGGenerateResponse,
    RAGRetrieveRequest,
    RetrievedDocument,
    RawPolicyFilterRequest,
    PolicyFilterResult,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    PolicyAuditLogEntry,
    PolicyRollbackRequest,
)
from services.rag_service.src.generator import LLMGenerator
from services.rag_service.src.indexer import PolicyVectorIndexer
from services.rag_service.src.ingestion import load_policy_documents
from services.rag_service.src.retriever import PolicyRetriever
from services.rag_service.src import policy_filter

POLICIES_PATH = Path(os.getenv("POLICIES_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policies.json")))
AUDIT_LOGS_PATH = Path(os.getenv("POLICY_AUDIT_LOGS_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policy_audit_logs.json")))
INDEX_PATH = Path(os.getenv("INDEX_PATH", str(ROOT_DIR / "artifacts" / "vector_store" / "policy_index.pkl")))
RETRIEVAL_METHOD = os.getenv("RETRIEVAL_METHOD", "bm25").strip().lower()
DENSE_EMBEDDING_MODEL = os.getenv("DENSE_EMBEDDING_MODEL", "keepitreal/vietnamese-sbert")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
RETRIEVAL_DEVICE = os.getenv("RETRIEVAL_DEVICE", "cpu")

indexer_instance = PolicyVectorIndexer()
retriever_instance: PolicyRetriever = None
generator_instance = LLMGenerator(timeout_seconds=15)


def init_knowledge_base():
    """Load or build vector store index from policies.json."""
    global indexer_instance, retriever_instance
    print(f"[rag_service] Loading policies from {POLICIES_PATH.name}...")
    docs = load_policy_documents(POLICIES_PATH)
    indexer_instance.fit_and_save(docs, INDEX_PATH)
    retriever_instance = PolicyRetriever(
        indexer_instance,
        method=RETRIEVAL_METHOD,
        dense_model=DENSE_EMBEDDING_MODEL,
        reranker_model=RERANKER_MODEL,
        device=RETRIEVAL_DEVICE,
    )
    print(f"[rag_service] Indexed {len(docs)} documents with {RETRIEVAL_METHOD}. Ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_knowledge_base()
    yield


app = FastAPI(
    title="RAG & Knowledge Service",
    description="Knowledge base search and LLM generation serving port 8002",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    """Health check for RAG service."""
    num_docs = len(indexer_instance.documents) if indexer_instance else 0
    return {
        "status": "healthy" if num_docs > 0 else "degraded",
        "service": "rag_service",
        "documents_indexed": num_docs,
        "index_path": str(INDEX_PATH),
        "retrieval_method": retriever_instance.method if retriever_instance else RETRIEVAL_METHOD,
    }


@app.post("/ingest")
def trigger_ingestion():
    """Trigger ingestion of policies.json to update vector store index."""
    try:
        init_knowledge_base()
        return {
            "status": "success",
            "message": f"Successfully ingested {len(indexer_instance.documents)} policy documents",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}",
        )


@app.post("/retrieve", response_model=List[RetrievedDocument])
def retrieve_policies(request: RAGRetrieveRequest):
    """Retrieve top-k policy documents with active version filtering."""
    if not retriever_instance:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retriever not ready",
        )
    return retriever_instance.retrieve(
        query=request.query,
        intent=request.intent,
        top_k=request.top_k,
        filter_active_only=request.filter_active_only,
    )


@app.post("/generate", response_model=RAGGenerateResponse)
async def generate_draft(request: RAGGenerateRequest):
    """Generate grounded draft response citing policy documents."""
    try:
        return await generator_instance.generate_draft(request.query, request.citations)
    except TimeoutError as te:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(te),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# Audit Log helpers & endpoints
# ---------------------------------------------------------------------------

def _load_audit_logs() -> List[dict]:
    if not AUDIT_LOGS_PATH.exists():
        return []
    try:
        with open(AUDIT_LOGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_audit_logs(logs: List[dict]):
    tmp_path = AUDIT_LOGS_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    tmp_path.replace(AUDIT_LOGS_PATH)


def _record_audit_log(
    doc_id: str,
    action: str,
    performed_by: str = "Admin",
    reason: Optional[str] = None,
    before_snapshot: Optional[dict] = None,
    after_snapshot: Optional[dict] = None,
) -> dict:
    logs = _load_audit_logs()
    entry = {
        "log_id": f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}",
        "timestamp": datetime.now().isoformat(),
        "doc_id": doc_id,
        "action": action,
        "performed_by": performed_by or "Admin",
        "reason": reason or "",
        "before_snapshot": before_snapshot,
        "after_snapshot": after_snapshot,
    }
    logs.insert(0, entry)
    _save_audit_logs(logs)
    return entry


@app.post("/policy/filter", response_model=PolicyFilterResult)
def filter_policy(request: RawPolicyFilterRequest):
    """Extract structured policy from raw text using LLM (Gemini) with heuristic fallback."""
    try:
        result = policy_filter.auto_extract_policy(request)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Policy extraction failed: {str(exc)}",
        )


@app.post("/policy/create", response_model=dict)
def create_policy(request: PolicyCreateRequest):
    """Persist a new policy document, reload KB, re-index vector store, and record audit log."""
    policies_path = POLICIES_PATH
    try:
        with open(policies_path, "r", encoding="utf-8") as f:
            policies = json.load(f)
    except Exception:
        policies = []

    new_policy = request.policy.model_dump()
    policies.append(new_policy)

    tmp_path = policies_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(policies, f, ensure_ascii=False, indent=2)
    tmp_path.replace(policies_path)

    # Record Audit Log
    _record_audit_log(
        doc_id=new_policy.get("doc_id", ""),
        action="CREATE",
        performed_by=request.performed_by or "Admin",
        reason=request.reason or request.admin_note or "Thêm mới chính sách",
        before_snapshot=None,
        after_snapshot=copy.deepcopy(new_policy),
    )

    init_knowledge_base()
    return {"status": "success", "message": "Policy added and KB refreshed"}


@app.get("/policies", response_model=List[RetrievedDocument])
def list_policies():
    """Return all policy documents currently in the Knowledge Base."""
    try:
        docs = load_policy_documents(POLICIES_PATH)
        return [d.model_dump() for d in docs]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load policies: {str(exc)}",
        )


@app.patch("/policies/{doc_id}", response_model=dict)
def update_policy(doc_id: str, payload: dict):
    """Partially update a policy document by doc_id, record audit log, and re-index KB."""
    try:
        with open(POLICIES_PATH, "r", encoding="utf-8") as f:
            policies = json.load(f)
    except Exception:
        raise HTTPException(status_code=404, detail="policies.json not found")

    updates = payload.get("updates", payload) if isinstance(payload, dict) and "updates" in payload else payload
    performed_by = payload.get("performed_by", "Admin") if isinstance(payload, dict) else "Admin"
    reason = payload.get("reason", "") if isinstance(payload, dict) else ""

    found = False
    before_snap = None
    after_snap = None
    action = "UPDATE"
    for p in policies:
        if p.get("doc_id") == doc_id:
            before_snap = copy.deepcopy(p)
            p.update(updates)
            after_snap = copy.deepcopy(p)
            if p.get("policy_type") == "superseded" and before_snap.get("policy_type") != "superseded":
                action = "SUPERSEDE"
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Policy '{doc_id}' not found")

    tmp_path = POLICIES_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(policies, f, ensure_ascii=False, indent=2)
    tmp_path.replace(POLICIES_PATH)

    # Record Audit Log
    _record_audit_log(
        doc_id=doc_id,
        action=action,
        performed_by=performed_by,
        reason=reason or (f"Thay đổi sang {action}" if action == "SUPERSEDE" else "Cập nhật thông tin chính sách"),
        before_snapshot=before_snap,
        after_snapshot=after_snap,
    )

    init_knowledge_base()
    return {"status": "success", "message": f"Policy '{doc_id}' updated and KB refreshed"}


@app.get("/policies/audit-logs", response_model=List[dict])
def list_audit_logs():
    """Return all policy audit log entries."""
    return _load_audit_logs()


@app.post("/policies/rollback", response_model=dict)
def rollback_policy(request: PolicyRollbackRequest):
    """Rollback a policy change based on audit log ID."""
    logs = _load_audit_logs()
    target_log = None
    for item in logs:
        if item.get("log_id") == request.log_id:
            target_log = item
            break

    if not target_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bản ghi Audit Log có ID '{request.log_id}'",
        )

    doc_id = target_log.get("doc_id")
    action = target_log.get("action")
    before_snapshot = target_log.get("before_snapshot")
    after_snapshot = target_log.get("after_snapshot")

    try:
        with open(POLICIES_PATH, "r", encoding="utf-8") as f:
            policies = json.load(f)
    except Exception:
        policies = []

    current_policy = next((p for p in policies if p.get("doc_id") == doc_id), None)
    current_snap = copy.deepcopy(current_policy) if current_policy else None

    # Rollback logic according to original action
    if action == "CREATE":
        policies = [p for p in policies if p.get("doc_id") != doc_id]
        restored_desc = f"Đã thu hồi chính sách mới tạo '{doc_id}' khỏi hệ thống"
    elif action in ("UPDATE", "SUPERSEDE"):
        if not before_snapshot:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không thể rollback: bản ghi trước đó không có snapshot dữ liệu (before_snapshot is None).",
            )
        if current_policy:
            policies = [before_snapshot if p.get("doc_id") == doc_id else p for p in policies]
        else:
            policies.append(before_snapshot)
        restored_desc = f"Đã khôi phục chính sách '{doc_id}' về trạng thái trước {action}"
    elif action == "ROLLBACK":
        if before_snapshot:
            if current_policy:
                policies = [before_snapshot if p.get("doc_id") == doc_id else p for p in policies]
            else:
                policies.append(before_snapshot)
            restored_desc = f"Đã đảo ngược rollback cho chính sách '{doc_id}'"
        else:
            policies = [p for p in policies if p.get("doc_id") != doc_id]
            restored_desc = f"Đã đảo ngược rollback cho chính sách '{doc_id}'"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hành động '{action}' không hỗ trợ rollback tự động.",
        )

    tmp_path = POLICIES_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(policies, f, ensure_ascii=False, indent=2)
    tmp_path.replace(POLICIES_PATH)

    # Record new audit log for the ROLLBACK operation
    _record_audit_log(
        doc_id=doc_id,
        action="ROLLBACK",
        performed_by=request.performed_by or "Admin",
        reason=request.reason or f"Undo/Rollback hành động '{action}' (Log ID: {request.log_id})",
        before_snapshot=current_snap,
        after_snapshot=before_snapshot,
    )

    init_knowledge_base()
    return {
        "status": "success",
        "message": f"{restored_desc} thành công. Knowledge Base đã được cập nhật.",
        "doc_id": doc_id,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run("services.rag_service.src.main:app", host="0.0.0.0", port=port, reload=False)


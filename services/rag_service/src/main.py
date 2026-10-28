"""FastAPI Service for Knowledge Retrieval & LLM Generation on Port 8002."""
import os
import sys
import json
from pathlib import Path
from typing import List
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
)
from services.rag_service.src.generator import LLMGenerator
from services.rag_service.src.indexer import PolicyVectorIndexer
from services.rag_service.src.ingestion import load_policy_documents
from services.rag_service.src.retriever import PolicyRetriever
from services.rag_service.src import policy_filter

POLICIES_PATH = Path(os.getenv("POLICIES_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policies.json")))
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
    """Persist a new policy document, reload KB and re-index vector store."""
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
def update_policy(doc_id: str, updates: dict):
    """Partially update a policy document by doc_id (e.g. flip policy_type to superseded)."""
    try:
        with open(POLICIES_PATH, "r", encoding="utf-8") as f:
            policies = json.load(f)
    except Exception:
        raise HTTPException(status_code=404, detail="policies.json not found")

    found = False
    for p in policies:
        if p.get("doc_id") == doc_id:
            p.update(updates)
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Policy '{doc_id}' not found")

    tmp_path = POLICIES_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(policies, f, ensure_ascii=False, indent=2)
    tmp_path.replace(POLICIES_PATH)

    init_knowledge_base()
    return {"status": "success", "message": f"Policy '{doc_id}' updated and KB refreshed"}



if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run("services.rag_service.src.main:app", host="0.0.0.0", port=port, reload=False)

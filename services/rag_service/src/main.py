"""FastAPI Service for Knowledge Retrieval & LLM Generation on Port 8002."""
import os
import sys
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
)
from services.rag_service.src.generator import LLMGenerator
from services.rag_service.src.indexer import PolicyVectorIndexer
from services.rag_service.src.ingestion import load_policy_documents
from services.rag_service.src.retriever import PolicyRetriever

POLICIES_PATH = Path(os.getenv("POLICIES_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policies.json")))
INDEX_PATH = Path(os.getenv("INDEX_PATH", str(ROOT_DIR / "artifacts" / "vector_store" / "policy_index.pkl")))

indexer_instance = PolicyVectorIndexer()
retriever_instance: PolicyRetriever = None
generator_instance = LLMGenerator(timeout_seconds=8)


def init_knowledge_base():
    """Load or build vector store index from policies.json."""
    global indexer_instance, retriever_instance
    print(f"[rag_service] Loading policies from {POLICIES_PATH.name}...")
    docs = load_policy_documents(POLICIES_PATH)
    indexer_instance.fit_and_save(docs, INDEX_PATH)
    retriever_instance = PolicyRetriever(indexer_instance)
    print(f"[rag_service] Indexed {len(docs)} documents. Ready.")


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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run("services.rag_service.src.main:app", host="0.0.0.0", port=port, reload=False)

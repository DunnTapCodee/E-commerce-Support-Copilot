"""FastAPI Document Service on Port 8004.
Handles Policy Lifecycle, LLM Parsing / Filter, Dynamic is_active Calculation, Audit Trails, and Rollback.
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.document_service.src.config import PORT
from services.document_service.src.policy_manager import policy_manager
from services.document_service.src.routers.document_router import router as document_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On service startup: automatically recompute active statuses against today's date
    print("[document_service] Starting up. Verifying and synchronizing is_active policy statuses...")
    try:
        sync_result = await policy_manager.recompute_all_active_statuses(trigger_rag_sync=False)
        print(f"[document_service] Synchronized {sync_result['total_policies']} policies. Status changes: {sync_result['updated_count']}.")
    except Exception as e:
        print(f"[document_service] Warning during initial status sync: {e}")
    yield


app = FastAPI(
    title="Document & Policy Lifecycle Service",
    description="Dedicated microservice managing e-commerce policies, automated is_active calculation, audit logs, and version rollback.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_router)


@app.get("/health")
def health_check():
    """Health check endpoint for Document Service."""
    docs = policy_manager.load_policies()
    logs = policy_manager.load_audit_logs()
    active_count = sum(1 for d in docs if d.is_active)
    return {
        "status": "healthy",
        "service": "document_service",
        "port": PORT,
        "total_policies": len(docs),
        "active_policies": active_count,
        "inactive_policies": len(docs) - active_count,
        "audit_logs_count": len(logs),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.document_service.src.main:app", host="0.0.0.0", port=PORT, reload=False)


"""FastAPI Service for Telemetry, Audit Logs & Mock Orders on Port 8003."""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import AuditLogCreate, HumanActionUpdate
from services.telemetry_service.src.database import init_db
from services.telemetry_service.src.repository import TelemetryRepository

DB_PATH = Path(os.getenv("DB_PATH", str(ROOT_DIR / "copilot_telemetry.sqlite3")))
MOCK_ORDERS_PATH = Path(os.getenv("MOCK_ORDERS_PATH", str(ROOT_DIR / "data" / "mock_orders.json")))

repo_instance = TelemetryRepository(DB_PATH, MOCK_ORDERS_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[telemetry_service] Initializing database at {DB_PATH}...")
    init_db(DB_PATH)
    print(f"[telemetry_service] Database ready with WAL mode.")
    yield


app = FastAPI(
    title="Telemetry & Audit Service",
    description="Telemetry audit log persistence and order lookup serving port 8003",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    """Health check endpoint for telemetry service."""
    return {
        "status": "healthy",
        "service": "telemetry_service",
        "db_path": str(DB_PATH),
    }


@app.post("/audit/log", status_code=status.HTTP_201_CREATED)
def record_audit_log(payload: AuditLogCreate):
    """Save or upsert initial interaction audit log."""
    try:
        repo_instance.insert_audit_log(payload)
        return {"status": "success", "interaction_id": payload.interaction_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record audit log: {str(e)}",
        )


@app.post("/audit/action")
def update_human_action(payload: HumanActionUpdate):
    """Update human review action for an interaction."""
    success = repo_instance.update_human_action(payload)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interaction {payload.interaction_id} not found in telemetry logs",
        )
    return {"status": "success", "interaction_id": payload.interaction_id}


@app.get("/audit/stats")
def get_audit_stats():
    """Fetch aggregate telemetry statistics and recent logs for dashboards."""
    return repo_instance.get_stats()


@app.get("/orders/{customer_id}")
def get_order_by_customer(customer_id: str):
    """Look up order information for financial reconciliation."""
    order = repo_instance.get_order(customer_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order for customer {customer_id} not found",
        )
    return order


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8003))
    uvicorn.run("services.telemetry_service.src.main:app", host="0.0.0.0", port=port, reload=False)

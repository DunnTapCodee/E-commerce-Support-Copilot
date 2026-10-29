"""FastAPI Service for Telemetry, Audit Logs & High-Performance Orders on Port 8003."""
import os
import sys
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import AuditLogCreate, HumanActionUpdate, OrderCancelRequest, OrderCancelResponse
from services.telemetry_service.src.database import init_db, migrate_mock_orders
from services.telemetry_service.src.repository import TelemetryRepository

DB_PATH = Path(os.getenv("DB_PATH", str(ROOT_DIR / "copilot_telemetry.sqlite3")))
MOCK_ORDERS_PATH = Path(os.getenv("MOCK_ORDERS_PATH", str(ROOT_DIR / "data" / "mock_orders.json")))

repo_instance = TelemetryRepository(DB_PATH, MOCK_ORDERS_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[telemetry_service] Initializing database at {DB_PATH} with mock orders migration...")
    init_db(DB_PATH, MOCK_ORDERS_PATH)
    print(f"[telemetry_service] Database ready with indexed orders table and WAL mode.")
    yield


app = FastAPI(
    title="Telemetry & Audit Service",
    description="Telemetry audit log persistence, indexed order queries, and LRU Cache serving port 8003",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    """Health check endpoint for telemetry service."""
    return {
        "status": "healthy",
        "service": "telemetry_service",
        "db_path": str(DB_PATH),
        "cache": repo_instance.get_cache_stats(),
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
def record_human_action(payload: HumanActionUpdate):
    """Record a support agent's review decision for an interaction."""
    try:
        updated = repo_instance.update_human_action(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record the human review action.",
        ) from exc

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy interaction_id cần cập nhật.",
        )

    return {
        "status": "recorded",
        "interaction_id": payload.interaction_id,
        "action": payload.action,
        "message": "Đã ghi nhận quyết định kiểm duyệt của nhân viên.",
    }



@app.get("/audit/stats")
def get_audit_stats():
    """Fetch aggregate telemetry statistics and recent logs for dashboards."""
    return repo_instance.get_stats()


# -------------------------------------------------------------------
# Module 3: Dynamic Order Query & Tool Calling Endpoints
# -------------------------------------------------------------------
@app.get("/orders/phone/{phone}")
def get_orders_by_phone(phone: str):
    """Retrieve all orders belonging to a phone number."""
    orders = repo_instance.get_orders_by_phone(phone)
    if not orders:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No orders found for phone '{phone}'",
        )
    return {"phone": phone, "total": len(orders), "orders": orders}


@app.get("/orders/{identifier}")
def get_order_by_identifier(identifier: str):
    """Look up order by order_id, phone, tracking_code, or customer_id using LRU cache + indexed SQLite."""
    order = repo_instance.get_order(identifier)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order matching identifier '{identifier}' not found",
        )
    return order


@app.post("/orders/{order_id}/cancel", response_model=OrderCancelResponse)
def cancel_order(order_id: str, payload: OrderCancelRequest):
    """Cancel order if allowed, update SQLite, and invalidate LRU cache."""
    result = repo_instance.cancel_order(order_id, payload.reason)
    return OrderCancelResponse(
        success=result["success"],
        order_id=result["order_id"],
        message=result["message"],
        updated_status=result.get("updated_status"),
    )


@app.get("/orders/customer/{customer_id}")
def get_orders_by_customer(customer_id: str):
    """Retrieve all orders belonging to a customer account."""
    orders = repo_instance.get_customer_orders(customer_id)
    return {"customer_id": customer_id, "total_orders": len(orders), "orders": orders}


@app.get("/orders/cache/stats")
def get_cache_metrics():
    """Retrieve LRU Cache hits, misses, hit ratio, and size."""
    return repo_instance.get_cache_stats()


@app.post("/orders/migrate")
def trigger_orders_migration(force: bool = False):
    """Manually trigger migration from mock_orders.json into SQLite."""
    total = migrate_mock_orders(DB_PATH, MOCK_ORDERS_PATH, force=force)
    repo_instance.cache.clear()
    return {"status": "success", "total_migrated": total, "force": force}

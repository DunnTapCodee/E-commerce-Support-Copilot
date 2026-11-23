"""FastAPI Service for Telemetry, Audit Logs & High-Performance Orders on Port 8003."""
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import (
    AuditLogCreate,
    HumanActionUpdate,
    IncidentBroadcastRequest,
    OrderActionDecisionRequest,
    OrderActionProposal,
    OrderCancelRequest,
    OrderCancelResponse,
)
from services.telemetry_service.src.database import init_db, migrate_mock_orders
from services.telemetry_service.src.metrics import detect_telemetry_drift, evaluate_shadow_comparison
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


@app.get("/audit/continual_learning/pool")
def get_continual_learning_pool(limit: int = 50):
    """Fetch high-value approved interaction samples for continual learning loops."""
    return {
        "status": "success",
        "count": len(repo_instance.get_continual_learning_pool(limit)),
        "samples": repo_instance.get_continual_learning_pool(limit),
    }


class ShadowEvaluationRequest(BaseModel):
    interaction_id: str
    primary_draft: str
    shadow_draft: str
    expected_entities: Optional[dict] = None
    primary_latency_ms: float = 0.0
    shadow_latency_ms: float = 0.0


@app.get("/audit/drift")
def get_telemetry_drift_report(limit: int = 100):
    """Analyze recent production interactions for Data Drift, Concept Drift, and Automation Bias."""
    stats = repo_instance.get_stats()
    recent_records = (stats.get("recent_records") or stats.get("recent_logs") or [])[:limit]
    return detect_telemetry_drift(recent_records)


@app.post("/audit/shadow/evaluate")
def evaluate_shadow_deployment(payload: ShadowEvaluationRequest):
    """Evaluate a Shadow model/prompt candidate against Primary production output (CMU MLIP Ch. 19)."""
    result = evaluate_shadow_comparison(
        primary_draft=payload.primary_draft,
        shadow_draft=payload.shadow_draft,
        expected_entities=payload.expected_entities,
        primary_latency_ms=payload.primary_latency_ms,
        shadow_latency_ms=payload.shadow_latency_ms,
    )
    return {
        "status": "evaluated",
        "interaction_id": payload.interaction_id,
        **result,
    }


# -------------------------------------------------------------------
# Module 3: Dynamic Order Query & Tool Calling Endpoints
# -------------------------------------------------------------------
@app.get("/orders/phone/{phone}")
def get_orders_by_phone(phone: str, customer_id: Optional[str] = None):
    """Retrieve all orders belonging to a phone number."""
    orders = repo_instance.get_orders_by_phone(phone, customer_id=customer_id)
    if not orders:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No orders found for phone '{phone}'",
        )
    return {"phone": phone, "total": len(orders), "orders": orders}


@app.get("/orders/{identifier}")
def get_order_by_identifier(identifier: str, customer_id: Optional[str] = None):
    """Look up order by order_id, phone, tracking_code, or customer_id using LRU cache + indexed SQLite."""
    order = repo_instance.get_order(identifier, customer_id=customer_id)
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


# -------------------------------------------------------------------
# Dot 2 (Task 4 & 5): Quick-Approval Order Actions, Delay Agent & Incident Clustering
# -------------------------------------------------------------------
@app.post("/orders/actions/propose")
def propose_order_action(payload: OrderActionProposal):
    """Persist a PENDING order action proposal extracted from chat (no orders mutation)."""
    return repo_instance.propose_order_action(payload)


@app.get("/orders/actions")
def list_order_actions(
    order_id: Optional[str] = None,
    session_id: Optional[str] = None,
    action_status: Optional[str] = None,
):
    """List pending/decided order action proposals."""
    items = repo_instance.list_order_actions(
        order_id=order_id, session_id=session_id, status=action_status
    )
    return {"total": len(items), "actions": items}


@app.post("/orders/actions/{action_id}/decide")
def decide_order_action(action_id: str, payload: OrderActionDecisionRequest):
    """Execute APPROVED order update atomically or record REJECTED decision with reason."""
    try:
        res = repo_instance.decide_order_action(action_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order action proposal '{action_id}' not found",
        )
    return res


@app.post("/proactive/delay/scan")
def scan_proactive_delay(reference_date: Optional[str] = None, min_overdue_days: int = 3):
    """Scan Shipping orders > min_overdue_days past promised_delivery_date (idempotent)."""
    return repo_instance.scan_overdue_shipping_orders(
        reference_date=reference_date,
        min_overdue_days=min_overdue_days,
    )


@app.get("/proactive/delay/notifications")
def get_proactive_delay_notifications(notif_status: Optional[str] = None):
    """List simulated 30k overdue apology notifications."""
    items = repo_instance.list_delay_notifications(status=notif_status)
    return {"total": len(items), "notifications": items}


@app.post("/proactive/delay/dispatch")
def dispatch_proactive_delay_notifications(payload: Optional[Dict[str, Any]] = None):
    """Mark queued overdue delay notifications as SENT."""
    body = payload or {}
    return repo_instance.dispatch_delay_notifications(
        order_ids=body.get("order_ids"),
        performed_by=body.get("performed_by", "CS Staff"),
    )


@app.get("/incidents/clusters")
def get_incident_clusters(window_hours: int = 24, min_cluster_size: int = 3):
    """Return clustered widespread incidents detected within recent telemetry window."""
    return repo_instance.get_incident_clusters(
        window_hours=window_hours,
        min_cluster_size=min_cluster_size,
    )


@app.post("/incidents/broadcast")
def record_incident_broadcast(payload: IncidentBroadcastRequest):
    """Log staff bulk broadcast announcement for an incident cluster."""
    return repo_instance.record_incident_broadcast(payload)


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


# -------------------------------------------------------------------
# Staff & Customer Role-Based Endpoints
# -------------------------------------------------------------------
@app.get("/staff")
def list_staff():
    """Retrieve all support staff members."""
    staff = repo_instance.list_staff()
    return {"total": len(staff), "staff": staff}


@app.get("/staff/{staff_id}")
def get_staff(staff_id: str):
    """Retrieve a single support staff member."""
    member = repo_instance.get_staff(staff_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff '{staff_id}' not found",
        )
    return member


@app.get("/customers")
def list_customers(assigned_staff_id: Optional[str] = None):
    """Retrieve all customers, optionally filtered by assigned_staff_id."""
    customers = repo_instance.list_customers(assigned_staff_id=assigned_staff_id)
    return {"total": len(customers), "assigned_staff_id": assigned_staff_id, "customers": customers}


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str):
    """Retrieve a single customer profile."""
    customer = repo_instance.get_customer(customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{customer_id}' not found",
        )
    return customer


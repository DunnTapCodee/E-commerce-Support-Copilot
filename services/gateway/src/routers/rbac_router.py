"""FastAPI router for Staff & Customer Role-Based endpoints on API Gateway."""
import asyncio
from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, HTTPException, Query, status

from services.gateway.src.config import CONVERSATION_SERVICE_URL, TELEMETRY_SERVICE_URL

router = APIRouter(prefix="/api/v1/copilot", tags=["staff-customers"])


async def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Execute HTTP GET to downstream microservice with clean error mapping."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 404:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=resp.json().get("detail", "Not found"))
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể kết nối đến dịch vụ downstream (Telemetry/Conversation).",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Quá thời gian chờ phản hồi từ dịch vụ downstream.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi downstream: {str(exc)}",
        )


@router.get("/staff")
async def list_staff():
    """Get all support staff members."""
    return await _get_json(f"{TELEMETRY_SERVICE_URL}/staff")


@router.get("/staff/{staff_id}")
async def get_staff(staff_id: str):
    """Get a single support staff member by ID."""
    return await _get_json(f"{TELEMETRY_SERVICE_URL}/staff/{staff_id}")


@router.get("/customers")
async def list_customers(
    assigned_staff_id: Optional[str] = Query(None, description="Filter customers assigned to a specific staff_id"),
):
    """Get customer list, optionally filtered by assigned_staff_id."""
    params = {"assigned_staff_id": assigned_staff_id} if assigned_staff_id else None
    return await _get_json(f"{TELEMETRY_SERVICE_URL}/customers", params=params)


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str):
    """Get single customer profile."""
    return await _get_json(f"{TELEMETRY_SERVICE_URL}/customers/{customer_id}")


@router.get("/customers/{customer_id}/orders")
async def get_customer_orders(customer_id: str):
    """Get order & transaction history for a specific customer."""
    return await _get_json(f"{TELEMETRY_SERVICE_URL}/orders/customer/{customer_id}")


@router.get("/customers/{customer_id}/overview")
async def get_customer_overview(customer_id: str):
    """Get unified customer overview: profile, orders/transactions, and chat sessions."""
    async def _safe_get(url: str, default: Any) -> Any:
        try:
            return await _get_json(url)
        except HTTPException as exc:
            if exc.status_code == 404:
                return default
            raise

    customer_task = _get_json(f"{TELEMETRY_SERVICE_URL}/customers/{customer_id}")
    orders_task = _safe_get(
        f"{TELEMETRY_SERVICE_URL}/orders/customer/{customer_id}",
        {"customer_id": customer_id, "total_orders": 0, "orders": []},
    )
    sessions_task = _safe_get(
        f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/sessions?customer_id={customer_id}",
        [],
    )

    customer_info, orders_info, sessions_info = await asyncio.gather(
        customer_task, orders_task, sessions_task
    )

    return {
        "customer": customer_info,
        "orders": orders_info.get("orders", []),
        "total_orders": orders_info.get("total_orders", 0),
        "chat_sessions": sessions_info if isinstance(sessions_info, list) else [],
    }

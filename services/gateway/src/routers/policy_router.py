"""FastAPI router proxying policy and document management endpoints to Document Service."""
from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from contracts.schemas import (
    PolicyCreateRequest,
    PolicyRollbackRequest,
    RawPolicyFilterRequest,
)
from services.gateway.src.clients import MicroserviceClients

router = APIRouter(prefix="/api/v1/copilot", tags=["policies"])
clients = MicroserviceClients()


async def _proxy_document_call(coro):
    """Safely execute downstream calls to Document Service with error mapping."""
    try:
        return await coro
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể kết nối đến Document Service (port 8004). Vui lòng kiểm tra dịch vụ quản lý tài liệu.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Quá thời gian chờ phản hồi từ Document Service (Timeout).",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi downstream: {str(exc)}",
        )


@router.post("/policy/filter")
async def proxy_policy_filter(request: RawPolicyFilterRequest):
    """Proxy: LLM-based policy metadata extraction from raw text."""
    return await _proxy_document_call(clients.filter_policy(request))


@router.post("/policy/filter-bulk")
async def proxy_policy_filter_bulk(request: RawPolicyFilterRequest):
    """Proxy: LLM-based extraction of multiple policies from raw text/document."""
    return await _proxy_document_call(clients.filter_bulk_policy(request))


@router.post("/policy/parse-file")
async def proxy_parse_file(file: UploadFile = File(...)):
    """Proxy: Extract clean text from uploaded document files (.docx, .pdf, .txt, etc.)."""
    content = await file.read()
    return await _proxy_document_call(clients.parse_file(file.filename or "unknown", content, file.content_type))


@router.post("/policy/create")
async def proxy_policy_create(request: PolicyCreateRequest):
    """Proxy: Persist confirmed policy into KB, re-evaluate is_active, and re-index."""
    return await _proxy_document_call(clients.create_policy(request))


@router.get("/policies")
async def proxy_list_policies():
    """Proxy: List all policies in KB."""
    return await _proxy_document_call(clients.list_policies())


@router.get("/policies/audit-logs")
async def proxy_list_policy_audit_logs():
    """Proxy: List all policy lifecycle audit events and notifications."""
    return await _proxy_document_call(clients.list_policy_audit_logs())


@router.post("/policies/rollback")
async def proxy_rollback_policy(request: PolicyRollbackRequest):
    """Proxy: Rollback a policy to a prior version state."""
    return await _proxy_document_call(clients.rollback_policy(request))


@router.post("/policies/sync-active-status")
async def proxy_sync_active_status():
    """Proxy: Recompute and synchronize is_active status for all policies based on current date."""
    return await _proxy_document_call(clients.sync_active_status())


@router.get("/policies/{doc_id}")
async def proxy_get_policy(doc_id: str):
    """Proxy: Get details of a single policy."""
    return await _proxy_document_call(clients.get_policy(doc_id))


@router.patch("/policies/{doc_id}")
@router.put("/policies/{doc_id}")
async def proxy_update_policy(doc_id: str, updates: Dict[str, Any]):
    """Proxy: Partially update policy, auto-recompute is_active, and log audit event."""
    return await _proxy_document_call(clients.update_policy(doc_id, updates))


@router.delete("/policies/{doc_id}")
async def proxy_delete_policy(
    doc_id: str,
    performed_by: str = Query("Admin", description="User performing deletion"),
    reason: Optional[str] = Query(None, description="Reason for deletion"),
):
    """Proxy: Delete policy, record audit log, and re-index."""
    return await _proxy_document_call(clients.delete_policy(doc_id, performed_by=performed_by, reason=reason))

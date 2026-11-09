"""FastAPI Router for Document and Policy Management (Port 8004)."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from contracts.schemas import (
    PolicyAuditLogEntry,
    PolicyCreateRequest,
    PolicyFilterResult,
    PolicyRollbackRequest,
    PolicyUpdateRequest,
    RawPolicyFilterRequest,
    RetrievedDocument,
)
from services.document_service.src.policy_filter import filter_raw_policy
from services.document_service.src.policy_manager import policy_manager

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post("/filter-preview", response_model=PolicyFilterResult)
async def filter_preview_endpoint(request: RawPolicyFilterRequest):
    """Parse unstructured text via LLM/Heuristic and auto-compute is_active."""
    try:
        return await filter_raw_policy(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trích xuất chính sách thất bại: {str(exc)}",
        )


@router.get("/policies", response_model=List[RetrievedDocument])
def list_policies_endpoint(
    active_only: bool = Query(False, description="Filter only active policies"),
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List all policy documents in the knowledge base."""
    docs = policy_manager.load_policies()
    if active_only:
        docs = [d for d in docs if d.is_active]
    if category:
        docs = [d for d in docs if (d.category or "").lower() == category.lower()]
    return docs


@router.get("/policies/audit-logs", response_model=List[PolicyAuditLogEntry])
def list_audit_logs_endpoint(limit: int = Query(100, ge=1, le=500)):
    """List recent document lifecycle change notifications and audit logs."""
    logs = policy_manager.load_audit_logs()
    return logs[:limit]


@router.post("/policies/sync-active-status")
async def sync_active_status_endpoint():
    """Trigger batch recalculation of is_active status for all policies based on current date."""
    try:
        result = await policy_manager.recompute_all_active_statuses(trigger_rag_sync=True)
        return {"status": "success", "result": result}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi đồng bộ trạng thái chính sách: {str(exc)}",
        )


@router.post("/policies/rollback", response_model=RetrievedDocument)
async def rollback_policy_endpoint(request: PolicyRollbackRequest):
    """Rollback a policy to a prior version/snapshot based on an audit log ID."""
    try:
        return await policy_manager.rollback_policy(request)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hoàn tác chính sách: {str(exc)}",
        )


@router.get("/policies/{doc_id}", response_model=RetrievedDocument)
def get_policy_endpoint(doc_id: str):
    """Get single policy document by ID."""
    doc = policy_manager.get_policy(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy chính sách với mã '{doc_id}'",
        )
    return doc


@router.post("/policies", response_model=RetrievedDocument, status_code=status.HTTP_201_CREATED)
async def create_policy_endpoint(request: PolicyCreateRequest):
    """Save a confirmed policy to knowledge base with automated is_active calculation and audit logging."""
    try:
        return await policy_manager.create_policy(request)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi lưu trữ chính sách: {str(exc)}",
        )


@router.put("/policies/{doc_id}", response_model=RetrievedDocument)
@router.patch("/policies/{doc_id}", response_model=RetrievedDocument)
async def update_policy_endpoint(doc_id: str, updates: Dict[str, Any]):
    """Update policy attributes (dates, content, type) with automated is_active recalculation."""
    try:
        performed_by = updates.pop("performed_by", "Admin")
        reason = updates.pop("reason", None)
        return await policy_manager.update_policy(
            doc_id=doc_id,
            updates=updates,
            performed_by=performed_by,
            reason=reason,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi cập nhật chính sách: {str(exc)}",
        )


@router.delete("/policies/{doc_id}")
async def delete_policy_endpoint(
    doc_id: str,
    performed_by: str = Query("Admin", description="User deleting document"),
    reason: Optional[str] = Query(None, description="Reason for deletion"),
):
    """Delete a policy document and record audit log."""
    try:
        await policy_manager.delete_policy(doc_id, performed_by=performed_by, reason=reason)
        return {"status": "deleted", "doc_id": doc_id}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi xóa chính sách: {str(exc)}",
        )




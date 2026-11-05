"""Policy lifecycle, storage, audit logging, and automated active status management."""
import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx

from contracts.schemas import (
    PolicyAuditLogEntry,
    PolicyCreateRequest,
    PolicyRollbackRequest,
    RetrievedDocument,
)
from services.document_service.src.config import (
    AUDIT_LOGS_PATH,
    POLICIES_PATH,
    RAG_SERVICE_URL,
)


def parse_iso_date(date_str: Optional[str]) -> Optional[date]:
    """Parse string date format (YYYY-MM-DD or DD/MM/YYYY) safely."""
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned = date_str.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def calculate_active_status(
    doc: Union[RetrievedDocument, Dict[str, Any]],
    reference_date: Optional[date] = None,
) -> Tuple[bool, str]:
    """Strictly and automatically evaluate dynamic active status of a policy document.

    Rules:
      - superseded: always False
      - expiration_date set and today > expiration_date: False (Expired)
      - effective_date set and today < effective_date: False (Not yet effective)
      - temporary without dates: False
      - Otherwise: True
    """
    ref_date = reference_date or date.today()

    if isinstance(doc, dict):
        policy_type = (doc.get("policy_type") or "permanent").lower()
        eff_str = doc.get("effective_date")
        exp_str = doc.get("expiration_date")
        doc_id = doc.get("doc_id", "DOC")
    else:
        policy_type = (getattr(doc, "policy_type", "permanent") or "permanent").lower()
        eff_str = doc.effective_date
        exp_str = doc.expiration_date
        doc_id = doc.doc_id

    # 1. Superseded policies are permanently inactive
    if policy_type == "superseded":
        return False, f"Chính sách [{doc_id}] đã bị thay thế (superseded) bởi phiên bản mới hơn."

    eff_date = parse_iso_date(eff_str)
    exp_date = parse_iso_date(exp_str)

    # 2. Check future effective date
    if eff_date and ref_date < eff_date:
        return (
            False,
            f"Chính sách [{doc_id}] chưa đến ngày hiệu lực (ngày bắt đầu: {eff_date.strftime('%Y-%m-%d')}, hiện tại: {ref_date.strftime('%Y-%m-%d')}).",
        )

    # 3. Check expiration date
    if exp_date and ref_date > exp_date:
        return (
            False,
            f"Chính sách [{doc_id}] đã hết hạn vào ngày {exp_date.strftime('%Y-%m-%d')} (hiện tại: {ref_date.strftime('%Y-%m-%d')}).",
        )

    # 4. Temporary policy validation
    if policy_type == "temporary" and not exp_date:
        return (
            False,
            f"Chính sách tạm thời [{doc_id}] thiếu ngày hết hạn (expiration_date).",
        )

    # 5. Active
    return True, f"Chính sách [{doc_id}] đang có hiệu lực áp dụng."


class PolicyManager:
    """Enterprise policy repository with automated active status, audit trails, and rollback."""

    def __init__(self, policies_path: Optional[str] = None, audit_logs_path: Optional[str] = None):
        self.policies_path = POLICIES_PATH if policies_path is None else Path(policies_path)
        self.audit_logs_path = AUDIT_LOGS_PATH if audit_logs_path is None else Path(audit_logs_path)
        self._ensure_storage_exists()

    def _ensure_storage_exists(self):
        self.policies_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.policies_path.exists():
            with open(self.policies_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

        self.audit_logs_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.audit_logs_path.exists():
            with open(self.audit_logs_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def load_policies(self) -> List[RetrievedDocument]:
        """Load all policy documents from persistent JSON."""
        try:
            with open(self.policies_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            return [RetrievedDocument(**item) for item in raw_data]
        except Exception as e:
            print(f"[PolicyManager] Error loading policies: {e}")
            return []

    def save_policies(self, docs: List[RetrievedDocument]):
        """Persist policy documents to JSON."""
        with open(self.policies_path, "w", encoding="utf-8") as f:
            json.dump([doc.model_dump() for doc in docs], f, ensure_ascii=False, indent=2)

    def load_audit_logs(self) -> List[PolicyAuditLogEntry]:
        """Load all audit log entries."""
        try:
            with open(self.audit_logs_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            return [PolicyAuditLogEntry(**item) for item in raw_data]
        except Exception as e:
            print(f"[PolicyManager] Error loading audit logs: {e}")
            return []

    def record_audit_log(
        self,
        action: str,
        doc_id: str,
        doc_title: Optional[str] = None,
        performed_by: str = "Admin",
        reason: Optional[str] = None,
        before_snapshot: Optional[Dict[str, Any]] = None,
        after_snapshot: Optional[Dict[str, Any]] = None,
    ) -> PolicyAuditLogEntry:
        """Create and append an audit log entry."""
        entry = PolicyAuditLogEntry(
            log_id=f"LOG-{uuid.uuid4().hex[:10].upper()}",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            doc_id=doc_id,
            doc_title=doc_title,
            action=action,
            performed_by=performed_by,
            reason=reason,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        logs = self.load_audit_logs()
        logs.insert(0, entry)  # latest first
        with open(self.audit_logs_path, "w", encoding="utf-8") as f:
            json.dump([l.model_dump() for l in logs], f, ensure_ascii=False, indent=2)
        return entry

    async def trigger_rag_sync(self):
        """Notify RAG service to reload KB and re-index vector store."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{RAG_SERVICE_URL}/api/v1/rag/sync-kb")
                if resp.status_code == 200:
                    print("[PolicyManager] Successfully triggered RAG re-index.")
        except Exception as exc:
            print(f"[PolicyManager] RAG sync notification failed (service may be starting): {exc}")

    def get_policy(self, doc_id: str) -> Optional[RetrievedDocument]:
        """Retrieve a policy by ID."""
        docs = self.load_policies()
        for doc in docs:
            if doc.doc_id == doc_id:
                return doc
        return None

    async def create_policy(self, request: PolicyCreateRequest) -> RetrievedDocument:
        """Add a new policy, automatically computing is_active status and logging audit event."""
        docs = self.load_policies()
        doc_dict = request.policy.model_dump()

        # Prevent duplicate ID
        if any(d.doc_id == doc_dict["doc_id"] for d in docs):
            raise ValueError(f"Chính sách với mã '{doc_dict['doc_id']}' đã tồn tại trong hệ thống.")

        # Automated is_active calculation based on dates & type
        is_active, status_reason = calculate_active_status(doc_dict)
        doc_dict["is_active"] = is_active

        new_doc = RetrievedDocument(**doc_dict)
        docs.append(new_doc)
        self.save_policies(docs)

        # Log audit
        self.record_audit_log(
            action="CREATE",
            doc_id=new_doc.doc_id,
            doc_title=new_doc.title,
            performed_by=request.performed_by or "Admin",
            reason=request.reason or f"Tạo mới chính sách. Trạng thái tự động: {'Active' if is_active else 'Inactive'} ({status_reason})",
            before_snapshot=None,
            after_snapshot=new_doc.model_dump(),
        )

        await self.trigger_rag_sync()
        return new_doc

    async def update_policy(
        self,
        doc_id: str,
        updates: Dict[str, Any],
        performed_by: str = "Admin",
        reason: Optional[str] = None,
    ) -> RetrievedDocument:
        """Partially update an existing policy with automatic is_active re-calculation and audit snapshot."""
        docs = self.load_policies()
        found_idx = -1
        for idx, d in enumerate(docs):
            if d.doc_id == doc_id:
                found_idx = idx
                break

        if found_idx == -1:
            raise ValueError(f"Không tìm thấy chính sách với mã '{doc_id}'.")

        target = docs[found_idx]
        before_snapshot = target.model_dump()

        target_dict = target.model_dump()
        target_dict.update({k: v for k, v in updates.items() if k != "doc_id"})

        # Automatically recalculate is_active whenever dates or type change
        auto_active, auto_reason = calculate_active_status(target_dict)
        target_dict["is_active"] = auto_active

        updated_doc = RetrievedDocument(**target_dict)
        docs[found_idx] = updated_doc
        self.save_policies(docs)

        action = "SUPERSEDE" if target_dict.get("policy_type") == "superseded" else "UPDATE"
        self.record_audit_log(
            action=action,
            doc_id=doc_id,
            doc_title=updated_doc.title,
            performed_by=performed_by,
            reason=reason or f"Cập nhật thông tin. Trạng thái tự động: {'Active' if auto_active else 'Inactive'} ({auto_reason})",
            before_snapshot=before_snapshot,
            after_snapshot=updated_doc.model_dump(),
        )

        await self.trigger_rag_sync()
        return updated_doc

    async def delete_policy(
        self, doc_id: str, performed_by: str = "Admin", reason: Optional[str] = None
    ) -> bool:
        """Delete a policy with audit record."""
        docs = self.load_policies()
        found = None
        remaining = []
        for d in docs:
            if d.doc_id == doc_id:
                found = d
            else:
                remaining.append(d)

        if not found:
            raise ValueError(f"Không tìm thấy chính sách với mã '{doc_id}'.")

        self.save_policies(remaining)
        self.record_audit_log(
            action="DELETE",
            doc_id=doc_id,
            doc_title=found.title,
            performed_by=performed_by,
            reason=reason or f"Xóa chính sách [{doc_id}] khỏi hệ thống.",
            before_snapshot=found.model_dump(),
            after_snapshot=None,
        )

        await self.trigger_rag_sync()
        return True

    async def rollback_policy(self, request: PolicyRollbackRequest) -> RetrievedDocument:
        """Rollback a policy to its snapshot recorded in an audit log entry."""
        logs = self.load_audit_logs()
        target_log = None
        for l in logs:
            if l.log_id == request.log_id:
                target_log = l
                break

        if not target_log:
            raise ValueError(f"Không tìm thấy bản ghi Audit Log với mã '{request.log_id}'.")

        target_snapshot = target_log.before_snapshot
        if not target_snapshot:
            raise ValueError(f"Bản ghi '{request.log_id}' không có dữ liệu Before Snapshot để hoàn tác.")

        doc_id = target_log.doc_id
        docs = self.load_policies()
        found_idx = -1
        for idx, d in enumerate(docs):
            if d.doc_id == doc_id:
                found_idx = idx
                break

        current_snapshot = docs[found_idx].model_dump() if found_idx != -1 else None

        # Automatically recalculate is_active for the restored snapshot against today's date
        auto_active, auto_reason = calculate_active_status(target_snapshot)
        target_snapshot["is_active"] = auto_active
        restored_doc = RetrievedDocument(**target_snapshot)

        if found_idx != -1:
            docs[found_idx] = restored_doc
        else:
            docs.append(restored_doc)

        self.save_policies(docs)

        self.record_audit_log(
            action="ROLLBACK",
            doc_id=doc_id,
            doc_title=restored_doc.title,
            performed_by=request.performed_by or "Admin",
            reason=request.reason or f"Hoàn tác về phiên bản trước thao tác '{target_log.action}' (Log ID: {target_log.log_id}). Trạng thái tự động: {'Active' if auto_active else 'Inactive'} ({auto_reason})",
            before_snapshot=current_snapshot,
            after_snapshot=restored_doc.model_dump(),
        )

        await self.trigger_rag_sync()
        return restored_doc

    async def recompute_all_active_statuses(
        self, reference_date: Optional[date] = None, trigger_rag_sync: bool = True
    ) -> Dict[str, Any]:
        """Batch recompute active status for all policies based on current date.

        Automatically triggers system audit events when a policy transitions:
          - True -> False: 'AUTO_EXPIRE'
          - False -> True: 'AUTO_ACTIVATE'
        """
        ref_date = reference_date or date.today()
        docs = self.load_policies()
        changed_docs = []

        for idx, doc in enumerate(docs):
            doc_dict = doc.model_dump()
            prev_status = doc.is_active
            new_status, reason = calculate_active_status(doc_dict, ref_date)

            if prev_status != new_status:
                doc_dict["is_active"] = new_status
                updated_doc = RetrievedDocument(**doc_dict)
                docs[idx] = updated_doc

                action = "AUTO_ACTIVATE" if new_status else "AUTO_EXPIRE"
                self.record_audit_log(
                    action=action,
                    doc_id=doc.doc_id,
                    doc_title=doc.title,
                    performed_by="System (Auto-Scheduler)",
                    reason=f"Hệ thống tự động chuyển trạng thái sang {'Active' if new_status else 'Inactive'} theo mốc ngày {ref_date.strftime('%Y-%m-%d')}. Lý do: {reason}",
                    before_snapshot=doc.model_dump(),
                    after_snapshot=updated_doc.model_dump(),
                )
                changed_docs.append({"doc_id": doc.doc_id, "previous": prev_status, "new": new_status, "reason": reason})

        if changed_docs:
            self.save_policies(docs)
            if trigger_rag_sync:
                await self.trigger_rag_sync()

        return {
            "total_policies": len(docs),
            "updated_count": len(changed_docs),
            "changes": changed_docs,
            "checked_at": ref_date.strftime("%Y-%m-%d"),
        }


# Singleton instance
policy_manager = PolicyManager()

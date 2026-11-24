"""Versioned Runtime Configuration Snapshot & Rollback Registry (Task 6).

Provides immutable configuration versioning (intent_backend, retrieval_method,
model IDs, guardrail thresholds, policy pack version) with +07:00 audit history
and drift / Release-Gate rollback recommendations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from contracts.llm_failover import get_default_openai_model
from contracts.schemas import get_system_now

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = ROOT_DIR / "db_storage" / "release_config_registry.json"


def capture_current_runtime_config(
    policy_pack_version: Optional[str] = None,
    prompt_version: str = "v2.0",
) -> Dict[str, Any]:
    """Read current non-secret runtime configuration parameters from environment."""
    return {
        "intent_backend": os.getenv("INTENT_BACKEND", "llm"),
        "intent_routing_mode": os.getenv("INTENT_ROUTING_MODE", "router"),
        "retrieval_method": os.getenv("RETRIEVAL_METHOD", "bm25"),
        "llm_provider": os.getenv("LLM_PROVIDER", "openai_compatible"),
        "openai_model": get_default_openai_model(),
        "intent_confidence_threshold": float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.60")),
        "faithfulness_threshold": float(os.getenv("FAITHFULNESS_THRESHOLD", "0.70")),
        "active_policy_pack_version": policy_pack_version or "policies.json@52",
        "prompt_version": prompt_version,
    }


class ReleaseConfigRegistry:
    """File-backed versioned snapshot and rollback registry for operational safety."""

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = Path(registry_path or DEFAULT_REGISTRY_PATH)

    def _load(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "active_version_id": None,
                "snapshots": [],
                "rollback_audit_log": [],
            }
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            data.setdefault("active_version_id", None)
            data.setdefault("snapshots", [])
            data.setdefault("rollback_audit_log", [])
            return data
        except Exception:
            return {"active_version_id": None, "snapshots": [], "rollback_audit_log": []}

    def _save(self, data: Dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_snapshots(self) -> Dict[str, Any]:
        """Return active version, all snapshots, and rollback audit trail."""
        data = self._load()
        return {
            "active_version_id": data["active_version_id"],
            "total_snapshots": len(data["snapshots"]),
            "snapshots": data["snapshots"],
            "rollback_audit_log": data["rollback_audit_log"],
        }

    def get_active_snapshot(self) -> Optional[Dict[str, Any]]:
        """Return currently active configuration snapshot, if any."""
        data = self._load()
        active_id = data.get("active_version_id")
        if not active_id:
            return None
        for snap in data["snapshots"]:
            if snap.get("version_id") == active_id:
                return snap
        return None

    def create_snapshot(
        self,
        config: Optional[Dict[str, Any]] = None,
        created_by: str = "Ops Engineer",
        notes: str = "",
        release_gate_status: str = "UNVERIFIED",
        version_id: Optional[str] = None,
        activate: bool = True,
    ) -> Dict[str, Any]:
        """Record a new immutable configuration snapshot and optionally activate it."""
        data = self._load()
        prev_id = data.get("active_version_id")
        vid = (version_id or f"rel-{len(data['snapshots']) + 1}-{uuid.uuid4().hex[:6]}").strip()
        if any(s.get("version_id") == vid for s in data["snapshots"]):
            raise ValueError(f"Snapshot version_id '{vid}' already exists.")

        snapshot = {
            "version_id": vid,
            "created_at": get_system_now(),
            "created_by": created_by,
            "notes": notes,
            "previous_version_id": prev_id,
            "release_gate_status": release_gate_status,
            "config": dict(config) if config is not None else capture_current_runtime_config(),
        }
        data["snapshots"].append(snapshot)
        if activate or not prev_id:
            data["active_version_id"] = vid
        self._save(data)
        return snapshot

    def rollback_to_version(
        self,
        target_version_id: Optional[str] = None,
        reason: str = "",
        performed_by: str = "Ops Engineer",
    ) -> Dict[str, Any]:
        """Roll active config back to target_version_id (or previous_version_id) with mandatory audit reason."""
        clean_reason = (reason or "").strip()
        if not clean_reason:
            raise ValueError("Rollback bắt buộc phải nhập lý do (reason).")

        data = self._load()
        current_id = data.get("active_version_id")
        current_snap = self.get_active_snapshot()

        resolved_target_id = (target_version_id or "").strip()
        if not resolved_target_id and current_snap:
            resolved_target_id = str(current_snap.get("previous_version_id") or "")
        if not resolved_target_id:
            raise ValueError("Không xác định được target_version_id để rollback.")
        if resolved_target_id == current_id:
            raise ValueError(f"Phiên bản '{resolved_target_id}' đang là bản active hiện tại.")

        target_snap = next(
            (s for s in data["snapshots"] if s.get("version_id") == resolved_target_id),
            None,
        )
        if not target_snap:
            raise ValueError(f"Không tìm thấy snapshot '{resolved_target_id}' trong registry.")

        now_ts = get_system_now()
        audit_entry = {
            "rollback_id": f"rb_{uuid.uuid4().hex[:10]}",
            "timestamp": now_ts,
            "from_version_id": current_id,
            "to_version_id": resolved_target_id,
            "performed_by": performed_by,
            "reason": clean_reason,
        }
        data["active_version_id"] = resolved_target_id
        data["rollback_audit_log"].append(audit_entry)
        self._save(data)
        return {
            "status": "ROLLED_BACK",
            "audit_entry": audit_entry,
            "active_snapshot": target_snap,
        }

    def evaluate_drift_and_recommend_rollback(
        self,
        drift_report: Optional[Dict[str, Any]] = None,
        release_report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check drift alerts or RELEASE_BLOCKED status and recommend prior healthy snapshot."""
        triggers: List[str] = []
        if drift_report and drift_report.get("drift_detected"):
            alerts = drift_report.get("alerts") or ["production_drift_detected"]
            triggers.append(f"TELEMETRY_DRIFT: {', '.join(str(a) for a in alerts[:3])}")
        if release_report and release_report.get("release_status") == "RELEASE_BLOCKED (NO-GO)":
            blockers = release_report.get("blockers") or ["release_gate_blocked"]
            triggers.append(f"RELEASE_BLOCKED: {blockers[0]}")

        active = self.get_active_snapshot()
        prev_id = active.get("previous_version_id") if active else None
        return {
            "should_rollback": bool(triggers and prev_id),
            "triggers": triggers,
            "active_version_id": active.get("version_id") if active else None,
            "recommended_target_version_id": prev_id,
        }

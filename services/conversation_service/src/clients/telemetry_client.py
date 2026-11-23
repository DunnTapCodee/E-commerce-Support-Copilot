"""Async client for Telemetry & Mock Order Service."""
from __future__ import annotations

from typing import Any, Dict, Optional
import httpx
from contracts.schemas import AuditLogCreate
from services.conversation_service.src.config import TELEMETRY_SERVICE_URL


class TelemetryServiceClient:
    def __init__(self, base_url: str = TELEMETRY_SERVICE_URL):
        self.base_url = base_url.rstrip("/")

    async def lookup_order(self, order_id_or_key: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{self.base_url}/orders/{order_id_or_key}")
            if resp.status_code == 200:
                return resp.json()
            return None

    async def record_audit_log(self, payload: AuditLogCreate) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(
                    f"{self.base_url}/audit/log",
                    json=payload.model_dump(),
                )
                return resp.status_code in {200, 201}
        except Exception as exc:
            print(f"[TelemetryClient] Audit recording failed: {exc}")
            return False

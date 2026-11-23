"""Deterministic contract, integration, and privacy regression tests.
Runs 100% offline with mocked HTTP transports and temporary files; zero external calls or real DB writes.
"""
import csv
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Set
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from contracts.schemas import (
    GatewayResponse,
    GuardrailResult,
    IntentPredictionResponse,
    PolicyAuditLogEntry,
    RetrievedDocument,
)
from scripts.export_continual_learning_dataset import append_single_interaction_to_csv, redact_pii
from services.gateway.src.main import app as gateway_app
from services.rag_service.src.main import app as rag_app

ROOT_DIR = Path(__file__).resolve().parents[1]


def _extract_ts_interface_fields(ts_text: str, interface_name: str) -> Dict[str, bool]:
    """Parse top-level field names and whether they are required (True) or optional (False)."""
    pattern = re.compile(rf"export\s+interface\s+{re.escape(interface_name)}\s*\{{(.*?)\n\}}", re.DOTALL)
    match = pattern.search(ts_text)
    if not match:
        raise AssertionError(f"Interface '{interface_name}' not found in frontend/src/types/index.ts")
    fields: Dict[str, bool] = {}
    for line in match.group(1).splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("//") or cleaned.startswith("/*"):
            continue
        field_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(\?)?\s*:", cleaned)
        if field_match:
            fields[field_match.group(1)] = field_match.group(2) is None
    return fields


class TestBackendFrontendContracts(unittest.TestCase):
    def test_frontend_required_interface_fields_exist_in_pydantic_contracts(self):
        """All required fields expected by React TypeScript interfaces must exist on backend Pydantic DTOs."""
        ts_path = ROOT_DIR / "frontend" / "src" / "types" / "index.ts"
        ts_text = ts_path.read_text(encoding="utf-8")

        mapping = [
            ("RetrievedDocument", RetrievedDocument),
            ("IntentPredictionResponse", IntentPredictionResponse),
            ("GuardrailResult", GuardrailResult),
            ("GatewayResponse", GatewayResponse),
            ("PolicyAuditLogEntry", PolicyAuditLogEntry),
        ]
        for ts_name, model_cls in mapping:
            ts_fields = _extract_ts_interface_fields(ts_text, ts_name)
            pydantic_fields: Set[str] = set(model_cls.model_fields.keys())
            required_ts_fields = {name for name, is_req in ts_fields.items() if is_req}
            missing = required_ts_fields - pydantic_fields
            self.assertEqual(
                missing,
                set(),
                f"Frontend required fields missing from backend {ts_name}: {missing}",
            )

    def test_rag_retrieve_route_declares_list_of_retrieved_document(self):
        """Verify RAG Service /retrieve route declares List[RetrievedDocument] (JSON array) contract."""
        retrieve_routes = [r for r in rag_app.routes if getattr(r, "path", None) == "/retrieve"]
        self.assertEqual(len(retrieve_routes), 1)
        self.assertEqual(retrieve_routes[0].response_model, List[RetrievedDocument])


class TestGatewayPrimaryAndFallbackIntegration(unittest.TestCase):
    def _mock_factory(self, handler):
        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        return lambda *args, **kwargs: real_async_client(
            transport=transport, **{k: v for k, v in kwargs.items() if k != "transport"}
        )

    def test_gateway_primary_path_returns_valid_gateway_response(self):
        """Primary Gateway path proxies to Conversation Service and validates GatewayResponse schema."""
        conv_payload = {
            "interaction_id": "int-primary-1",
            "intent": {
                "intent": "return_policy",
                "confidence": 0.94,
                "is_in_scope": True,
                "model_name": "mainnewnol/gpt-oss-120b",
                "all_probabilities": {"return_policy": 0.94},
            },
            "guardrail": {
                "allow_llm": True,
                "action_type": "PROCEED_TO_LLM",
                "reason": "OK",
            },
            "citations": [
                {
                    "doc_id": "POL-RET-001",
                    "title": "Chính sách đổi trả",
                    "content": "Đổi trả 30 ngày.",
                    "is_active": True,
                }
            ],
            "draft_text": "Theo [POL-RET-001], bạn có thể đổi trả trong 30 ngày.",
            "components_used": {"intent_classifier": "LLM Intent Classifier (mainnewnol/gpt-oss-120b)"},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/api/v1/conversation/chat"):
                return httpx.Response(200, json=conv_payload)
            return httpx.Response(404, json={"detail": request.url.path})

        factory = self._mock_factory(handler)
        with patch("services.gateway.src.main.httpx.AsyncClient", side_effect=factory):
            with TestClient(gateway_app) as client:
                resp = client.post(
                    "/api/v1/copilot/query",
                    json={"query": "Chính sách đổi trả?", "session_id": "sess-primary-1"},
                )

        self.assertEqual(resp.status_code, 200)
        parsed = GatewayResponse(**resp.json())
        self.assertEqual(parsed.interaction_id, "int-primary-1")
        self.assertEqual(parsed.intent.model_name, "mainnewnol/gpt-oss-120b")
        self.assertEqual(len(parsed.citations), 1)
        self.assertTrue(parsed.guardrail.allow_llm)

    def test_gateway_sse_stream_fallback_emits_meta_token_done_with_citations(self):
        """When Conversation Service streaming fails, /query_stream synthesizes meta, token, done SSE events."""
        retrieved_docs = [
            {
                "doc_id": "POL-RET-001",
                "title": "Chính sách đổi trả",
                "content": "Đổi trả trong vòng 30 ngày cho Tiki Trading.",
                "version": "2.0",
                "is_active": True,
                "policy_type": "permanent",
                "effective_date": "2024-01-01",
                "expiration_date": None,
            }
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/api/v1/conversation/chat_stream") or path.endswith("/api/v1/conversation/chat"):
                raise httpx.ConnectError("Conversation service unreachable", request=request)
            if path.endswith("/predict"):
                return httpx.Response(
                    200,
                    json={
                        "intent": "return_policy",
                        "confidence": 0.92,
                        "is_in_scope": True,
                        "model_name": "mainnewnol/gpt-oss-120b",
                        "all_probabilities": {"return_policy": 0.92},
                    },
                )
            if "/orders/" in path:
                return httpx.Response(404, json={"detail": "Not found"})
            if path.endswith("/retrieve"):
                return httpx.Response(200, json=retrieved_docs)
            if path.endswith("/generate"):
                return httpx.Response(
                    200,
                    json={
                        "draft_text": "Theo chính sách [POL-RET-001], bạn có thể đổi trả trong vòng 30 ngày cho Tiki Trading.",
                        "citations": retrieved_docs,
                        "latency_ms": 15,
                        "generation_mode": "openai_compatible",
                    },
                )
            if path.endswith("/audit/log"):
                return httpx.Response(200, json={"status": "logged"})
            return httpx.Response(404, json={"detail": path})

        factory = self._mock_factory(handler)
        with patch("services.gateway.src.main.httpx.AsyncClient", side_effect=factory), patch(
            "services.gateway.src.clients.httpx.AsyncClient", side_effect=factory
        ):
            with TestClient(gateway_app) as client:
                resp = client.post(
                    "/api/v1/copilot/query_stream",
                    json={"query": "Đổi trả Tiki Trading bao nhiêu ngày?", "session_id": "sess-sse-1"},
                )

        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertIn("event: meta", text)
        self.assertIn("event: token", text)
        self.assertIn("event: done", text)

        events = {}
        for block in text.strip().split("\n\n"):
            lines = block.splitlines()
            ev_name = lines[0].replace("event:", "").strip()
            ev_data = json.loads(lines[1].replace("data:", "", 1).strip())
            events[ev_name] = ev_data

        self.assertEqual(len(events["meta"]["citations"]), 1)
        self.assertEqual(events["meta"]["citations"][0]["doc_id"], "POL-RET-001")
        self.assertIn("30 ngày", events["done"]["draft_text"])

    def test_gateway_fallback_escalates_when_intent_service_unreachable(self):
        """When both Conversation Service and Intent Service are unreachable, Gateway fails closed to ESCALATE_HUMAN."""
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/api/v1/conversation/chat") or path.endswith("/predict"):
                raise httpx.ConnectError("Service unreachable", request=request)
            if "/orders/" in path:
                return httpx.Response(404, json={"detail": "Not found"})
            if path.endswith("/audit/log"):
                return httpx.Response(200, json={"status": "logged"})
            return httpx.Response(404, json={"detail": path})

        factory = self._mock_factory(handler)
        with patch("services.gateway.src.main.httpx.AsyncClient", side_effect=factory), patch(
            "services.gateway.src.clients.httpx.AsyncClient", side_effect=factory
        ):
            with TestClient(gateway_app) as client:
                resp = client.post(
                    "/api/v1/copilot/query",
                    json={"query": "Kiểm tra đơn ORD-1001", "session_id": "sess-down-1"},
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["guardrail"]["allow_llm"])
        self.assertEqual(data["guardrail"]["action_type"], "ESCALATE_HUMAN")
        self.assertEqual(data["generation_mode"], "blocked_intent_guard")
        self.assertIn("Unavailable", data["components_used"]["intent_classifier"])


class TestPrivacyContinualLearningCsvExport(unittest.TestCase):
    def test_pii_redaction_masks_phone_email_and_id_but_preserves_order_id(self):
        """PII redaction protects phone numbers, emails, and numeric IDs while keeping ORD-XXXX intact."""
        raw = "Kiểm tra đơn ORD-1001 cho SĐT 0912345678, email test.user@example.com, CCCD 001234567890"
        cleaned = redact_pii(raw)
        self.assertIn("ORD-1001", cleaned)
        self.assertNotIn("0912345678", cleaned)
        self.assertNotIn("test.user@example.com", cleaned)
        self.assertNotIn("001234567890", cleaned)
        self.assertIn("[REDACTED_PHONE]", cleaned)
        self.assertIn("[REDACTED_EMAIL]", cleaned)
        self.assertIn("[REDACTED_NUMBER]", cleaned)

    def test_append_single_interaction_redacts_pii_and_honors_disable_toggle(self):
        """CSV export redacts PII on write and can be disabled cleanly via env var."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "cl.csv"

            with patch.dict(os.environ, {"DISABLE_CONTINUAL_LEARNING_CSV_EXPORT": "true"}, clear=False):
                append_single_interaction_to_csv(
                    interaction_id="id-disabled",
                    customer_query="SĐT 0987654321 đơn ORD-1001",
                    predicted_intent="track_order",
                    confidence=0.9,
                    output_path=csv_path,
                )
                self.assertFalse(csv_path.exists())

            with patch.dict(os.environ, {"DISABLE_CONTINUAL_LEARNING_CSV_EXPORT": ""}, clear=False):
                append_single_interaction_to_csv(
                    interaction_id="id-enabled",
                    customer_query="SĐT 0987654321 email a@b.vn đơn ORD-1001",
                    predicted_intent="track_order",
                    confidence=0.92,
                    rewritten_query="Tra cứu đơn ORD-1001 SĐT 0987654321",
                    output_path=csv_path,
                )
                self.assertTrue(csv_path.exists())
                rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
                self.assertEqual(len(rows), 1)
                self.assertNotIn("0987654321", rows[0]["raw_user_query"])
                self.assertNotIn("a@b.vn", rows[0]["raw_user_query"])
                self.assertNotIn("0987654321", rows[0]["training_input"])
                self.assertIn("ORD-1001", rows[0]["training_input"])


if __name__ == "__main__":
    unittest.main()

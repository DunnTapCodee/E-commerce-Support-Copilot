"""Regression tests for Gateway fallback handling of RAG Service /retrieve JSON responses."""
import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from contracts.schemas import RetrievedDocument
from services.gateway.src.clients import MicroserviceClients
from services.gateway.src.main import app


class TestGatewayRagFallback(unittest.TestCase):
    def _mock_async_client_factory(self, handler):
        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def _factory(*args, **kwargs):
            kwargs.pop("transport", None)
            return real_async_client(transport=transport, *args, **kwargs)

        return _factory

    def test_retrieve_policies_parses_json_array_response(self):
        """MicroserviceClients.retrieve_policies must accept JSON array returned by rag_service /retrieve."""
        captured_requests = []
        payload = [
            {
                "doc_id": "POL-RET-001",
                "category": "return_refund",
                "title": "Chính sách đổi trả tiêu chuẩn",
                "content": "Khách hàng có thể đổi trả trong vòng 30 ngày cho Tiki Trading.",
                "version": "2.0",
                "is_active": True,
                "policy_type": "permanent",
                "effective_date": "2024-01-01",
                "expiration_date": None,
                "tags": ["đổi trả"],
                "score": 0.91,
            }
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append((request.method, str(request.url), json.loads(request.content.decode("utf-8"))))
            return httpx.Response(200, json=payload)

        factory = self._mock_async_client_factory(handler)
        clients = MicroserviceClients()

        with patch("services.gateway.src.clients.httpx.AsyncClient", side_effect=factory):
            docs = asyncio.run(
                clients.retrieve_policies(
                    query="đổi trả hàng trong bao lâu",
                    intent="return_policy",
                    top_k=3,
                    filter_active_only=True,
                )
            )

        self.assertEqual(len(docs), 1)
        self.assertIsInstance(docs[0], RetrievedDocument)
        self.assertEqual(docs[0].doc_id, "POL-RET-001")
        self.assertEqual(docs[0].title, "Chính sách đổi trả tiêu chuẩn")
        self.assertAlmostEqual(docs[0].score, 0.91)
        self.assertEqual(len(captured_requests), 1)
        self.assertTrue(captured_requests[0][1].endswith("/retrieve"))
        self.assertEqual(
            captured_requests[0][2],
            {
                "query": "đổi trả hàng trong bao lâu",
                "intent": "return_policy",
                "top_k": 3,
                "filter_active_only": True,
            },
        )

    def test_retrieve_policies_handles_empty_array_and_legacy_dict(self):
        """Empty JSON array and legacy {'documents': [...]} wrapper remain supported."""
        clients = MicroserviceClients()

        empty_factory = self._mock_async_client_factory(lambda req: httpx.Response(200, json=[]))
        with patch("services.gateway.src.clients.httpx.AsyncClient", side_effect=empty_factory):
            self.assertEqual(asyncio.run(clients.retrieve_policies("test")), [])

        wrapped_payload = {
            "documents": [
                {
                    "doc_id": "POL-ORD-001",
                    "title": "Tra cứu đơn hàng",
                    "content": "Kiểm tra trạng thái trong mục Đơn hàng của tôi.",
                    "is_active": True,
                }
            ]
        }
        wrapped_factory = self._mock_async_client_factory(lambda req: httpx.Response(200, json=wrapped_payload))
        with patch("services.gateway.src.clients.httpx.AsyncClient", side_effect=wrapped_factory):
            docs = asyncio.run(clients.retrieve_policies("tra cứu đơn"))
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].doc_id, "POL-ORD-001")

    def test_retrieve_policies_rejects_unexpected_json_shape(self):
        """Unexpected non-list/non-dict JSON payloads raise ValueError clearly."""
        clients = MicroserviceClients()

        invalid_factory = self._mock_async_client_factory(lambda req: httpx.Response(200, json="invalid-payload"))
        with patch("services.gateway.src.clients.httpx.AsyncClient", side_effect=invalid_factory):
            with self.assertRaises(ValueError):
                asyncio.run(clients.retrieve_policies("test"))

        invalid_docs_factory = self._mock_async_client_factory(
            lambda req: httpx.Response(200, json={"documents": "not-a-list"})
        )
        with patch("services.gateway.src.clients.httpx.AsyncClient", side_effect=invalid_docs_factory):
            with self.assertRaises(ValueError):
                asyncio.run(clients.retrieve_policies("test"))

    def test_gateway_fallback_succeeds_when_rag_retrieve_returns_json_array(self):
        """End-to-end Gateway fallback uses JSON array citations instead of blocking on policy guard."""
        called_paths = []
        retrieved_docs = [
            {
                "doc_id": "POL-RET-001",
                "category": "return_refund",
                "title": "Chính sách đổi trả tiêu chuẩn",
                "content": "Khách hàng có thể đổi trả trong vòng 30 ngày đối với Tiki Trading hoặc 7 ngày đối với nhà bán đối tác.",
                "version": "2.0",
                "is_active": True,
                "policy_type": "permanent",
                "effective_date": "2024-01-01",
                "expiration_date": None,
                "tags": ["đổi trả"],
                "score": 0.92,
            }
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            called_paths.append(path)
            if path.endswith("/api/v1/conversation/chat"):
                raise httpx.ConnectError("Conversation service down", request=request)
            if path.endswith("/predict"):
                return httpx.Response(
                    200,
                    json={
                        "intent": "return_policy",
                        "confidence": 0.93,
                        "is_in_scope": True,
                        "all_probabilities": {"return_policy": 0.93},
                    },
                )
            if "/orders/" in path:
                return httpx.Response(404, json={"detail": "Not found"})
            if path.endswith("/retrieve"):
                return httpx.Response(200, json=retrieved_docs)
            if path.endswith("/generate"):
                body = json.loads(request.content.decode("utf-8"))
                self.assertEqual(len(body["citations"]), 1)
                self.assertEqual(body["citations"][0]["doc_id"], "POL-RET-001")
                return httpx.Response(
                    200,
                    json={
                        "draft_text": "Theo chính sách [POL-RET-001], bạn có thể đổi trả trong vòng 30 ngày đối với Tiki Trading hoặc 7 ngày đối với nhà bán đối tác.",
                        "citations": retrieved_docs,
                        "latency_ms": 12,
                        "generation_mode": "mock_rag",
                    },
                )
            if path.endswith("/audit/log"):
                return httpx.Response(200, json={"status": "logged"})
            return httpx.Response(404, json={"detail": f"Unexpected path: {path}"})

        factory = self._mock_async_client_factory(handler)

        with patch("services.gateway.src.main.httpx.AsyncClient", side_effect=factory), patch(
            "services.gateway.src.clients.httpx.AsyncClient", side_effect=factory
        ):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/copilot/query",
                    json={"query": "Chính sách đổi trả Tiki Trading bao nhiêu ngày?", "session_id": "sess-fallback-1"},
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["generation_mode"], "mock_rag")
        self.assertTrue(data["guardrail"]["allow_llm"])
        self.assertEqual(data["guardrail"]["action_type"], "PROCEED_TO_LLM")
        self.assertEqual(len(data["citations"]), 1)
        self.assertEqual(data["citations"][0]["doc_id"], "POL-RET-001")
        self.assertIn("30 ngày", data["draft_text"])
        self.assertEqual(data["components_used"]["retrieval_engine"], "Direct Policy Retrieval (1 tài liệu)")
        self.assertIn("/retrieve", called_paths)
        self.assertIn("/generate", called_paths)

    def test_gateway_fallback_blocks_when_rag_retrieve_returns_empty_array(self):
        """Empty JSON array from RAG Service triggers policy guard escalation cleanly."""
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/api/v1/conversation/chat"):
                raise httpx.ConnectError("Conversation service down", request=request)
            if path.endswith("/predict"):
                return httpx.Response(
                    200,
                    json={
                        "intent": "return_policy",
                        "confidence": 0.91,
                        "is_in_scope": True,
                        "all_probabilities": {"return_policy": 0.91},
                    },
                )
            if "/orders/" in path:
                return httpx.Response(404, json={"detail": "Not found"})
            if path.endswith("/retrieve"):
                return httpx.Response(200, json=[])
            if path.endswith("/audit/log"):
                return httpx.Response(200, json={"status": "logged"})
            return httpx.Response(404, json={"detail": f"Unexpected path: {path}"})

        factory = self._mock_async_client_factory(handler)

        with patch("services.gateway.src.main.httpx.AsyncClient", side_effect=factory), patch(
            "services.gateway.src.clients.httpx.AsyncClient", side_effect=factory
        ):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/copilot/query",
                    json={"query": "Chính sách không tồn tại", "session_id": "sess-fallback-2"},
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["generation_mode"], "blocked_policy_guard")
        self.assertFalse(data["guardrail"]["allow_llm"])
        self.assertEqual(data["guardrail"]["action_type"], "ESCALATE_HUMAN")
        self.assertEqual(data["citations"], [])


if __name__ == "__main__":
    unittest.main()

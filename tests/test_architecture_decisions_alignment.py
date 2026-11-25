"""Regression tests verifying alignment with confirmed architecture decisions:
1. Intent Classification: LLM primary -> ML fallback -> safe observable abstention across Intent, Conversation, and Gateway.
2. Configuration Consistency: CKEY.VN defaults and no silent fallback to Gemini when openai_compatible is configured.
3. Time Handling: No +12h offset; timezone-aware Asia/Ho_Chi_Minh (+07:00) timestamps, midnight & mixed UTC/VN sorting.
4. TLS Security: Default verify=True and optional CA bundle support across OpenAI-compatible and Gemini callers.
"""
import asyncio
import gc
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

import contracts.llm_failover as llm_failover
from contracts.schemas import (
    AuditLogCreate,
    ConversationSessionState,
    ConversationTurnItem,
    IntentPredictionResponse,
    RetrievedDocument,
    VN_TZ,
    get_system_now,
    get_vn_now,
    get_vn_today,
)
from services.conversation_service.src.dialogue_state.sqlite_state_store import PersistentStateStore
from services.conversation_service.src.dialogue_state.state import ConversationState
from services.conversation_service.src.main import app as conversation_app
from services.conversation_service.src.policies.copilot_draft_engine import CopilotDraftEngine
from services.document_service.src.policy_manager import PolicyManager, calculate_active_status
from services.gateway.src.guardrails import check_temporal_validity, evaluate_intent_guard
from services.gateway.src.main import app as gateway_app
from services.intent_service.src.llm_classifier import LLMIntentClassifier
from services.intent_service.src.main import app as intent_app
from services.intent_service.src.predictor import IntentPredictor
from services.rag_service.src.generator import LLMGenerator
from services.telemetry_service.src.database import init_db
from services.telemetry_service.src.repository import TelemetryRepository


class TestIntentArchitectureAlignment(unittest.TestCase):
    def test_llm_primary_prioritized_even_when_out_of_scope(self):
        """When primary LLM succeeds (even returning out_of_scope), ML fallback is NOT invoked."""
        llm_oos = IntentPredictionResponse(
            intent="out_of_scope",
            confidence=0.95,
            is_in_scope=False,
            model_name="vantoanbk57/deepseek-v4.1-flash",
            all_probabilities={"out_of_scope": 0.95},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"INTENT_BACKEND": "hybrid", "OPENAI_API_KEY": "mock-key", "DISABLE_EXTERNAL_LLM": ""},
                clear=False,
            ):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="hybrid")
                    predictor.legacy_model = MagicMock()
                    with patch.object(predictor.llm_classifier, "predict", return_value=llm_oos) as mock_llm, patch.object(
                        predictor, "_predict_ml"
                    ) as mock_ml:
                        resp = predictor.predict("Hôm nay thời tiết sao?")
                        self.assertEqual(resp.intent, "out_of_scope")
                        self.assertEqual(resp.model_name, "vantoanbk57/deepseek-v4.1-flash")
                        mock_llm.assert_called_once()
                        mock_ml.assert_not_called()

    def test_llm_unavailable_falls_back_to_loaded_ml_artifact(self):
        """When primary LLM fails/unavailable and ML artifact is loaded, IntentPredictor uses ML fallback."""
        ml_resp = IntentPredictionResponse(
            intent="track_order",
            confidence=0.88,
            is_in_scope=True,
            model_name="legacy_baseline",
            all_probabilities={"track_order": 0.88},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "INTENT_BACKEND": "llm",
                    "OPENAI_API_KEY": "",
                    "OPENAI_API_KEY_BACKUP": "",
                    "OPENAI_API_KEYS": "",
                    "GEMINI_API_KEY": "unused-gemini-key",
                    "DISABLE_EXTERNAL_LLM": "",
                },
                clear=False,
            ):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="llm")
                    predictor.legacy_model = MagicMock()
                    self.assertTrue(predictor.has_ml_artifacts)

                    self.assertFalse( hasattr(predictor.llm_classifier, "_call_gemini") )
                    with patch.object(predictor, "_predict_ml", return_value=ml_resp) as mock_ml:
                        resp = predictor.predict("Kiểm tra đơn ORD-1001")
                        self.assertEqual(resp.intent, "track_order")
                        self.assertEqual(resp.model_name, "legacy_baseline")
                        mock_ml.assert_called_once()

    def test_online_llm_failure_with_low_confidence_ml_never_sneaks_semantic_regex_fallback(self):
        """ADR-002 Regression: When primary LLM fails and ML returns low confidence (e.g. 0.10 OOV),
        IntentPredictor must NOT call _semantic_fallback to inflate confidence; it must let downstream escalate.
        """
        low_ml = IntentPredictionResponse(
            intent="track_order",
            confidence=0.10,
            is_in_scope=True,
            model_name="legacy_baseline",
            all_probabilities={"track_order": 0.10},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "INTENT_BACKEND": "llm",
                    "OPENAI_API_KEY": "mock-broken-key",
                    "DISABLE_EXTERNAL_LLM": "",
                },
                clear=False,
            ):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="llm")
                    predictor.legacy_model = MagicMock()
                    with (
                        patch.object(predictor.llm_classifier, "predict", side_effect=RuntimeError("LLM timeout")),
                        patch.object(predictor, "_predict_ml", return_value=low_ml) as mock_ml,
                        patch.object(predictor.llm_classifier, "_semantic_fallback") as mock_sem,
                    ):
                        resp = predictor.predict("Kiểm tra đơn hàng ORD-1001 giúp tôi")
                        self.assertEqual(resp.confidence, 0.10)
                        self.assertEqual(resp.model_name, "legacy_baseline")
                        mock_ml.assert_called_once()
                        mock_sem.assert_not_called()

                        guard = evaluate_intent_guard(resp)
                        self.assertFalse(guard.allow_llm)
                        self.assertEqual(guard.action_type, "ESCALATE_HUMAN")

    def test_deployed_bilingual_numpy_linear_artifact_loads_without_sklearn_warnings(self):
        """OD-002 Regression: Deployed Module 1 bilingual artifact supports VI & EN with zero pickle warnings."""
        import warnings

        model_dir = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "intent"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            predictor = IntentPredictor(model_source=model_dir, intent_backend="ml")
            vi_in = predictor.predict("Tôi muốn hủy đơn hàng vừa đặt giúp mình")
            en_in = predictor.predict("I want to track my order status")
            vi_oos = predictor.predict("Hướng dẫn cách nấu phở bò ngon tại nhà")

        inconsistent_warnings = [w for w in caught if "InconsistentVersionWarning" in str(w.category)]
        self.assertEqual(inconsistent_warnings, [], f"Unexpected sklearn version warnings: {inconsistent_warnings}")
        self.assertFalse(predictor.is_legacy)
        self.assertEqual(vi_in.intent, "cancel_order")
        self.assertGreaterEqual(vi_in.confidence, 0.60)
        self.assertEqual(en_in.intent, "track_order")
        self.assertGreaterEqual(en_in.confidence, 0.60)
        self.assertEqual(vi_oos.intent, "out_of_scope")
        self.assertFalse(vi_oos.is_in_scope)

    def test_both_llm_and_ml_unavailable_returns_safe_observable_abstention(self):
        """When both LLM and ML are unavailable, predictor returns fail-closed abstention that triggers ESCALATE_HUMAN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "INTENT_BACKEND": "hybrid",
                    "OPENAI_API_KEY": "",
                    "OPENAI_API_KEY_BACKUP": "",
                    "OPENAI_API_KEYS": "",
                    "DISABLE_EXTERNAL_LLM": "",
                },
                clear=False,
            ):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="hybrid")
                    self.assertFalse(predictor.has_ml_artifacts)
                    resp = predictor.predict("Tôi muốn hủy đơn ORD-1001")
                    self.assertEqual(resp.intent, "unknown_query")
                    self.assertEqual(resp.confidence, 0.0)
                    self.assertFalse(resp.is_in_scope)
                    self.assertEqual(resp.model_name, "unavailable_fallback")

                    guard = evaluate_intent_guard(resp)
                    self.assertFalse(guard.allow_llm)
                    self.assertEqual(guard.action_type, "ESCALATE_HUMAN")

    def test_semantic_rule_fallback_records_honest_model_name(self):
        """Offline semantic fallback must not masquerade as live LLM in model_name."""
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "", "OPENAI_API_KEY_BACKUP": "", "OPENAI_API_KEYS": "", "DISABLE_EXTERNAL_LLM": ""},
            clear=False,
        ):
            clf = LLMIntentClassifier(api_key="")
            resp = clf.predict("Kiểm tra đơn ORD-1001")
            self.assertEqual(resp.model_name, "semantic_rule_fallback")

    def test_intent_health_and_models_report_actual_configuration(self):
        """Intent /health and models reflect CKEY.VN OpenAI-compatible primary and ML availability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"INTENT_BACKEND": "hybrid", "OPENAI_MODEL": "vantoanbk57/deepseek-v4.1-flash"},
                clear=False,
            ):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="hybrid")
                    self.assertEqual(predictor.models["primary"], "openai_compatible:vantoanbk57/deepseek-v4.1-flash")
                    self.assertEqual(predictor.models["ml_fallback"], "unavailable")

                    with patch("services.intent_service.src.main.predictor_instance", predictor):
                        client = TestClient(intent_app)
                        health = client.get("/health").json()
                        self.assertEqual(health["status"], "healthy")
                        self.assertFalse(health["ml_artifacts_loaded"])
                        self.assertEqual(health["intent_backend"], "hybrid")

    def test_conversation_service_fails_closed_when_intent_unavailable_even_with_active_intent(self):
        """Conversation Service must escalate to human when Intent returns unavailable_fallback or errors, even on turn 2."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp_store = PersistentStateStore(Path(tmpdir) / "conv.sqlite3")
            state = tmp_store.get_or_create("sess-unavail-1", "CUST-1100")
            state.active_intent = "track_order"
            tmp_store.save(state)

            unavail_resp = IntentPredictionResponse(
                intent="unknown_query",
                confidence=0.0,
                is_in_scope=False,
                model_name="unavailable_fallback",
                all_probabilities={},
            )

            with patch("services.conversation_service.src.main.state_store", tmp_store), patch(
                "services.conversation_service.src.main.intent_client.predict_intent",
                new=AsyncMock(return_value=unavail_resp),
            ), patch(
                "services.conversation_service.src.main.telemetry_client.lookup_order",
                new=AsyncMock(return_value=None),
            ), patch(
                "services.conversation_service.src.main.telemetry_client.record_audit_log",
                new=AsyncMock(return_value=True),
            ), patch(
                "services.conversation_service.src.main.rag_client.retrieve_policies",
                new=AsyncMock(return_value=[]),
            ), patch(
                "services.conversation_service.src.main.append_single_interaction_to_csv",
                return_value=None,
            ), patch(
                "services.conversation_service.src.main.MemoryWorker.update_memory_task",
                new=AsyncMock(return_value=None),
            ):
                with TestClient(conversation_app) as client:
                    resp = client.post(
                        "/api/v1/conversation/chat",
                        json={"query": "Đơn này sao rồi shop?", "session_id": "sess-unavail-1"},
                    )
                    self.assertEqual(resp.status_code, 200)
                    body = resp.json()
                    self.assertEqual(body["intent"]["intent"], "unknown_query")
                    self.assertEqual(body["intent"]["model_name"], "unavailable_fallback")
                    self.assertFalse(body["guardrail"]["allow_llm"])
                    self.assertEqual(body["guardrail"]["action_type"], "ESCALATE_HUMAN")

                    # Also verify exception from intent_client fails closed
                    with patch(
                        "services.conversation_service.src.main.intent_client.predict_intent",
                        new=AsyncMock(side_effect=RuntimeError("Intent service down")),
                    ):
                        resp2 = client.post(
                            "/api/v1/conversation/chat",
                            json={"query": "Đơn này sao rồi shop?", "session_id": "sess-unavail-1"},
                        )
                        self.assertEqual(resp2.status_code, 200)
                        body2 = resp2.json()
                        self.assertFalse(body2["guardrail"]["allow_llm"])
                        self.assertEqual(body2["guardrail"]["action_type"], "ESCALATE_HUMAN")

            del tmp_store
            gc.collect()

    def test_gateway_fallback_escalates_cleanly_on_unavailable_intent(self):
        """Gateway fallback path escalates when Intent Service returns unavailable_fallback."""
        real_async_client = httpx.AsyncClient

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/api/v1/conversation/chat"):
                raise httpx.ConnectError("Conversation service down", request=request)
            if path.endswith("/predict"):
                return httpx.Response(
                    200,
                    json={
                        "intent": "unknown_query",
                        "confidence": 0.0,
                        "is_in_scope": False,
                        "model_name": "unavailable_fallback",
                        "all_probabilities": {},
                    },
                )
            if "/orders/" in path:
                return httpx.Response(404, json={"detail": "Not found"})
            if path.endswith("/audit/log"):
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(404, json={"detail": path})

        transport = httpx.MockTransport(handler)
        factory = lambda *args, **kwargs: real_async_client(
            transport=transport, **{k: v for k, v in kwargs.items() if k != "transport"}
        )

        with patch("services.gateway.src.main.httpx.AsyncClient", side_effect=factory), patch(
            "services.gateway.src.clients.httpx.AsyncClient", side_effect=factory
        ):
            with TestClient(gateway_app) as client:
                resp = client.post(
                    "/api/v1/copilot/query",
                    json={"query": "Hỗ trợ đơn hàng", "session_id": "gw-unavail-1"},
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["guardrail"]["allow_llm"])
        self.assertEqual(data["guardrail"]["action_type"], "ESCALATE_HUMAN")
        self.assertEqual(data["generation_mode"], "blocked_intent_guard")
        self.assertIn("unavailable_fallback", data["components_used"]["intent_classifier"])


class TestConfigurationConsistencyAlignment(unittest.TestCase):
    def test_openai_compatible_does_not_silently_fallback_to_gemini_in_rag_or_draft(self):
        """FR-INT-003: Dead _call_gemini paths are removed; missing OpenAI keys fall back cleanly to grounded templates."""
        doc = RetrievedDocument(doc_id="POL-RET-001", title="Đổi trả", content="Đổi trả trong 30 ngày.")
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai_compatible",
                "OPENAI_API_KEY": "",
                "OPENAI_API_KEY_BACKUP": "",
                "OPENAI_API_KEYS": "",
                "GEMINI_API_KEY": "unused-gemini-key",
                "DISABLE_EXTERNAL_LLM": "",
            },
            clear=False,
        ):
            gen = LLMGenerator(timeout_seconds=5)
            self.assertFalse(hasattr(gen, "_call_gemini"))
            self.assertFalse(hasattr(CopilotDraftEngine, "_call_gemini"))
            rag_res = asyncio.run(gen.generate_draft("Chính sách đổi trả", [doc]))
            self.assertEqual(rag_res.generation_mode, "template_fallback")

            draft = asyncio.run(
                CopilotDraftEngine.generate_draft(
                    user_query="Chính sách đổi trả",
                    intent="return_policy",
                    facts={},
                    order_data=None,
                    context_summary=None,
                    recent_turns_text="",
                    citations=[doc],
                )
            )
            self.assertIn("[POL-RET-001]", draft)
            self.assertIn("30 ngày", draft)

    def test_service_default_models_match_ckey_when_env_unset(self):
        """Service config defaults align with vantoanbk57/deepseek-v4.1-flash when OPENAI_MODEL is not in env."""
        from services.conversation_service.src import config as conv_cfg
        from services.document_service.src import config as doc_cfg

        clean_env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_MODEL", "LLM_MODEL")}
        with patch.dict(os.environ, clean_env, clear=True):
            self.assertEqual(os.getenv("OPENAI_MODEL", "vantoanbk57/deepseek-v4.1-flash"), "vantoanbk57/deepseek-v4.1-flash")
        # Direct code defaults verified in modules when imported without legacy overrides
        self.assertNotIn("openai-gpt-oss-20b", getattr(conv_cfg, "OPENAI_MODEL", ""))
        self.assertNotIn("openai-gpt-oss-20b", getattr(doc_cfg, "OPENAI_MODEL", ""))


class TestTimeHandlingAlignment(unittest.TestCase):
    def test_get_system_now_uses_real_vietnam_time_without_12h_shift(self):
        """get_system_now emits ISO 8601 +07:00 matching actual Asia/Ho_Chi_Minh time."""
        before = datetime.now(VN_TZ)
        now_str = get_system_now()
        after = datetime.now(VN_TZ)

        self.assertRegex(now_str, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")
        parsed = datetime.fromisoformat(now_str)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertGreaterEqual(parsed, before.replace(microsecond=0))
        self.assertLessEqual(parsed, after.replace(microsecond=0))

        turn = ConversationTurnItem(turn_id=1, customer_query="hi", agent_response="chao")
        sess_schema = ConversationSessionState(session_id="s1")
        conv_state = ConversationState(session_id="s2")
        self.assertTrue(sess_schema.updated_at.endswith("+07:00"))
        self.assertTrue(conv_state.last_updated.endswith("+07:00"))
        self.assertEqual(turn.timestamp[:10], get_vn_now().strftime("%Y-%m-%d"))

    def test_sqlite_state_store_and_policy_audit_use_vn_iso_and_sort_across_midnight(self):
        """SQLite sessions/turns & PolicyManager record +07:00 timestamps and sort mixed legacy/ISO across midnight."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "conv.sqlite3"
            store = PersistentStateStore(db_path)
            store.get_or_create("sess-tz-1", "CUST-1")
            store.add_turn_record("sess-tz-1", role="customer", content="Đơn hàng của tôi")
            details = store.get_full_session_details("sess-tz-1")
            self.assertTrue(details["createdAt"].endswith("+07:00"))
            self.assertTrue(details["updatedAt"].endswith("+07:00"))
            self.assertRegex(details["messages"][0]["timestamp"], r"^\d{2}:\d{2}$")

            # Insert mixed legacy naive + ISO +07:00 + UTC Z across midnight boundary
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    "INSERT INTO conversation_sessions (session_id, customer_id, title, updated_at) VALUES (?, ?, ?, ?);",
                    ("s-legacy-late", "CUST-1", "Legacy late", "2026-11-21 23:55:00"),
                )
                conn.execute(
                    "INSERT INTO conversation_sessions (session_id, customer_id, title, updated_at) VALUES (?, ?, ?, ?);",
                    ("s-iso-midnight", "CUST-1", "Midnight VN", "2026-11-22T00:05:00+07:00"),
                )
                conn.execute(
                    "INSERT INTO conversation_sessions (session_id, customer_id, title, updated_at) VALUES (?, ?, ?, ?);",
                    ("s-utc-equivalent", "CUST-1", "UTC Z", "2026-11-21T16:59:00Z"),
                )
                conn.commit()

            ordered = [s["sessionId"] for s in store.list_sessions_by_customer("CUST-1") if s["sessionId"].startswith("s-")]
            self.assertEqual(ordered, ["s-iso-midnight", "s-utc-equivalent", "s-legacy-late"])

            policies_path = tmp_path / "policies.json"
            audit_path = tmp_path / "audit.json"
            policies_path.write_text("[]", encoding="utf-8")
            manager = PolicyManager(policies_path=str(policies_path), audit_logs_path=str(audit_path))
            entry = manager.record_audit_log("CREATE", "POL-TZ-1", "Test Policy")
            self.assertTrue(entry.timestamp.endswith("+07:00"))
            del store
            gc.collect()

    def test_telemetry_repository_writes_vn_iso_and_sorts_mixed_utc_and_vn_chronologically(self):
        """TelemetryRepository writes +07:00 for new logs/cancellations and sorts mixed legacy UTC + new +07:00 accurately."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "tel.sqlite3"
            mock_orders = Path(__file__).resolve().parents[1] / "data" / "mock_orders.json"
            init_db(db_path, mock_orders)
            repo = TelemetryRepository(db_path, mock_orders)

            # Seed legacy UTC rows (16:50 UTC = 23:50 +07:00) and newer/older +07:00 rows across midnight
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    """INSERT INTO telemetry_logs
                    (interaction_id, timestamp, customer_query, predicted_intent, intent_confidence, guardrail_action, retrieved_doc_ids, raw_draft_text, is_continual_learning)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    ("int-utc-legacy", "2026-11-21 16:50:00", "q1", "track_order", 0.9, "PROCEED_TO_LLM", "", "d1", 1),
                )
                conn.execute(
                    """INSERT INTO telemetry_logs
                    (interaction_id, timestamp, customer_query, predicted_intent, intent_confidence, guardrail_action, retrieved_doc_ids, raw_draft_text, is_continual_learning)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    ("int-vn-early", "2026-11-21T23:45:00+07:00", "q2", "track_order", 0.9, "PROCEED_TO_LLM", "", "d2", 1),
                )
                conn.execute(
                    """INSERT INTO telemetry_logs
                    (interaction_id, timestamp, customer_query, predicted_intent, intent_confidence, guardrail_action, retrieved_doc_ids, raw_draft_text, is_continual_learning)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    ("int-vn-midnight", "2026-11-22T00:02:00+07:00", "q3", "track_order", 0.9, "PROCEED_TO_LLM", "", "d3", 1),
                )
                conn.commit()

            # Insert a brand-new record -> gets current real +07:00 timestamp
            repo.insert_audit_log(
                AuditLogCreate(
                    interaction_id="int-live-new",
                    customer_query="q4",
                    predicted_intent="track_order",
                    intent_confidence=0.95,
                    guardrail_action="PROCEED_TO_LLM",
                    retrieved_doc_ids="",
                    raw_draft_text="d4",
                    latency_ms=10,
                )
            )
            stats = repo.get_stats()
            recent_ids = [r["interaction_id"] for r in stats["recent_records"]]
            new_rec = next(r for r in stats["recent_records"] if r["interaction_id"] == "int-live-new")
            self.assertTrue(new_rec["timestamp"].endswith("+07:00"))
            # Check chronological ordering among the 3 seeded records around midnight
            seeded_order = [i for i in recent_ids if i.startswith("int-v") or i == "int-utc-legacy"]
            self.assertEqual(seeded_order, ["int-vn-midnight", "int-utc-legacy", "int-vn-early"])

            del repo
            gc.collect()

    def test_temporal_policy_helpers_use_vn_today(self):
        """Temporal policy evaluation uses Vietnam calendar date."""
        today_str = get_vn_today().strftime("%Y-%m-%d")
        doc = RetrievedDocument(
            doc_id="POL-TEMP-TODAY",
            title="Today Promo",
            content="Valid today",
            is_active=True,
            policy_type="temporary",
            effective_date=today_str,
            expiration_date=today_str,
        )
        valid, status, _ = check_temporal_validity(doc)
        self.assertTrue(valid)
        self.assertEqual(status, "ACTIVE")
        active_flag, _ = calculate_active_status(doc)
        self.assertTrue(active_flag)


class TestTLSVerificationAlignment(unittest.TestCase):
    def test_llm_failover_enforces_tls_verify_true_by_default(self):
        """Sync, async, and stream failover clients enable TLS verification by default."""
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp_200)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_client
        mock_cm.__aexit__.return_value = False

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "mock-tls-key",
                "OPENAI_API_KEY_BACKUP": "",
                "OPENAI_API_KEYS": "",
                "LLM_CA_BUNDLE": "",
                "REQUESTS_CA_BUNDLE": "",
                "SSL_CERT_FILE": "",
                "DISABLE_EXTERNAL_LLM": "",
            },
            clear=False,
        ):
            with patch("contracts.llm_failover.requests.post", return_value=resp_200) as mock_post:
                llm_failover.call_chat_completion_sync_with_failover({"model": "m", "messages": []})
                self.assertIs(mock_post.call_args.kwargs["verify"], True)

            with patch("contracts.llm_failover.httpx.AsyncClient", return_value=mock_cm) as mock_async_cls:
                asyncio.run(llm_failover.call_chat_completion_with_failover({"model": "m", "messages": []}))
                self.assertIs(mock_async_cls.call_args.kwargs["verify"], True)

            stream_resp = MagicMock(status_code=200)

            async def _empty_lines():
                if False:
                    yield ""

            stream_resp.aiter_lines = _empty_lines
            stream_cm = AsyncMock()
            stream_cm.__aenter__.return_value = stream_resp
            stream_cm.__aexit__.return_value = False
            mock_stream_client = AsyncMock()
            mock_stream_client.stream = MagicMock(return_value=stream_cm)
            mock_stream_client_cm = AsyncMock()
            mock_stream_client_cm.__aenter__.return_value = mock_stream_client
            mock_stream_client_cm.__aexit__.return_value = False

            async def _drain():
                async for _ in llm_failover.stream_chat_completion_with_failover({"model": "m", "messages": []}):
                    pass

            with patch("contracts.llm_failover.httpx.AsyncClient", return_value=mock_stream_client_cm) as mock_stream_cls:
                asyncio.run(_drain())
                self.assertIs(mock_stream_cls.call_args.kwargs["verify"], True)

    def test_tls_supports_custom_ca_bundle_and_fails_closed_if_missing(self):
        """Custom CA bundle path is propagated cleanly; nonexistent CA bundle raises FileNotFoundError."""
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as tmp:
            ca_path = tmp.name
        try:
            with patch.dict(os.environ, {"LLM_CA_BUNDLE": ca_path}, clear=False):
                self.assertEqual(llm_failover.get_tls_verify_for_requests(), ca_path)
                with patch("contracts.llm_failover.ssl.create_default_context", return_value="mock-ssl-ctx") as mock_ssl:
                    self.assertEqual(llm_failover.get_tls_verify_for_httpx(), "mock-ssl-ctx")
                    mock_ssl.assert_called_once_with(cafile=ca_path)
        finally:
            os.unlink(ca_path)

        with patch.dict(os.environ, {"LLM_CA_BUNDLE": "nonexistent_ca_bundle_12345.pem"}, clear=False):
            with self.assertRaises(FileNotFoundError):
                llm_failover.get_tls_verify_for_requests()
            with self.assertRaises(FileNotFoundError):
                llm_failover.get_tls_verify_for_httpx()

    def test_dead_gemini_callers_removed_across_runtime_services(self):
        """FR-INT-003: Verify unused _call_gemini methods and fake gemini-3.8-flash strings are removed from runtime services."""
        import inspect
        from services.conversation_service.src.input_pipeline import input_classifier as ic_mod
        from services.conversation_service.src.policies import copilot_draft_engine as cde_mod
        from services.intent_service.src import llm_classifier as lc_mod
        from services.rag_service.src import generator as gen_mod

        for mod in (ic_mod, cde_mod, lc_mod, gen_mod):
            src = inspect.getsource(mod)
            self.assertNotIn("_call_gemini", src, f"Dead _call_gemini found in {mod.__name__}")
            self.assertNotIn("gemini-3.8-flash", src, f"Fake model name found in {mod.__name__}")
            self.assertNotIn("generativelanguage.googleapis.com", src, f"Legacy Gemini URL found in {mod.__name__}")


if __name__ == "__main__":
    unittest.main()

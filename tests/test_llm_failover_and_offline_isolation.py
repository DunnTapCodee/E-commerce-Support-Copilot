"""Regression tests for credential isolation, LLM failover, and offline ML fallback control."""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import contracts.llm_failover as llm_failover
from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.llm_classifier import LLMIntentClassifier
from services.intent_service.src.predictor import IntentPredictor


class TestCredentialAndOfflineIsolation(unittest.TestCase):
    def test_no_hardcoded_default_keys_in_failover_module(self):
        """Ensure DEFAULT_KEYS was removed and empty env yields no API keys."""
        self.assertFalse(hasattr(llm_failover, "DEFAULT_KEYS"))
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "",
                "OPENAI_API_KEY_BACKUP": "",
                "OPENAI_API_KEYS": "",
                "DISABLE_EXTERNAL_LLM": "",
            },
            clear=False,
        ):
            self.assertEqual(llm_failover.get_available_api_keys(), [])

    def test_disable_external_llm_overrides_configured_keys(self):
        """DISABLE_EXTERNAL_LLM=true blocks key retrieval even if keys exist in env."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "mock-key-primary",
                "OPENAI_API_KEYS": "mock-key-1,mock-key-2",
                "DISABLE_EXTERNAL_LLM": "true",
            },
            clear=False,
        ):
            self.assertTrue(llm_failover.is_external_llm_disabled())
            self.assertEqual(llm_failover.get_available_api_keys(), [])

    def test_missing_credentials_make_zero_network_calls(self):
        """Async, sync, and stream failover skip HTTP calls when no keys are configured."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "",
                "OPENAI_API_KEY_BACKUP": "",
                "OPENAI_API_KEYS": "",
                "DISABLE_EXTERNAL_LLM": "",
            },
            clear=False,
        ):
            with patch("contracts.llm_failover.httpx.AsyncClient") as mock_async_client, patch(
                "contracts.llm_failover.requests.post"
            ) as mock_post:
                sync_res = llm_failover.call_chat_completion_sync_with_failover({"messages": []})
                async_res = asyncio.run(llm_failover.call_chat_completion_with_failover({"messages": []}))

                async def _collect_stream():
                    tokens = []
                    async for tok in llm_failover.stream_chat_completion_with_failover({"messages": []}):
                        tokens.append(tok)
                    return tokens

                stream_res = asyncio.run(_collect_stream())

                self.assertIsNone(sync_res)
                self.assertIsNone(async_res)
                self.assertEqual(stream_res, [])
                mock_async_client.assert_not_called()
                mock_post.assert_not_called()

    def test_valid_mock_credentials_preserve_online_failover_sync(self):
        """Online sync failover still uses primary then backup key from env when mocked."""
        resp_429 = MagicMock(status_code=429, text="rate limit")
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": '{"intent": "track_order"}'}}]}

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "mock-primary",
                "OPENAI_API_KEY_BACKUP": "mock-backup",
                "OPENAI_API_KEYS": "",
                "DISABLE_EXTERNAL_LLM": "",
            },
            clear=False,
        ):
            with patch("contracts.llm_failover.requests.post", side_effect=[resp_429, resp_200]) as mock_post:
                res = llm_failover.call_chat_completion_sync_with_failover({"model": "m", "messages": []})
                self.assertIsNotNone(res)
                self.assertEqual(mock_post.call_count, 2)
                first_auth = mock_post.call_args_list[0].kwargs["headers"]["Authorization"]
                second_auth = mock_post.call_args_list[1].kwargs["headers"]["Authorization"]
                self.assertEqual(first_auth, "Bearer mock-primary")
                self.assertEqual(second_auth, "Bearer mock-backup")

    def test_valid_mock_credentials_preserve_online_failover_async(self):
        """Online async failover works with mocked httpx.AsyncClient."""
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp_200)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_client
        mock_cm.__aexit__.return_value = False

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "mock-async-key", "OPENAI_API_KEY_BACKUP": "", "OPENAI_API_KEYS": "", "DISABLE_EXTERNAL_LLM": ""},
            clear=False,
        ):
            with patch("contracts.llm_failover.httpx.AsyncClient", return_value=mock_cm):
                res = asyncio.run(llm_failover.call_chat_completion_with_failover({"model": "m", "messages": []}))
                self.assertEqual(res["choices"][0]["message"]["content"], "ok")
                mock_client.post.assert_awaited_once()

    def test_ml_mode_missing_artifacts_never_calls_external_llm(self):
        """Pure ML mode must fail loudly rather than calling external LLM when ML models are missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"INTENT_BACKEND": "ml", "OPENAI_API_KEY": "mock-key", "DISABLE_EXTERNAL_LLM": ""}, clear=False):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="ml")
                    self.assertFalse(predictor.is_loaded)
                    with patch.object(predictor.llm_classifier, "predict") as mock_llm_predict:
                        with self.assertRaises(RuntimeError):
                            predictor.predict("Kiểm tra đơn ORD-1001")
                        mock_llm_predict.assert_not_called()

    def test_hybrid_mode_offline_isolation_uses_semantic_fallback_without_network(self):
        """When DISABLE_EXTERNAL_LLM=true and ML is absent, hybrid mode uses offline semantic fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"INTENT_BACKEND": "hybrid", "OPENAI_API_KEY": "mock-key", "DISABLE_EXTERNAL_LLM": "true"}, clear=False):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="hybrid")
                    with patch("contracts.llm_failover.requests.post") as mock_post:
                        resp = predictor.predict("Kiểm tra đơn hàng ORD-1001 giúp tôi")
                        self.assertEqual(resp.intent, "track_order")
                        mock_post.assert_not_called()

    def test_llm_classifier_offline_when_no_credentials(self):
        """LLMIntentClassifier uses _semantic_fallback without HTTP calls when credentials are absent."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "",
                "OPENAI_API_KEY_BACKUP": "",
                "OPENAI_API_KEYS": "",
                "GEMINI_API_KEY": "",
                "DISABLE_EXTERNAL_LLM": "",
            },
            clear=False,
        ):
            clf = LLMIntentClassifier(api_key="")
            with patch("contracts.llm_failover.requests.post") as mock_post, patch(
                "services.intent_service.src.llm_classifier.requests.post"
            ) as mock_gemini_post:
                resp = clf.predict("Thời tiết hôm nay ở Hà Nội thế nào?")
                self.assertEqual(resp.intent, "out_of_scope")
                self.assertFalse(resp.is_in_scope)
                mock_post.assert_not_called()
                mock_gemini_post.assert_not_called()

    def test_online_predictor_behavior_preserved_with_mock(self):
        """Online IntentPredictor still delegates to LLMIntentClassifier when enabled and configured."""
        mocked_resp = IntentPredictionResponse(
            intent="track_order",
            confidence=0.97,
            is_in_scope=True,
            model_name="mock-online-llm",
            all_probabilities={"track_order": 0.97},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"INTENT_BACKEND": "llm", "OPENAI_API_KEY": "mock-key", "DISABLE_EXTERNAL_LLM": ""}, clear=False):
                with patch.object(IntentPredictor, "_load_legacy_model", return_value=None):
                    predictor = IntentPredictor(model_source=tmpdir, intent_backend="llm")
                    with patch.object(predictor.llm_classifier, "predict", return_value=mocked_resp) as mock_predict:
                        resp = predictor.predict("Đơn ORD-1001 đang ở đâu")
                        self.assertEqual(resp.intent, "track_order")
                        self.assertEqual(resp.model_name, "mock-online-llm")
                        mock_predict.assert_called_once()


if __name__ == "__main__":
    unittest.main()

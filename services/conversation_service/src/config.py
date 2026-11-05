"""Configuration and endpoints for Conversation Service."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

PORT = int(os.getenv("PORT", "8001"))
INTENT_SERVICE_URL = os.getenv("INTENT_SERVICE_URL", "http://127.0.0.1:8005")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:8002")
TELEMETRY_SERVICE_URL = os.getenv("TELEMETRY_SERVICE_URL", "http://127.0.0.1:8003")

INTENT_CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.60"))
DISABLE_CONFIDENCE_GUARD = os.getenv("DISABLE_CONFIDENCE_GUARD", "false").lower() in ("true", "1", "yes")
FAITHFULNESS_THRESHOLD = float(os.getenv("FAITHFULNESS_THRESHOLD", "0.70"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai-gpt-oss-20b")

FINANCIAL_INTENTS = {"request_refund", "payment_issue"}


"""Configuration for Document Service on Port 8004."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

# File paths
POLICIES_PATH = Path(os.getenv("POLICIES_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policies.json")))
AUDIT_LOGS_PATH = Path(os.getenv("AUDIT_LOGS_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policy_audit_logs.json")))

# Downstream service
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:8002")

# LLM Providers
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "openai-gpt-oss-20b"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

PORT = int(os.getenv("DOCUMENT_SERVICE_PORT", "8004"))


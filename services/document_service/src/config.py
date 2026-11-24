"""Configuration for Document Service on Port 8004."""
import os
from pathlib import Path

# Load environment variables from .env at project root
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Keep original constant name for compatibility
ROOT_DIR = PROJECT_ROOT

# File paths
POLICIES_PATH = Path(os.getenv("POLICIES_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policies.json")))
AUDIT_LOGS_PATH = Path(os.getenv("AUDIT_LOGS_PATH", str(ROOT_DIR / "data" / "knowledge_base" / "policy_audit_logs.json")))

# Downstream service
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:8002")

from contracts.llm_failover import DEFAULT_OPENAI_BASE_URL, get_default_openai_model

# LLM Provider (OpenAI-compatible only, fixed keys from .env & contracts.llm_failover)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""
OPENAI_API_KEY_BACKUP = os.getenv("OPENAI_API_KEY_BACKUP") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
OPENAI_MODEL = get_default_openai_model()

PORT = int(os.getenv("DOCUMENT_SERVICE_PORT", "8004"))


"""Resilient OpenAI-compatible client with automatic multi-key failover and health tracking.
Supports primary and backup API keys to guarantee zero-downtime upon quota exhaustion (402)
or authentication error (401) or rate-limit (429).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import ssl
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
try:
    import httpx
except ImportError:  # Lightweight containers (e.g. telemetry_service) may omit httpx
    httpx = None  # type: ignore[assignment]

try:
    import requests
except ImportError:  # Lightweight containers (e.g. gateway) may omit requests
    requests = None  # type: ignore[assignment]

logger = logging.getLogger("contracts.llm_failover")

DEFAULT_OPENAI_BASE_URL = "https://api.xah.io/v1"
DEFAULT_OPENAI_MODEL = "vantoanbk57/deepseek-v4.1-flash"


def get_default_openai_model() -> str:
    """Single source of truth for configured OpenAI-compatible model ID."""
    return os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_OPENAI_MODEL


def _resolve_ca_bundle() -> Optional[str]:
    """Return optional CA bundle path from standard environment variables."""
    ca_bundle = (
        os.getenv("LLM_CA_BUNDLE")
        or os.getenv("REQUESTS_CA_BUNDLE")
        or os.getenv("SSL_CERT_FILE")
        or ""
    ).strip()
    if not ca_bundle:
        return None
    if not Path(ca_bundle).is_file():
        raise FileNotFoundError(f"Configured CA bundle file not found: {ca_bundle}")
    return ca_bundle


def get_tls_verify_for_requests() -> Union[bool, str]:
    """Return TLS verification option for requests (True by default, or CA bundle path)."""
    return _resolve_ca_bundle() or True


def get_tls_verify_for_httpx() -> Union[bool, ssl.SSLContext]:
    """Return TLS verification option for httpx (True by default, or SSLContext with CA bundle)."""
    ca_bundle = _resolve_ca_bundle()
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    return True


def is_external_llm_disabled() -> bool:
    """Return True when external LLM network calls are explicitly disabled."""
    return os.getenv("DISABLE_EXTERNAL_LLM", "").strip().lower() in ("1", "true", "yes")


def get_available_api_keys() -> List[str]:
    """Retrieve OpenAI-compatible API keys strictly from environment variables."""
    if is_external_llm_disabled():
        return []

    keys: List[str] = []
    # 1. Check comma-separated env var
    env_keys = os.getenv("OPENAI_API_KEYS", "")
    if env_keys:
        for k in env_keys.split(","):
            clean = k.strip()
            if clean and clean not in keys:
                keys.append(clean)

    # 2. Check primary and backup env vars
    primary = os.getenv("OPENAI_API_KEY", "").strip()
    if primary and primary not in keys:
        keys.append(primary)

    backup = os.getenv("OPENAI_API_KEY_BACKUP", "").strip()
    if backup and backup not in keys:
        keys.append(backup)

    return keys


async def call_chat_completion_with_failover(
    payload: Dict[str, Any],
    base_url: Optional[str] = None,
    timeout: float = 12.0,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Execute chat completion with automatic failover across multiple keys."""
    url = f"{(base_url or os.getenv('OPENAI_BASE_URL', 'https://api.xah.io/v1')).rstrip('/')}/chat/completions"
    keys = get_available_api_keys()
    if not keys:
        logger.debug("[LLMFailover] No OpenAI-compatible API keys available; skipping request.")
        return None

    base_headers = dict(headers or {})
    base_headers["Content-Type"] = "application/json"

    last_error: Optional[Exception] = None

    for idx, key in enumerate(keys):
        req_headers = dict(base_headers)
        req_headers["Authorization"] = f"Bearer {key}"
        masked_key = f"{key[:8]}...{key[-4:]}"

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=get_tls_verify_for_httpx()) as client:
                resp = await client.post(url, json=payload, headers=req_headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return data
                elif resp.status_code in (401, 402, 429, 500, 502, 503):
                    logger.warning(
                        "[LLMFailover] Key %s failed with HTTP %s: %s. Failing over to next key.",
                        masked_key,
                        resp.status_code,
                        resp.text[:150],
                    )
                    continue
                else:
                    logger.error(
                        "[LLMFailover] Key %s returned unexpected HTTP %s: %s",
                        masked_key,
                        resp.status_code,
                        resp.text[:150],
                    )
        except Exception as exc:
            logger.warning("[LLMFailover] Key %s encounter error: %s. Failing over.", masked_key, exc)
            last_error = exc
            continue

    if last_error:
        logger.error("[LLMFailover] All %d API keys exhausted without success. Last error: %s", len(keys), last_error)
    return None


def call_chat_completion_sync_with_failover(
    payload: Dict[str, Any],
    base_url: Optional[str] = None,
    timeout: float = 15.0,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Synchronous chat completion with automatic failover (for sync classifiers)."""
    url = f"{(base_url or os.getenv('OPENAI_BASE_URL', 'https://api.xah.io/v1')).rstrip('/')}/chat/completions"
    keys = get_available_api_keys()
    if not keys:
        logger.debug("[LLMFailover Sync] No OpenAI-compatible API keys available; skipping request.")
        return None

    base_headers = dict(headers or {})
    base_headers["Content-Type"] = "application/json"

    for idx, key in enumerate(keys):
        req_headers = dict(base_headers)
        req_headers["Authorization"] = f"Bearer {key}"
        masked_key = f"{key[:8]}...{key[-4:]}"

        try:
            if requests is not None:
                resp = requests.post(
                    url,
                    json=payload,
                    headers=req_headers,
                    timeout=timeout,
                    verify=get_tls_verify_for_requests(),
                )
            else:
                resp = httpx.post(
                    url,
                    json=payload,
                    headers=req_headers,
                    timeout=timeout,
                    verify=get_tls_verify_for_httpx(),
                )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return data
            elif resp.status_code in (401, 402, 429, 500, 502, 503):
                logger.warning(
                    "[LLMFailover Sync] Key %s failed with HTTP %s: %s. Failing over.",
                    masked_key,
                    resp.status_code,
                    resp.text[:150],
                )
                continue
        except Exception as exc:
            logger.warning("[LLMFailover Sync] Key %s error: %s. Failing over.", masked_key, exc)
            continue

    return None


async def stream_chat_completion_with_failover(
    payload: Dict[str, Any],
    base_url: Optional[str] = None,
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens (Server-Sent Events) with initial connection failover."""
    url = f"{(base_url or os.getenv('OPENAI_BASE_URL', 'https://api.xah.io/v1')).rstrip('/')}/chat/completions"
    keys = get_available_api_keys()
    if not keys:
        logger.debug("[LLMFailover Stream] No OpenAI-compatible API keys available; skipping stream.")
        return

    base_headers = dict(headers or {})
    base_headers["Content-Type"] = "application/json"

    req_payload = dict(payload)
    req_payload["stream"] = True

    for idx, key in enumerate(keys):
        req_headers = dict(base_headers)
        req_headers["Authorization"] = f"Bearer {key}"
        masked_key = f"{key[:8]}...{key[-4:]}"

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=get_tls_verify_for_httpx()) as client:
                async with client.stream("POST", url, json=req_payload, headers=req_headers) as resp:
                    if resp.status_code != 200:
                        err_bytes = await resp.aread()
                        logger.warning(
                            "[LLMFailover Stream] Key %s HTTP %s: %s. Failing over.",
                            masked_key,
                            resp.status_code,
                            err_bytes.decode("utf-8", errors="ignore")[:150],
                        )
                        continue

                    # Stream succeeded, yield tokens
                    import json
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[len("data: "):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content") or ""
                            if token:
                                yield token
                        except Exception:
                            continue
                    return  # Streaming finished successfully
        except Exception as exc:
            logger.warning("[LLMFailover Stream] Key %s failed: %s. Failing over.", masked_key, exc)
            continue


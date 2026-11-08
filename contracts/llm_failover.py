"""Resilient OpenAI-compatible client with automatic multi-key failover and health tracking.
Supports primary and backup API keys to guarantee zero-downtime upon quota exhaustion (402)
or authentication error (401) or rate-limit (429).
"""
from __future__ import annotations

import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
import requests

logger = logging.getLogger("contracts.llm_failover")

# Default API Keys provided for gpt-oss-20b
DEFAULT_KEYS = [
    "sk-6b62dfadc0fa9e74980de017ec926c48817aaeb0e3442449e95d2d52439d127e",
    "sk-9ab538e009ab78639e177b0703b78476c74511874de5c39d5fc6a7a1d786977a",
]


def get_available_api_keys() -> List[str]:
    """Retrieve list of active and backup OpenAI-compatible API keys."""
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

    # 3. Add default production keys if not already present
    for dk in DEFAULT_KEYS:
        if dk not in keys:
            keys.append(dk)

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

    base_headers = dict(headers or {})
    base_headers["Content-Type"] = "application/json"

    last_error: Optional[Exception] = None

    for idx, key in enumerate(keys):
        req_headers = dict(base_headers)
        req_headers["Authorization"] = f"Bearer {key}"
        masked_key = f"{key[:8]}...{key[-4:]}"

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
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

    base_headers = dict(headers or {})
    base_headers["Content-Type"] = "application/json"

    for idx, key in enumerate(keys):
        req_headers = dict(base_headers)
        req_headers["Authorization"] = f"Bearer {key}"
        masked_key = f"{key[:8]}...{key[-4:]}"

        try:
            resp = requests.post(url, json=payload, headers=req_headers, timeout=timeout, verify=False)
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

    base_headers = dict(headers or {})
    base_headers["Content-Type"] = "application/json"

    req_payload = dict(payload)
    req_payload["stream"] = True

    for idx, key in enumerate(keys):
        req_headers = dict(base_headers)
        req_headers["Authorization"] = f"Bearer {key}"
        masked_key = f"{key[:8]}...{key[-4:]}"

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
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
                            token = delta.get("content") or delta.get("reasoning_content") or ""
                            if token:
                                yield token
                        except Exception:
                            continue
                    return  # Streaming finished successfully
        except Exception as exc:
            logger.warning("[LLMFailover Stream] Key %s failed: %s. Failing over.", masked_key, exc)
            continue


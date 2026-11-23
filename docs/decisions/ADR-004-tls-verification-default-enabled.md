# ADR-004: Enable TLS Certificate Verification by Default for All LLM HTTP Clients

- **Status:** `Accepted` (`Confirmed` by owner; implemented & locally verified with mocks; live handshake against `https://api.xah.io/v1` pending online verification)
- **Linked Requirements:** `NFR-SEC-001`, `NFR-SEC-002`, `OD-003`
- **Linked Assumptions:** [ASM-001](../assumptions.md)

## Context
Outbound LLM HTTP clients in `contracts/llm_failover.py` (sync, async, and streaming), `services/intent_service/src/llm_classifier.py`, and `services/rag_service/src/generator.py` previously passed `verify=False` (`Observed`), disabling TLS certificate validation and exposing API keys and customer queries to MITM risks. The original reason `verify=False` was introduced is **unverified** in repository records.

## Decision
1. Enable TLS certificate verification (`verify=True`) by default across all `requests` and `httpx` LLM clients (`contracts/llm_failover.py`, `llm_classifier.py`, `generator.py`, `copilot_draft_engine.py`).
2. Provide shared helpers `get_tls_verify_for_requests()` and `get_tls_verify_for_httpx()` in `contracts/llm_failover.py` that support an optional custom CA bundle via `LLM_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, or `SSL_CERT_FILE`.
3. Fail closed (`FileNotFoundError`) if a configured CA bundle path does not exist. Never use `verify=False` as a workaround.

## Alternatives Considered
- **Keep `verify=False` behind an env flag:** Rejected because disabling TLS verification conflicts with security baseline requirements.
- **Rely exclusively on implicit library defaults without CA bundle helpers:** Rejected because `httpx` prefers an explicit `ssl.SSLContext(cafile=...)` while `requests` accepts a string path; centralizing helpers ensures consistent fail-closed behavior.

## Consequences
- **Positive:** Eliminates TLS bypass vulnerabilities across all LLM call paths (`zero verify=False` verified statically).
- **Negative / Risk:** Live TLS connectivity to `https://api.xah.io/v1` has **not** yet been tested online (`ASM-001`, `OD-003`). If the endpoint uses a non-standard CA chain, operators must configure `LLM_CA_BUNDLE` in `.env` rather than disabling verification.

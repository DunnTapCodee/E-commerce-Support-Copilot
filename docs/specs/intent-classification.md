# Specification: Intent Classification (`SPEC-INT-001`)

> **Linked Requirements:** `FR-INT-001`, `FR-INT-002`, `FR-INT-003`, `FR-INT-004`, `FR-INT-005`, `BR-002`, `SC-003`, `NFR-SEC-001`, `NFR-SEC-002`, `NFR-OBS-001`
> **Linked ADRs:** [ADR-002](../decisions/ADR-002-intent-llm-primary-ml-fallback.md), [ADR-004](../decisions/ADR-004-tls-verification-default-enabled.md)
> **Primary Modules (`Observed`):** `services/intent_service/src/main.py`, `predictor.py`, `llm_classifier.py`, `normalizer.py`, `router.py`, `pipeline/dataset.py`, `contracts/llm_failover.py`

---

## 1. Purpose & Decision Strategy

- **`Confirmed Requirement` (`FR-INT-001`, `FR-INT-002`):** Classify customer queries using **`LLM primary -> ML fallback when LLM is unavailable -> safe human escalation`**.
- **`Confirmed Requirement` (`FR-INT-001`, `FR-INT-003`):** Primary LLM uses CKEY.VN (`LLM_PROVIDER=openai_compatible`, `OPENAI_BASE_URL=https://api.xah.io/v1`, `OPENAI_MODEL=vantoanbk57/deepseek-v4.1-flash`, `INTENT_BACKEND=llm`). Do not silently fall back to Gemini or another external provider when CKEY.VN fails.
- **`Observed Implementation` Gap:** `artifacts/models/intent/` currently contains only `.gitkeep` (no deployed Module 1 router). Local ML fallback currently relies on legacy sklearn `1.6.1` artifacts (`ML-model/` or `artifacts/models/intent_model.pkl`) when present.

---

## 2. Inputs & Outputs (`Observed Implementation`)

### HTTP Endpoints (`services/intent_service/src/main.py`)
- **`POST /predict`**
  - **Input (`IntentPredictionRequest`):** `{"query": "<non-empty string>"}` (may include context tags from `conversation_service`, e.g., `[PREV_INTENT:track_order] [ORDER:ORD-1003] ...`). Empty/whitespace-only query returns `HTTP 400`.
  - **Output (`IntentPredictionResponse`):**
    ```json
    {
      "intent": "track_order",
      "confidence": 0.93,
      "is_in_scope": true,
      "language": "vi",
      "model_name": "vantoanbk57/deepseek-v4.1-flash",
      "latency_ms": 120.5,
      "all_probabilities": {"track_order": 0.93}
    }
    ```
  - **Error:** `HTTP 503` if `predictor_instance is None`.
- **`GET /health`**
  - **Output:** `status` (`healthy` | `degraded`), `service`, `model_loaded`, `ml_artifacts_loaded` (`bool`), `intent_backend` (`llm` | `hybrid` | `ml`), `routing_mode` (`router` | `multilingual`), `models`, `error`.

### Taxonomy (`Confirmed Requirement` — `OD-004` Resolved)
- `pipeline/dataset.py` defines **16** canonical `TARGET_INTENTS` (`track_order`, `cancel_order`, `delivery_time`, `delivery_issue`, `shipping_costs`, `return_policy`, `return_product`, `refund_policy`, `request_refund`, `refund_status`, `payment_issue`, `human_agent`, `warranty`, `get_discounts`, `create_account`, `recover_password`) + `out_of_scope` (12 core operational intents + 4 practical additions confirmed by project owner).
- `services/intent_service/src/llm_classifier.py` (`INTENT_DESCRIPTIONS`, `INTENT_SYSTEM_PROMPT`, `_semantic_fallback`) and `services/conversation_service/src/dialogue_state/tracker.py` are aligned to all **16** canonical intents + `out_of_scope` (`tests/test_intent_llm.py::test_canonical_16_intents_taxonomy_and_extended_fallbacks`).
- *Training pipeline note (`Observed`):* `services/intent_service/README_MODULE1.md` and `build_datasets.py` still note that Kaggle Bitext translation splits map `warranty` -> `out_of_scope` until Module 1 ML training data (`OD-002`) is expanded for all 16 intents.

---

## 3. Runtime States & Processing Rules

### Backend Modes (`INTENT_BACKEND` in `IntentPredictor`)

| Mode | Normal Online Path (`DISABLE_EXTERNAL_LLM` unset/false) | Offline Isolation Path (`DISABLE_EXTERNAL_LLM=true`) | Status |
| --- | --- | --- | --- |
| `llm` (default) | 1) CKEY.VN LLM primary -> 2) If LLM unavailable and `has_ml_artifacts=True`: `_predict_ml()` -> 3) Else: `unavailable_fallback` | `LLMIntentClassifier._semantic_fallback()` (`model_name="semantic_rule_fallback"`) — zero outbound HTTP | `Confirmed Requirement` (online); `Observed Implementation` (offline test isolation) |
| `hybrid` | Same as `llm` online (`LLM primary -> ML fallback -> unavailable_fallback`) | If `has_ml_artifacts=True`: `_predict_ml()`; else `semantic_rule_fallback` | `Observed Implementation` |
| `ml` | Pure local ML (`_predict_ml()`). Raises `RuntimeError` if `not has_ml_artifacts`. Never calls LLM. | Same as online (`_predict_ml()`, fails loudly if missing) | `Observed Implementation` |
| Other values | Rejected at init with `ValueError` | Rejected at init with `ValueError` | `Observed Implementation` |

### Decision Flow (`llm` / `hybrid` online)
1. **Invoke Primary LLM (`LLMIntentClassifier.predict`)**:
   - Uses `call_chat_completion_sync_with_failover()` with `verify=get_tls_verify_for_requests()` (`verify=True` default, optional CA bundle) and multi-key failover (`OPENAI_API_KEYS`, `OPENAI_API_KEY`, `OPENAI_API_KEY_BACKUP`) across HTTP `401/402/429/500/502/503` or transport errors.
   - If LLM returns valid JSON with a recognized intent, return `IntentPredictionResponse` with `model_name=<configured OPENAI_MODEL>`.
   - **Invariant (`Confirmed Requirement`):** Valid LLM `out_of_scope` predictions MUST be returned directly; ML MUST NOT override a valid LLM result.
2. **Detect LLM Unavailability**:
   - LLM is considered unavailable if `LLMIntentClassifier.predict()` raises an exception, returns `None`, or degrades internally to `model_name == "semantic_rule_fallback"` (caused by missing keys, exhausted keys, HTTP failure, timeout, or unparseable JSON).
3. **Conditional ML Fallback**:
   - Only if `has_ml_artifacts` (`bool(self.backends) or self.legacy_model is not None`): run `_predict_ml(query)` (applying `normalize_vietnamese_query` + `LanguageRouter` + Module 1 backend or legacy sklearn pipeline).
   - `model_name` records the actual ML backend (`meta["method"]` or `"legacy_baseline"`).
4. **Fail-Closed Abstention (Both Unavailable)**:
   - If `not has_ml_artifacts`, log error and return:
     `IntentPredictionResponse(intent="unknown_query", confidence=0.0, is_in_scope=False, language="vi", model_name="unavailable_fallback", all_probabilities={})`.

---

## 4. Failure Scenarios & Edge Cases

| Scenario | Expected Behavior | Status |
| --- | --- | --- |
| Primary LLM returns `out_of_scope` (`conf=0.95`, `is_in_scope=False`) | Return LLM result as-is; downstream guardrails escalate (`ESCALATE_HUMAN`). Do not call `_predict_ml()`. | `Confirmed Requirement` / `Observed Implementation` |
| Primary key returns HTTP `429`/`402`/`401` | Fail over to next key in `get_available_api_keys()`; never fall back to Gemini when `LLM_PROVIDER=openai_compatible`. | `Confirmed Requirement` / `Observed Implementation` |
| All LLM keys exhausted / timeout / network error + ML loaded | Fall back to `_predict_ml()`, return ML prediction with ML `model_name`. | `Confirmed Requirement` / `Observed Implementation` |
| All LLM keys exhausted + no ML artifacts loaded | Return `unavailable_fallback` (`unknown_query`, `0.0`, `is_in_scope=False`). Both `conversation_service` and `gateway` escalate to human (`ESCALATE_HUMAN`). | `Confirmed Requirement` / `Observed Implementation` |
| `intent_service` process unreachable (`ConnectError` / `HTTP 503`) | Both `conversation_service` and `gateway` create `unavailable_fallback` (`unknown_query`, `0.0`, `is_in_scope=False`) and escalate (`ESCALATE_HUMAN`), even on turn 2 with prior `active_intent`. | `Confirmed Requirement` / `Observed Implementation` |
| `DISABLE_EXTERNAL_LLM=true` in CI / offline tests | Zero outbound HTTP calls (`get_available_api_keys() == []`); uses ML (in `hybrid`/`ml`) or `semantic_rule_fallback` (in `llm` or `hybrid` without ML) with honest `model_name`. | `Observed Implementation` |
| Unaccented Vietnamese query (e.g., `"kiem tra don ord-1001"`) | `normalize_vietnamese_query()` normalizes before ML/heuristic scoring. | `Observed Implementation` |
| Empty or whitespace-only query | `POST /predict` returns `HTTP 400`. | `Observed Implementation` |

---

## 5. Invariants

1. **No Silent Provider Switch (`Confirmed Requirement`):** `LLM_PROVIDER=openai_compatible` must never invoke Gemini on CKEY.VN failure.
2. **Honest Backend Attribution (`Confirmed Requirement`):** `_semantic_fallback` must never report `model_name="llm_intent_classifier"`; every response records its true origin (`<OPENAI_MODEL>`, `<ml_backend>`, `semantic_rule_fallback`, or `unavailable_fallback`).
3. **No Guardrail Bypass (`Confirmed Requirement`):** `unavailable_fallback` and `out_of_scope` must never be upgraded to an in-scope intent by `IntentTracker` or bypassed by `DISABLE_CONFIDENCE_GUARD=true`.
4. **TLS Verified by Default (`Confirmed Requirement`):** Outbound LLM requests always use `verify=True` (or validated CA bundle path), never `verify=False`.

---

## 6. Acceptance Criteria & Verification Mapping

| ID | Verifiable Condition | Current Automated Evidence (`Observed`) |
| --- | --- | --- |
| `AC-INT-001` | Mocked LLM `out_of_scope` returns LLM response with `vantoanbk57/deepseek-v4.1-flash` and 0 ML calls. | `tests/test_architecture_decisions_alignment.py::test_llm_primary_prioritized_even_when_out_of_scope` |
| `AC-INT-002` | Unavailable LLM + loaded ML invokes `_predict_ml()` with ML `model_name` and 0 Gemini calls. | `tests/test_architecture_decisions_alignment.py::test_llm_unavailable_falls_back_to_loaded_ml_artifact` |
| `AC-INT-003` | Unavailable LLM + no ML returns `unavailable_fallback` (`0.0`, `is_in_scope=False`), triggering `ESCALATE_HUMAN` in Gateway and Conversation Service (even with active session intent). | `tests/test_architecture_decisions_alignment.py` (`test_both_llm_and_ml_unavailable_*`, `test_conversation_service_fails_closed_*`, `test_gateway_fallback_escalates_*`) |
| `AC-INT-004` | `ml` mode with missing artifacts raises `RuntimeError` without calling LLM. | `tests/test_llm_failover_and_offline_isolation.py::test_ml_mode_missing_artifacts_never_calls_external_llm` |
| `AC-INT-005` | Real Module 1 ML artifacts deployed and benchmarked in `artifacts/models/intent/`. | **Not yet verified** (`Open Decision` `OD-002`; mock tests verify routing logic only). |

# ADR-002: Intent Classification Strategy — LLM Primary, ML Fallback, Fail-Closed Escalation

- **Status:** `Accepted` (`Confirmed` by owner; logic implemented & locally verified with mocks; Module 1 ML artifacts deployment pending)
- **Linked Requirements:** `BR-002`, `FR-INT-001`, `FR-INT-002`, `FR-INT-003`, `FR-INT-004`, `SC-003`, `OD-002`, `OD-004`
- **Linked Specs:** [Intent Classification Spec](../specs/intent-classification.md)

## Context
Previously (`Observed` prior to alignment):
- `IntentPredictor` and `LLMIntentClassifier` diverged across `.env` (`INTENT_BACKEND=llm`), `docker-compose.yml` (`hybrid`), and hardcoded defaults (`openai-gpt-oss-20b`, `gemini-2.5-flash` in `models` property).
- `LLMIntentClassifier.predict()` caught errors and silently returned `_semantic_fallback()` labeled as `"llm_intent_classifier"`, preventing `IntentPredictor` from reaching ML fallback or failing closed.
- When `intent_service` failed or returned `unknown_query`, `conversation_service` could carry over prior `active_intent`, bypassing human escalation.

## Decision
1. Adopt **`LLM primary -> ML fallback when LLM is unavailable -> safe human escalation`**.
2. Standardize primary LLM configuration on CKEY.VN: `LLM_PROVIDER=openai_compatible`, `OPENAI_BASE_URL=https://api.xah.io/v1`, `OPENAI_MODEL=vantoanbk57/deepseek-v4.1-flash`, `INTENT_BACKEND=llm`.
3. Invoke local ML fallback (`_predict_ml`) **only** when the primary LLM is unavailable **and** valid ML artifacts are loaded (`has_ml_artifacts=True`). Do not allow ML to override valid LLM outputs (including `out_of_scope`).
4. When both LLM and ML are unavailable (online runtime), return fail-closed `unknown_query` (`confidence=0.0`, `is_in_scope=False`, `model_name="unavailable_fallback"`) and escalate to human (`ESCALATE_HUMAN`) in both `gateway` and `conversation_service`.
5. Do **not** silently fall back to Gemini or another external provider when `LLM_PROVIDER=openai_compatible`.
6. Record the actual backend in `model_name` and expose `ml_artifacts_loaded` and `intent_backend` in `GET /health`.

## Alternatives Considered
- **ML-first with LLM fallback:** Not selected by owner; Module 1 bilingual ML artifacts are not yet trained/deployed in `artifacts/models/intent/`.
- **Silent fallback to Gemini or regex heuristics (`_semantic_fallback`) in production:** Rejected because it violates provider policy and risks bypassing guardrails with high-confidence heuristic guesses.

## Consequences
- **Positive:** Predictable provider usage, honest observability, and fail-closed safety across `intent_service`, `conversation_service`, and `gateway`.
- **Negative / Risk:** Until real Module 1 artifacts are deployed in `artifacts/models/intent/` (`OD-002`, `ASM-002`), an extended CKEY.VN outage falls back either to legacy sklearn `1.6.1` pickle (`ML-model/`) or directly to human escalation.

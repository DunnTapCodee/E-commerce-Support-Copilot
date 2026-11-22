# ADR-003: Real Vietnam Timezone (`Asia/Ho_Chi_Minh`) Without Artificial `+12 Hours` Offset

- **Status:** `Accepted` (`Confirmed` by owner; implemented for new writes & read/sort/display; historical records intentionally unmigrated)
- **Linked Requirements:** `BR-005`, `NFR-TIME-001`, `SC-004`, `OD-008`
- **Linked Architecture / Specs:** [Architecture Overview](../architecture/overview.md) §5.2, [Copilot Workflow Spec](../specs/copilot-workflow.md)

## Context
Multiple backend modules (`contracts/schemas.py`, `sqlite_state_store.py`, `state.py`, `policy_manager.py`) previously computed timestamps using `datetime.now() + timedelta(hours=12)` (`Observed`). The original reason why `+12 hours` was introduced is **unverified** in repository records. Meanwhile, SQLite `DEFAULT CURRENT_TIMESTAMP` in `telemetry_service` wrote naive UTC strings, and `guardrails.py` / `policy_manager.py` used naive `date.today()`.

## Decision
1. Remove all `+12 hours` artificial offsets across the codebase.
2. Standardize on timezone-aware Vietnam time (`Asia/Ho_Chi_Minh`, `UTC+07:00`) via canonical helpers in `contracts/schemas.py` (`VN_TZ`, `get_vn_now()`, `get_vn_today()`, `get_system_now()`).
3. Emit explicit ISO 8601 `+07:00` timestamps (`YYYY-MM-DDTHH:MM:SS+07:00`) for all new writes in `conversation_service`, `telemetry_service` (`insert_audit_log`, `cancel_order`), and `document_service` (`policy_audit_logs.json`), and evaluate temporal policies against `get_vn_today()`.
4. Preserve historical persisted rows untouched (no automatic batch migration). Reconcile mixed legacy UTC (`telemetry_logs`) and legacy naive wall-clock (`conversation_sessions`, `policy_audit_logs.json`) records on read, chronological sorting, and frontend display (`frontend/src/lib/time.ts`).

## Alternatives Considered
- **Store all new timestamps in UTC (`Z`) and convert on display:** Viable standard alternative, but explicit `+07:00` ISO 8601 was chosen so both machine parsers (`datetime.fromisoformat`, JS `new Date`) and raw log/JSON/SQLite inspection/slicing (`created_at[11:16]`) remain directly readable in Vietnam time.
- **Batch-migrate existing SQLite/JSON/CSV history immediately:** Rejected per owner constraint to avoid destructive/risky mutations to historical data without a dedicated migration plan (`OD-008`).

## Consequences
- **Positive:** Eliminates 12-hour clock drift and UTC midnight date mismatches in Docker containers; preserves compatibility with existing `HH:MM` slicing and historical data.
- **Negative / Follow-up:** Pre-fix rows in `copilot_telemetry.sqlite3`, `copilot_conversations.sqlite3`, and `policy_audit_logs.json` remain in their original naive format (`ASM-003`).

# ADR-001: React/Vite as Primary UI and Streamlit Retained as Legacy

- **Status:** `Accepted` (`Confirmed` by owner; Docker Compose UI migration deferred)
- **Linked Requirements:** `PG-002`, `FR-UI-001`, `FR-UI-002`, `OD-001`
- **Linked Architecture / Specs:** [Architecture Overview](../architecture/overview.md), [Copilot Workflow Spec](../specs/copilot-workflow.md)

## Context
The repository contains two separate UI implementations (`Observed`):
1. `frontend/` — a React 18 / TypeScript / Vite SPA (`:5173`) supporting role selection (`/`), Customer Portal (`/customer`), Staff Workspace (`/staff`), SSE streaming (`/query_stream`), RBAC customer/staff views, policy management, audit notifications, telemetry, and evaluation dashboards.
2. `services/ui_service/` — a Streamlit application (`:8501`) currently wired into `docker-compose.yml` and `run_dev.py`.

Historical rationale for maintaining both UIs in parallel is **unverified** in repository records.

## Decision
- Designate **React/Vite (`frontend/`)** as the official primary UI for ongoing product development.
- Retain **Streamlit (`services/ui_service/`)** as a legacy UI for reference and existing flows.
- Do **not** delete `services/ui_service/` or modify `docker-compose.yml` UI container structure solely because of this decision.

## Alternatives Considered
- **Option A — Remove Streamlit immediately and containerize React in Compose:** Rejected for baseline v1 to avoid unrequested deployment/infrastructure disruption before a dedicated containerization plan (`OD-001`).
- **Option B — Dual-primary maintenance:** Rejected because new features (e.g., RBAC views, SSE streaming) already live primarily in `frontend/`.

## Consequences
- **Positive:** Clear target for all new UI work and frontend contract alignment (`frontend/src/types/index.ts`, `frontend/src/lib/time.ts`).
- **Negative / Follow-up:** `docker-compose.yml` continues to ship Streamlit by default while `frontend/` runs via `npm run dev` until `OD-001` is decided. `README.md` still reflects the Streamlit-centric quick start.

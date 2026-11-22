# Risk and Approval Policy — v0.2 candidate

> Canonical policy for risk and authority. The top-level `AGENTS.md` is only a summary. Markdown is not a security boundary: enforce key restrictions through least-privilege permissions, isolation, and CI where possible.

## Autonomy versus authority

- **Autonomy:** agent chooses investigation, design, implementation, and verification steps within the authorized task.
- **Authority:** agent may perform a particular action or produce a particular side effect.

Classify meaningful **actions**, not only entire tasks, using the highest applicable risk. A one-line change to an authorization rule can be high risk.

| Level | Examples | Default response |
| --- | --- | --- |
| R0 — inspection | Read non-secret code/docs, inspect `git status`, search symbols | Proceed within existing permissions; avoid exposing secret contents |
| R1 — scoped/reversible | Localized bug fix, test, documentation edit, isolated UI change | Proceed within task scope; use only side-effect-assessed verification |
| R2 — cross-boundary | Shared contracts, multi-service behavior, persistence changes, major dependencies | Create proportionate plan; map consumers, compatibility, test and rollback strategy; request approval if scope or agreed behavior changes |
| R3 — sensitive/high-impact | Deleting or corrupting data, production access/deployment, financial/security policy change, credential actions, paid/unapproved outbound calls | Stop before the action and obtain specific explicit authorization |

## Approval gates

Require explicit task-specific approval before:

- Deleting, overwriting, or destructively migrating important/shared/production data; resetting or cleaning work trees, rewriting history, or deleting someone else's changes.
- Pushing, merging, force-pushing, restarting/deploying a live environment, or changing production configuration.
- Materially changing security/authorization/financial policies; making a breaking API or schema change; performing unrequested broad refactors.
- Calling paid or sensitive external services, sending third-party messages/transactions, or transmitting sensitive content beyond already authorized access.
- Revoking, rotating, or distributing credentials, or changing infrastructure and access privileges.

Approval for an **investigation** does not imply permission to execute a fix, migration, deployment, or cleanup. Existing tool permissions may be stricter than this document.

## Pre-command side-effect gate

Before running a test, script, build, or service, examine whether it can:

1. Write tracked files, SQLite databases, JSON policy data, model/index artifacts, datasets, build outputs, or other state.
2. Connect to LLM APIs, running local services backed by persistent data, remote endpoints, or production; consume credits or send content.
3. Read/expose secrets, change environment settings, bind services, or trigger a destructive operation.

Check `docs/agent/REPO_GUIDE.md` for **candidate classifications**, then inspect the current command, imports/fixtures/config, and target environment. A static review is not a runtime guarantee. Prefer disposable worktrees, snapshots, temporary DBs, mocks, or explicit isolation. Unknown behavior is not automatically authorized.

## Escalation when risk increases

Stop before the newly risky step; preserve current state; explain evidence, uncertainty, affected scope, safe alternatives, verification, and recovery; ask only for approval required to cross the boundary. Independent safe investigation may continue.

## Short approval request

`Proposed action | Why necessary | Exact affected files/data/environment | Impact/rollback | Planned verification | Approval requested`

## Security response

If evidence indicates credentials embedded in source or exposed in history, report the **location and exposure risk only**, never the secret values. Prioritize owner-led revocation/rotation and exposure review; deleting a key from the latest commit does not undo earlier exposure. Identify TLS verification bypass as a separate issue and do not expand its use. See repo-specific leads in `REPO_GUIDE.md`.

## Enforcement

Apply real permission limits, branch protections, secret scanning, sandboxed tests, CI, and release approval gates where available. Do not interpret a successful prompt as proof of enforcement.

---
name: change-impact-analysis
description: >-
  Read-only pre-implementation dependency, contract, risk, and verification
  impact analysis before editing code, schemas, configs, or policies. Use when
  evaluating proposed changes to shared DTOs, APIs, guardrails, persistence, or
  cross-module boundaries to map callers, consumers, breaking risks, and
  minimal tests. Do not use for whole-repo onboarding (use repo-onboarding),
  resuming a handoff (use task-resume), or unrelated trivial Fast-path edits.
---

# Change Impact Analysis

Assess callers, contracts, invariants, risk boundaries, and verification needs
before modifying sensitive or cross-boundary code.

## Constraints

- **Read-only analysis first:** Do not edit source, schemas, or configs unless
  implementation is explicitly authorized.
- **Targeted tracing:** Use symbol/reference search (`git grep` / `rg`) instead
  of exhaustive codebase scans.
- **No unassessed side effects:** Never run live services, full unisolated test
  suites, or external calls during impact analysis.
- **No protocol duplication:** Follow
  [TASK_PROTOCOL.md](../../../docs/agent/TASK_PROTOCOL.md) for overall execution
  paths rather than restating it here.

## Procedure

1. **Pinpoint the Proposed Surface**
   - Identify exact target files, symbols, endpoints, schemas, or config keys.
   - Read [AGENTS.md](../../../AGENTS.md),
     [RISK_AND_APPROVAL.md](../../../docs/agent/RISK_AND_APPROVAL.md), and (if
     present) [REPO_GUIDE.md](../../../docs/agent/REPO_GUIDE.md) plus
     [verification.md](../../../docs/development/verification.md).

2. **Map Callers, Consumers & State**
   - Trace upstream callers, downstream clients, shared DTOs/types, persistent
     storage schemas, and environment/configuration consumers.
   - Inspect both producer and consumer code directly before claiming interface
     compatibility.

3. **Check Requirements, Specs & Invariants**
   - Locate affected requirements, specs, ADRs, and safety invariants
     (security/TLS, auth/RBAC, financial/temporal rules, fail-closed fallbacks).

4. **Classify Impacts & Risk Level**
   - Separate **`Confirmed` impacts** (verified in code/tests) from
     **`Plausible` impacts** (inferred or unverified cross-boundary/UI paths).
   - Assign the highest applicable risk (`R0`–`R3`) and flag any approval gate
     (breaking schema change, data migration, credential/security change).

5. **Recommend Minimal Safe Verification**
   - List the smallest targeted, side-effect-safe checks covering touched files
     and downstream consumers, plus any blocked or missing test coverage.

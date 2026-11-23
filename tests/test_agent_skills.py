"""Deterministic structural, reusability, and activation-eval checks for Agent Skills.

Note on activation scope:
  These tests verify skill structure, frontmatter separability, constraint compliance,
  context budget, and simulated read-only reconciliation offline. Live LLM implicit
  activation across an independent agent session cannot be verified inside unit tests
  and is tracked as a separate manual fresh-session pilot.
"""
from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest

from scripts.validate_skills import _parse_frontmatter, validate_skills_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"

EXPECTED_SKILLS = ("change-impact-analysis", "repo-onboarding", "task-resume")

# Terms that would indicate accidental coupling of project-agnostic core skills to
# repository-specific service or database names.
PROJECT_SPECIFIC_LEAK_TERMS = (
    "e-commerce-support-copilot",
    "rag_service",
    "document_service",
    "intent_service",
    "telemetry_service",
    "conversation_service",
    "copilot_telemetry.sqlite3",
    "copilot_conversations.sqlite3",
    "ckey.vn",
)

# Deterministic positive & negative activation evaluation set (Deliverable B).
ACTIVATION_EVAL_CASES = [
    # Positive: repo-onboarding
    ("Help me onboard to this repository and map its entrypoints, frameworks, tests, and knowledge gaps.", "repo-onboarding"),
    ("What is the architecture, tech stack, and agent harness setup in this unfamiliar codebase?", "repo-onboarding"),
    # Positive: task-resume
    ("Resume the task handed off in docs/tasks/TASK-20261122-isolate-policy-audit-test-handoff.md and reconcile Git state.", "task-resume"),
    ("Continue from the paused execution plan and check which handoff steps remain unverified.", "task-resume"),
    # Positive: change-impact-analysis
    ("Analyze the impact, callers, consumers, and verification risks before modifying shared DTOs or guardrails.", "change-impact-analysis"),
    ("What contracts, cross-module dependencies, and tests could break if I propose this schema change?", "change-impact-analysis"),
    # Negative: unrelated Fast-path tasks that should not match any of these 3 skills
    ("Fix the typo in this single error string on line 18.", None),
    ("Sort the imports alphabetically in one utility module.", None),
]

SKILL_CUE_WEIGHTS = {
    "repo-onboarding": {
        "onboard": 3,
        "unfamiliar": 3,
        "entrypoint": 2,
        "framework": 2,
        "architecture": 1,
        "tech stack": 2,
        "knowledge gaps": 2,
        "codebase": 1,
    },
    "task-resume": {
        "resume": 3,
        "handed-off": 3,
        "handoff": 3,
        "execution plan": 3,
        "paused": 2,
        "reconcile": 2,
        "continue": 1,
        "unverified": 1,
    },
    "change-impact-analysis": {
        "impact": 3,
        "caller": 2,
        "consumer": 2,
        "shared dto": 2,
        "guardrail": 2,
        "contract": 2,
        "dependenc": 2,
        "schema": 2,
        "cross-module": 2,
        "break": 2,
    },
}


def _score_frontmatter_match(prompt: str, metadata_by_skill: dict[str, dict[str, str]]) -> str | None:
    """Deterministic lexical routing probe over skill frontmatter metadata."""
    low = prompt.lower()
    scores: dict[str, int] = {}
    for skill_name, fm in metadata_by_skill.items():
        haystack = f"{fm.get('name', '')} {fm.get('description', '')}".lower()
        score = 0
        for cue, weight in SKILL_CUE_WEIGHTS[skill_name].items():
            if cue in low and cue in haystack:
                score += weight
        scores[skill_name] = score

    best_skill, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 3:
        return None
    return best_skill


class TestSkillValidator(unittest.TestCase):
    def test_live_repo_skills_pass_validator(self):
        """All committed repository skills under .agents/skills pass deterministic validation."""
        res = validate_skills_directory(SKILLS_DIR, repo_root=REPO_ROOT)
        self.assertTrue(res.ok, f"Unexpected validation errors: {res.errors}")
        self.assertEqual(tuple(sorted(res.skills_found)), EXPECTED_SKILLS)

    def test_live_skills_preserve_reusable_core_and_progressive_disclosure_budget(self):
        """Core skills avoid project-specific leaks, respect concise line/byte caps, and cite canonical docs."""
        total_frontmatter_chars = 0
        for skill_name in EXPECTED_SKILLS:
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            text = skill_md.read_text(encoding="utf-8")
            fm, body, errors = _parse_frontmatter(text, str(skill_md))
            self.assertEqual(errors, [])

            total_frontmatter_chars += len(fm["name"]) + len(fm["description"])
            self.assertLessEqual(len(text.splitlines()), 90, f"{skill_name} should stay concise for progressive disclosure")
            self.assertLessEqual(len(text.encode("utf-8")), 4500)

            low = text.lower()
            for leaked_term in PROJECT_SPECIFIC_LEAK_TERMS:
                self.assertNotIn(leaked_term, low, f"{skill_name} leaked repo-specific term {leaked_term!r}")

            self.assertIn("AGENTS.md", text)
            self.assertIn("Do not use", fm["description"])
            self.assertTrue(body.strip())

        self.assertLessEqual(total_frontmatter_chars, 1600)

    def test_validator_rejects_broken_and_malformed_skills(self):
        """Validator catches missing SKILL.md, name mismatch, duplicates, broken links, and file:// URIs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
            skills = root / ".agents" / "skills"

            # 1. Missing SKILL.md
            (skills / "empty-dir").mkdir(parents=True)

            # 2. Mismatched name + broken link + file:// link
            bad = skills / "bad-skill"
            bad.mkdir(parents=True)
            (bad / "SKILL.md").write_text(
                "---\n"
                "name: Wrong_Name\n"
                "description: Too short\n"
                "---\n\n"
                "# Bad\n"
                "[missing](../../../does_not_exist.md)\n"
                "[abs](file:///tmp/secret.txt)\n",
                encoding="utf-8",
            )

            # 3. Duplicate name across directories
            dup_a = skills / "alpha-skill"
            dup_b = skills / "beta-skill"
            dup_a.mkdir(parents=True)
            dup_b.mkdir(parents=True)
            valid_a = (
                "---\n"
                "name: alpha-skill\n"
                "description: Valid description explaining what alpha-skill does and when to run it.\n"
                "---\n\n"
                "# Alpha\n"
                "See [AGENTS.md](../../../AGENTS.md).\n"
            )
            (dup_a / "SKILL.md").write_text(valid_a, encoding="utf-8")
            (dup_b / "SKILL.md").write_text(valid_a, encoding="utf-8")

            res = validate_skills_directory(skills, repo_root=root)
            self.assertFalse(res.ok)
            joined = "\n".join(res.errors)
            self.assertIn("missing required SKILL.md", joined)
            self.assertIn("invalid skill name", joined)
            self.assertIn("must match directory name", joined)
            self.assertIn("description is too short", joined)
            self.assertIn("broken relative link", joined)
            self.assertIn("disallowed local/absolute link target", joined)
            self.assertIn("duplicate skill name 'alpha-skill'", joined)


class TestSkillQualityAndActivationEvalSet(unittest.TestCase):
    def test_frontmatter_routing_separability_on_positive_and_negative_cases(self):
        """Frontmatter metadata cleanly distinguishes positive, negative, and sibling prompts."""
        metadata: dict[str, dict[str, str]] = {}
        for skill_name in EXPECTED_SKILLS:
            text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
            fm, _, errors = _parse_frontmatter(text, skill_name)
            self.assertEqual(errors, [])
            metadata[skill_name] = fm

        for prompt, expected_skill in ACTIVATION_EVAL_CASES:
            matched = _score_frontmatter_match(prompt, metadata)
            self.assertEqual(matched, expected_skill, f"Prompt mismatch for {prompt!r}")

    def test_skill_procedures_enforce_read_only_and_permission_boundaries(self):
        """Skills defer authority to canonical docs and preserve safety constraints."""
        onboarding = (SKILLS_DIR / "repo-onboarding" / "SKILL.md").read_text(encoding="utf-8")
        resume = (SKILLS_DIR / "task-resume" / "SKILL.md").read_text(encoding="utf-8")
        impact = (SKILLS_DIR / "change-impact-analysis" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Read-only by default", onboarding)
        self.assertIn("Confirmed", onboarding)
        self.assertIn("Observed", onboarding)

        self.assertIn("Live state wins", resume)
        self.assertIn("CONTEXT_AND_MEMORY.md", resume)
        self.assertIn("RISK_AND_APPROVAL.md", resume)
        self.assertIn("COMPLETED", resume)

        self.assertIn("Read-only analysis first", impact)
        self.assertIn("TASK_PROTOCOL.md", impact)
        self.assertIn("RISK_AND_APPROVAL.md", impact)
        self.assertIn("Confirmed", impact)
        self.assertIn("Plausible", impact)


class TestSimulatedTaskResumePilot(unittest.TestCase):
    def test_completed_phase_iv_handoff_reconciles_without_reapplying_work(self):
        """Simulated read-only pilot target confirms completed status and disk alignment."""
        handoff_path = REPO_ROOT / "docs" / "tasks" / "TASK-20261122-isolate-policy-audit-test-handoff.md"
        plan_path = REPO_ROOT / "docs" / "tasks" / "TASK-20261122-isolate-policy-audit-test-plan.md"

        self.assertTrue(handoff_path.exists())
        self.assertTrue(plan_path.exists())

        handoff = handoff_path.read_text(encoding="utf-8")
        plan = plan_path.read_text(encoding="utf-8")

        self.assertRegex(handoff, r"\*\*Task Status:\*\*\s*`COMPLETED`")
        self.assertRegex(handoff, r"\*\*Verification Status:\*\*\s*`LOCALLY_VERIFIED`")
        self.assertRegex(plan, r"\*\*Task Status:\*\*\s*`COMPLETED`")
        self.assertIn("test_policy_audit_rollback.py", handoff)
        self.assertTrue((REPO_ROOT / "tests" / "test_policy_audit_rollback.py").exists())


if __name__ == "__main__":
    unittest.main()

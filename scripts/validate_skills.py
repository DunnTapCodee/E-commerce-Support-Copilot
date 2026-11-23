"""Deterministic stdlib-only validator for repository-scoped Agent Skills.

Validates `.agents/skills/<skill-name>/SKILL.md` directories against the shared
Agent Skills / Antigravity / Codex conventions without executing any skill
scripts or installing third-party dependencies.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Tuple

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HEADING_PATTERN = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_WINDOWS_ABS_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")

MAX_NAME_LENGTH = 64
MIN_DESCRIPTION_LENGTH = 20
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_LINES = 500
MAX_SKILL_BYTES = 24000


@dataclass
class SkillValidationResult:
    """Summary of validating all skills in a directory."""

    skills_dir: Path
    skills_found: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_frontmatter(text: str, rel_path: str) -> Tuple[Dict[str, str], str, List[str]]:
    """Parse minimal YAML frontmatter (scalars and > / | block scalars) using stdlib only."""
    errors: List[str] = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, [f"{rel_path}: missing opening YAML frontmatter delimiter '---' on line 1."]

    closing_idx: Optional[int] = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_idx = idx
            break

    if closing_idx is None:
        return {}, text, [f"{rel_path}: missing closing YAML frontmatter delimiter '---'."]

    fm_lines = lines[1:closing_idx]
    body = "\n".join(lines[closing_idx + 1 :])

    data: Dict[str, str] = {}
    i = 0
    while i < len(fm_lines):
        raw_line = fm_lines[i]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if raw_line[0].isspace():
            errors.append(f"{rel_path}: unexpected indented line in frontmatter line {i + 2}: {raw_line!r}")
            i += 1
            continue

        if ":" not in raw_line:
            errors.append(f"{rel_path}: invalid frontmatter entry on line {i + 2}: {raw_line!r}")
            i += 1
            continue

        key, raw_val = raw_line.split(":", 1)
        key = key.strip()
        val = raw_val.strip()

        if not key:
            errors.append(f"{rel_path}: empty frontmatter key on line {i + 2}.")
            i += 1
            continue

        if val in (">", ">-", "|", "|-"):
            fold = val.startswith(">")
            block_lines: List[str] = []
            i += 1
            base_indent: Optional[int] = None
            while i < len(fm_lines):
                next_line = fm_lines[i]
                if not next_line.strip():
                    block_lines.append("")
                    i += 1
                    continue
                indent = len(next_line) - len(next_line.lstrip(" "))
                if indent == 0:
                    break
                if base_indent is None:
                    base_indent = indent
                block_lines.append(next_line[min(base_indent, indent) :])
                i += 1

            if fold:
                paragraphs: List[str] = []
                current: List[str] = []
                for bl in block_lines:
                    if bl == "":
                        if current:
                            paragraphs.append(" ".join(current))
                            current = []
                    else:
                        current.append(bl.strip())
                if current:
                    paragraphs.append(" ".join(current))
                data[key] = "\n".join(paragraphs).strip()
            else:
                data[key] = "\n".join(block_lines).strip()
            continue

        if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
            val = val[1:-1]
        data[key] = val
        i += 1

    return data, body, errors


def _strip_fenced_code_blocks(markdown_text: str) -> str:
    """Remove fenced code blocks before checking Markdown links."""
    kept: List[str] = []
    in_fence = False
    fence_marker = ""
    for line in markdown_text.splitlines():
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_marker = stripped[:3]
                continue
            kept.append(line)
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
    return "\n".join(kept)


def _validate_links(skill_md: Path, body: str, repo_root: Path, rel_path: str) -> List[str]:
    """Ensure relative Markdown links in SKILL.md resolve inside repo_root."""
    errors: List[str] = []
    scannable = _strip_fenced_code_blocks(body)
    resolved_root = repo_root.resolve()

    for match in _LINK_PATTERN.finditer(scannable):
        raw_target = match.group(1).strip()
        target = raw_target.split("#", 1)[0].strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("file://") or _WINDOWS_ABS_PATTERN.match(target):
            errors.append(f"{rel_path}: disallowed local/absolute link target {raw_target!r}; use relative paths.")
            continue

        resolved = (skill_md.parent / target).resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError:
            errors.append(f"{rel_path}: relative link {raw_target!r} escapes repository root.")
            continue

        if not resolved.exists():
            errors.append(f"{rel_path}: broken relative link target {raw_target!r} -> {resolved}")

    return errors


def validate_skills_directory(
    skills_dir: Path,
    repo_root: Optional[Path] = None,
) -> SkillValidationResult:
    """Validate all skills under skills_dir without executing any contained scripts."""
    resolved_skills_dir = skills_dir.resolve()
    resolved_repo_root = (repo_root or resolved_skills_dir.parent.parent).resolve()
    result = SkillValidationResult(skills_dir=resolved_skills_dir)

    if not resolved_skills_dir.exists() or not resolved_skills_dir.is_dir():
        result.errors.append(f"Skills directory does not exist: {resolved_skills_dir}")
        return result

    seen_names: Dict[str, str] = {}
    entries = sorted(resolved_skills_dir.iterdir(), key=lambda p: p.name)
    skill_dirs = [p for p in entries if p.is_dir()]

    for entry in entries:
        if entry.is_file():
            result.errors.append(f"Unexpected top-level file in skills root (expected <skill>/SKILL.md): {entry.name}")

    if not skill_dirs:
        result.errors.append(f"No skill directories found in {resolved_skills_dir}")
        return result

    for skill_dir in skill_dirs:
        if skill_dir.name.startswith("."):
            continue

        actual_names = {p.name for p in skill_dir.iterdir()}
        if "SKILL.md" not in actual_names:
            result.errors.append(f"Skill directory '{skill_dir.name}' is missing required SKILL.md.")
            continue

        skill_md = skill_dir / "SKILL.md"
        try:
            rel_path = skill_md.resolve().relative_to(resolved_repo_root).as_posix()
        except ValueError:
            rel_path = str(skill_md)

        raw_bytes = skill_md.read_bytes()
        if len(raw_bytes) > MAX_SKILL_BYTES:
            result.errors.append(
                f"{rel_path}: exceeds progressive disclosure byte limit ({len(raw_bytes)} > {MAX_SKILL_BYTES})."
            )

        text = raw_bytes.decode("utf-8")
        line_count = len(text.splitlines())
        if line_count > MAX_SKILL_LINES:
            result.errors.append(
                f"{rel_path}: exceeds progressive disclosure line limit ({line_count} > {MAX_SKILL_LINES})."
            )

        frontmatter, body, fm_errors = _parse_frontmatter(text, rel_path)
        result.errors.extend(fm_errors)

        name = frontmatter.get("name", "").strip()
        description = frontmatter.get("description", "").strip()

        if not name:
            result.errors.append(f"{rel_path}: missing required frontmatter field 'name'.")
        else:
            if len(name) > MAX_NAME_LENGTH or not _NAME_PATTERN.match(name):
                result.errors.append(
                    f"{rel_path}: invalid skill name {name!r} (expected lowercase hyphenated <= {MAX_NAME_LENGTH} chars)."
                )
            if name != skill_dir.name:
                result.errors.append(
                    f"{rel_path}: frontmatter name {name!r} must match directory name {skill_dir.name!r}."
                )
            if name in seen_names:
                result.errors.append(
                    f"{rel_path}: duplicate skill name {name!r} (already defined in {seen_names[name]})."
                )
            else:
                seen_names[name] = rel_path

        if not description:
            result.errors.append(f"{rel_path}: missing required frontmatter field 'description'.")
        else:
            if len(description) < MIN_DESCRIPTION_LENGTH:
                result.errors.append(
                    f"{rel_path}: description is too short ({len(description)} < {MIN_DESCRIPTION_LENGTH} chars)."
                )
            if len(description) > MAX_DESCRIPTION_LENGTH:
                result.errors.append(
                    f"{rel_path}: description exceeds {MAX_DESCRIPTION_LENGTH} chars ({len(description)})."
                )

        if not body.strip():
            result.errors.append(f"{rel_path}: Markdown instruction body after frontmatter is empty.")
        elif not _HEADING_PATTERN.search(body):
            result.errors.append(f"{rel_path}: Markdown body must contain at least one section heading.")

        result.errors.extend(_validate_links(skill_md, body, resolved_repo_root, rel_path))
        result.skills_found.append(name or skill_dir.name)

    return result


def main(argv: Optional[List[str]] = None) -> int:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate repository-scoped Agent Skills.")
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=default_root / ".agents" / "skills",
        help="Path to skills directory (default: .agents/skills)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_root,
        help="Repository root boundary for relative link checks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON validation summary.",
    )
    args = parser.parse_args(argv)

    res = validate_skills_directory(args.skills_dir, repo_root=args.repo_root)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": res.ok,
                    "skills_dir": str(res.skills_dir),
                    "skills_found": res.skills_found,
                    "errors": res.errors,
                    "warnings": res.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if res.ok:
            print(f"SKILLS VALID ({len(res.skills_found)}): {', '.join(res.skills_found)}")
        else:
            print(f"SKILL VALIDATION FAILED ({len(res.errors)} error(s)):")
            for err in res.errors:
                print(f"  - {err}")

    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())

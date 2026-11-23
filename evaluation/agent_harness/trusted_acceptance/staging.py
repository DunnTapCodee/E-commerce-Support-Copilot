"""Isolated temporary grader staging and runtime instrumentation helpers.

Runs evaluator-owned acceptance tests and monitored/fault-injected probes inside
a disposable temporary copy of the candidate workspace so neither the user's
source repository nor the agent's sandbox is ever mutated by grading.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

IGNORED_STAGE_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "copilot_telemetry.sqlite3",
    "copilot_telemetry.sqlite3-wal",
    "copilot_telemetry.sqlite3-shm",
    "copilot_conversations.sqlite3",
    "copilot_conversations.sqlite3-wal",
    "copilot_conversations.sqlite3-shm",
}


def stage_candidate_workspace(candidate_root: Path, stage_dir: Path) -> Path:
    """Copy candidate workspace into an isolated temporary grader staging dir."""
    staged = stage_dir / "candidate_stage"

    def _ignore(_dir: str, names: List[str]) -> List[str]:
        return [n for n in names if n in IGNORED_STAGE_NAMES]

    shutil.copytree(candidate_root, staged, ignore=_ignore)
    return staged


def run_monitored_pytest_and_imports(
    staged_root: Path,
    test_rel_path: str,
    *,
    unset_env_keys: Sequence[str] = (),
    extra_env: Optional[Dict[str, str]] = None,
    pre_import_module: Optional[str] = None,
    timeout_seconds: int = 120,
) -> Tuple[int, str, List[str]]:
    """Run pytest (and optional pre-import) with runtime sqlite3.connect path tracking."""
    with tempfile.TemporaryDirectory() as trace_dir:
        trace_file = Path(trace_dir) / "sqlite_connect_trace.json"
        runner_script = Path(trace_dir) / "monitored_runner.py"
        runner_script.write_text(
            "import importlib, json, os, pathlib, sqlite3, sys\n"
            "import pytest\n"
            "\n"
            "trace_path = pathlib.Path(os.environ['EVAL_SQLITE_TRACE_FILE'])\n"
            "opened = []\n"
            "_orig_connect = sqlite3.connect\n"
            "\n"
            "def _tracked_connect(database, *args, **kwargs):\n"
            "    db_str = os.fspath(database) if isinstance(database, (str, bytes, os.PathLike)) else str(database)\n"
            "    if isinstance(db_str, bytes):\n"
            "        db_str = db_str.decode('utf-8', errors='replace')\n"
            "    if db_str != ':memory:' and not db_str.startswith('file::memory:'):\n"
            "        opened.append(str(pathlib.Path(db_str).resolve()))\n"
            "    else:\n"
            "        opened.append(db_str)\n"
            "    return _orig_connect(database, *args, **kwargs)\n"
            "\n"
            "sqlite3.connect = _tracked_connect\n"
            "pre_mod = os.environ.get('EVAL_PRE_IMPORT_MODULE', '').strip()\n"
            "try:\n"
            "    if pre_mod:\n"
            "        importlib.import_module(pre_mod)\n"
            "    rc = pytest.main([sys.argv[1], '-v'])\n"
            "finally:\n"
            "    trace_path.write_text(json.dumps(opened), encoding='utf-8')\n"
            "raise SystemExit(rc)\n",
            encoding="utf-8",
        )

        env = os.environ.copy()
        for key in unset_env_keys:
            env.pop(key, None)
        if extra_env:
            env.update(extra_env)
        env["EVAL_SQLITE_TRACE_FILE"] = str(trace_file)
        if pre_import_module:
            env["EVAL_PRE_IMPORT_MODULE"] = pre_import_module
        else:
            env.pop("EVAL_PRE_IMPORT_MODULE", None)
        env["PYTHONPATH"] = str(staged_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        proc = subprocess.run(
            [sys.executable, str(runner_script), test_rel_path],
            cwd=str(staged_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        opened_paths: List[str] = []
        if trace_file.exists():
            opened_paths = json.loads(trace_file.read_text(encoding="utf-8"))
        return proc.returncode, proc.stdout + "\n" + proc.stderr, opened_paths


def run_fault_probe_pytest(
    staged_root: Path,
    test_rel_path: str,
    fault_setup_code: str,
    *,
    extra_env: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 90,
) -> Tuple[int, str]:
    """Run candidate pytest with evaluator-injected behavioral faults after test module collection.

    A genuine non-vacuous test suite MUST fail (returncode != 0) when core behaviors
    are broken. If pytest exits 0 under fault injection, the test suite is vacuous.
    """
    with tempfile.TemporaryDirectory() as probe_dir:
        probe_script = Path(probe_dir) / "fault_probe_runner.py"
        class_body = "\n".join("        " + line for line in fault_setup_code.splitlines())
        probe_script.write_text(
            "import sys\n"
            "import pytest\n"
            "\n"
            "def _rebind_across_modules(attr_name, replacement):\n"
            "    for mod in list(sys.modules.values()):\n"
            "        if mod is not None and hasattr(mod, attr_name):\n"
            "            try:\n"
            "                setattr(mod, attr_name, replacement)\n"
            "            except Exception:\n"
            "                pass\n"
            "\n"
            "class _FaultPlugin:\n"
            "    def pytest_collection_modifyitems(self, session, config, items):\n"
            + class_body
            + "\n        print('EVAL_FAULT_PLUGIN_ARMED', flush=True)\n\n"
            "raise SystemExit(pytest.main([sys.argv[1], '-q'], plugins=[_FaultPlugin()]))\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        env["PYTHONPATH"] = str(staged_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        proc = subprocess.run(
            [sys.executable, str(probe_script), test_rel_path],
            cwd=str(staged_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout + "\n" + proc.stderr


def run_evaluator_acceptance_script(
    staged_root: Path,
    script_body: str,
    *,
    extra_env: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 120,
) -> Tuple[int, str]:
    """Execute an evaluator-owned acceptance script against staged candidate code."""
    with tempfile.TemporaryDirectory() as run_dir:
        script_path = Path(run_dir) / "accept_suite.py"
        script_path.write_text(script_body, encoding="utf-8")
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        env["PYTHONPATH"] = str(staged_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(staged_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout + "\n" + proc.stderr

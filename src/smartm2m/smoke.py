"""Offline end-to-end smoke test for the controller and reporting path."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .agent import CustomAgent
from .config import ArmConfig, TaskSpec
from .model import ScriptedModel
from .protocol import ModelResponse, ToolCall
from .reporting import outcomes_for_tasks, summary_for_pairs, write_summary
from .task import prepared_workspace
from .tools import ToolRunner
from .validation import validate_clean_replay, write_validation


def _call(number: int, name: str, arguments: dict[str, Any] | None = None) -> ModelResponse:
    return ModelResponse(tool_calls=[ToolCall(f"smoke-{number}", name, arguments or {})])


def _git(root: Path, *args: str, input_text: str | None = None) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")


def _fixture(root: Path) -> Path:
    repo = root / "calculator"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left - right\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n"
        "def test_adds_two_numbers():\n"
        "    assert add(2, 3) == 5\n\n"
        "def test_adds_zero():\n"
        "    assert add(4, 0) == 4\n",
        encoding="utf-8",
    )
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "smoke@example.invalid")
    _git(repo, "config", "user.name", "SMARTM2M smoke")
    _git(repo, "add", "src", "tests")
    _git(repo, "commit", "-m", "fixture base")
    return repo


def run_smoke(output_dir: str | Path | None = None) -> Path:
    destination = Path(output_dir).resolve() if output_dir else Path("results").resolve() / "smoke"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smartm2m-smoke-") as temp:
        fixture = _fixture(Path(temp))
        task = TaskSpec(
            instance_id="synthetic__calculator-1",
            problem_statement="The add function subtracts its right operand. Make addition correct without changing tests.",
            repo_path=str(fixture),
            test_commands=(
                'python -c "from src.calculator import add; assert add(2, 3) == 5; assert add(4, 0) == 4"',
            ),
        )
        patch = """diff --git a/src/calculator.py b/src/calculator.py
index 3b0f0e4..e0b9db1 100644
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,2 +1,2 @@
 def add(left: int, right: int) -> int:
-    return left - right
+    return left + right
"""
        model = ScriptedModel([
            _call(1, "list_files"),
            _call(2, "read_file", {"path": "src/calculator.py"}),
            _call(3, "apply_patch", {"patch": patch}),
            _call(4, "run_tests", {"command": "default"}),
            _call(5, "get_diff"),
            _call(6, "submit_patch"),
        ])
        custom_dir = destination / "custom" / task.instance_id.replace("/", "__")
        with prepared_workspace(task, destination / "workspaces") as workspace:
            runner = ToolRunner(workspace, task, command_timeout=30)
            result = CustomAgent(model, arm=ArmConfig(
                max_turns=10,
                cost_limit_usd=0.50,
                wall_time_seconds=120,
                command_timeout_seconds=30,
            )).run(task, runner)
            validation = validate_clean_replay(workspace, task.test_commands[0], timeout_seconds=30)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "candidate.patch").write_text(result.patch, encoding="utf-8")
            (custom_dir / "trajectory.json").write_text(
                json.dumps({"events": result.events}, indent=2) + "\n", encoding="utf-8"
            )
            (custom_dir / "commands.jsonl").write_text(
                "\n".join(json.dumps(row) for row in result.commands) + "\n", encoding="utf-8"
            )
            (custom_dir / "agent.json").write_text(json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8")
            write_validation(custom_dir / "validation.json", validation)

        baseline_row = {
            "instance_id": task.instance_id,
            "status": "completed",
            "reason": "smoke reference stub emits an empty patch",
            "patch_sha256": hashlib.sha256(b"").hexdigest(),
            "model_patch": "",
        }
        custom_row = {
            **result.as_dict(),
            "model_patch": result.patch,
            "validation_status": validation.status,
        }
        (destination / "reference").mkdir(parents=True, exist_ok=True)
        (destination / "custom").mkdir(parents=True, exist_ok=True)
        (destination / "reference" / "generation.jsonl").write_text(json.dumps(baseline_row) + "\n", encoding="utf-8")
        (destination / "custom" / "generation.jsonl").write_text(json.dumps(custom_row) + "\n", encoding="utf-8")
        (destination / "reference" / "predictions.jsonl").write_text(
            json.dumps({"instance_id": task.instance_id, "model_name_or_path": "smoke-stub", "model_patch": ""}) + "\n",
            encoding="utf-8",
        )
        (destination / "custom" / "predictions.jsonl").write_text(
            json.dumps({"instance_id": task.instance_id, "model_name_or_path": "smoke-stub", "model_patch": result.patch}) + "\n",
            encoding="utf-8",
        )
        (destination / "evaluation" / "reference").mkdir(parents=True, exist_ok=True)
        (destination / "evaluation" / "custom").mkdir(parents=True, exist_ok=True)
        (destination / "evaluation" / "reference" / "result.json").write_text(json.dumps({
            "instance_id": task.instance_id,
            "resolved": False,
            "status": "tests_failed",
            "reason": "empty smoke baseline patch",
        }) + "\n", encoding="utf-8")
        (destination / "evaluation" / "custom" / "result.json").write_text(json.dumps({
            "instance_id": task.instance_id,
            "resolved": validation.status == "passed",
            "status": "resolved" if validation.status == "passed" else "tests_failed",
            "reason": validation.reason,
        }) + "\n", encoding="utf-8")
        (destination / "manifest.json").write_text(json.dumps({
            "run_id": destination.name,
            "protocol_version": "synthetic-smoke-v1",
            "expected_count": 1,
            "tasks": [task.generation_projection()],
            "note": "Offline controller/reporting smoke; not SWE-bench evidence.",
        }, indent=2) + "\n", encoding="utf-8")
        baseline = outcomes_for_tasks(
            [task.instance_id],
            {task.instance_id: baseline_row},
            {task.instance_id: {"resolved": False, "status": "tests_failed"}},
        )
        custom = outcomes_for_tasks(
            [task.instance_id],
            {task.instance_id: custom_row},
            {task.instance_id: {"resolved": validation.status == "passed", "status": validation.status}},
        )
        summary = summary_for_pairs([task.instance_id], baseline, custom, 1)
        summary["run_id"] = destination.name
        summary["kind"] = "synthetic_smoke"
        write_summary(destination / "summary.json", summary)
        (destination / "contamination.md").write_text(
            "# Smoke contamination note\n\n"
            "This is a local synthetic fixture used only to test controller and reporting plumbing. "
            "It is not a benchmark result and has no claim about model memorization.\n",
            encoding="utf-8",
        )
        checksum_lines = []
        for path in sorted(destination.rglob("*")):
            if path.is_file() and path.name != "checksums.sha256":
                checksum_lines.append(
                    f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(destination).as_posix()}"
                )
        (destination / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return destination

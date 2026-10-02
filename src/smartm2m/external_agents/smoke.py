"""Offline and live smoke test for external coding agents on synthetic repositories."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..config import TaskSpec
from .antigravity import AntigravityAgent
from .codex import CodexAgent
from .config import ExternalAgentsConfig
from .runner import run_task_attempt


def run_external_smoke(
    output_dir: str | Path = "results/external-smoke",
    *,
    agent_choice: str = "all",
    live: bool = True,
) -> dict[str, Any]:
    """Execute a low-cost integration smoke test on a synthetic repository.

    Never touches frozen SWE-bench benchmark tasks or historical results.
    """
    out_root = Path(output_dir).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # 1. Create synthetic fixture repository
    fixture_dir = Path(tempfile.mkdtemp(prefix="smartm2m-smoke-repo-"))
    try:
        subprocess.run(["git", "init", "-b", "main"], cwd=fixture_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "smoke@example.com"], cwd=fixture_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Smoke Runner"], cwd=fixture_dir, check=True)

        source_file = fixture_dir / "greeter.py"
        source_file.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        test_file = fixture_dir / "test_greeter.py"
        test_file.write_text("from greeter import greet\n\ndef test_greet():\n    assert greet() == 'hello world'\n", encoding="utf-8")

        subprocess.run(["git", "add", "greeter.py", "test_greeter.py"], cwd=fixture_dir, check=True)
        subprocess.run(["git", "commit", "-m", "initial synthetic base"], cwd=fixture_dir, check=True)
        head_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=fixture_dir,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

        synthetic_task = TaskSpec(
            instance_id="synthetic-smoke-001",
            problem_statement="In greeter.py, change the return value of greet() from 'hello' to 'hello world'.",
            repo_path=str(fixture_dir),
            base_commit=head_commit,
            test_commands=("python3 -m pytest test_greeter.py",),
        )

        smoke_config = ExternalAgentsConfig(
            protocol_version="external-agents-smoke-v1",
            manifest_path=fixture_dir / "manifest.json",
            expected_count=1,
            tasks=(synthetic_task,),
            wall_time_seconds=180,
            command_timeout_seconds=60,
            results_root=out_root,
        )

        workspaces_dir = out_root / "workspaces"
        report: dict[str, Any] = {
            "status": "completed",
            "agents": {},
        }

        if agent_choice in {"codex", "all"} and live:
            codex_agent = CodexAgent(
                executable="codex",
                model="gpt-6.1-sol",
                sandbox="workspace-write",
                ephemeral=True,
                ignore_user_config=True,
                ignore_rules=True,
            )
            codex_out = out_root / "codex" / "tasks" / synthetic_task.instance_id
            codex_res = run_task_attempt(codex_agent, synthetic_task, smoke_config, workspaces_dir, codex_out)
            report["agents"]["codex"] = {
                "terminal_status": codex_res.terminal_status,
                "exit_code": codex_res.exit_code,
                "has_patch": bool(codex_res.patch.strip()),
                "patch_sha256": codex_res.patch_sha256,
                "wall_duration_seconds": codex_res.wall_duration_seconds,
            }

        if agent_choice in {"agy", "all"} and live:
            agy_agent = AntigravityAgent(
                executable="agy",
                model="gemini-3.8-flash-high",
                effort="high",
                output_format="stream-json",
                dangerously_skip_permissions=True,
                disable_slash_commands=True,
            )
            agy_out = out_root / "agy" / "tasks" / synthetic_task.instance_id
            agy_res = run_task_attempt(agy_agent, synthetic_task, smoke_config, workspaces_dir, agy_out)
            report["agents"]["agy"] = {
                "terminal_status": agy_res.terminal_status,
                "exit_code": agy_res.exit_code,
                "has_patch": bool(agy_res.patch.strip()),
                "patch_sha256": agy_res.patch_sha256,
                "wall_duration_seconds": agy_res.wall_duration_seconds,
            }

        (out_root / "smoke-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    finally:
        shutil.rmtree(fixture_dir, ignore_errors=True)

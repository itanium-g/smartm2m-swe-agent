import subprocess
from pathlib import Path

from smartm2m.agent import CustomAgent
from smartm2m.config import ArmConfig, TaskSpec
from smartm2m.model import ScriptedModel
from smartm2m.protocol import ModelResponse, ToolCall
from smartm2m.tools import ToolRunner


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "agent"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    return repo


def _response(number: int, name: str, arguments=None) -> ModelResponse:
    return ModelResponse(tool_calls=[ToolCall(str(number), name, arguments or {})])


def test_build_failure_rolls_back_and_allows_repair(tmp_path: Path):
    repo = _repo(tmp_path)
    task = TaskSpec(
        "synthetic__rollback-1",
        "Make VALUE equal to 2.",
        repo_path=str(repo),
        test_commands=("python -m py_compile src/value.py",),
    )
    bad = """diff --git a/src/value.py b/src/value.py
--- a/src/value.py
+++ b/src/value.py
@@ -1 +1 @@
-VALUE = 1
+VALUE =
"""
    good = """diff --git a/src/value.py b/src/value.py
--- a/src/value.py
+++ b/src/value.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 2
"""
    model = ScriptedModel([
        _response(1, "read_file", {"path": "src/value.py"}),
        _response(2, "apply_patch", {"patch": bad}),
        _response(3, "run_tests"),
        _response(4, "apply_patch", {"patch": good}),
        _response(5, "run_tests"),
        _response(6, "submit_patch"),
    ])
    result = CustomAgent(model, arm=ArmConfig(max_turns=10, wall_time_seconds=60, command_timeout_seconds=20)).run(
        task, ToolRunner(repo, task, command_timeout=20)
    )
    assert result.status == "submitted"
    assert result.recovery_used
    assert "VALUE = 2" in result.patch
    assert result.model_requests == 6
    assert result.model_attempts == 6

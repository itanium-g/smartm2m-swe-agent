import json
import subprocess
from pathlib import Path

from smartm2m.agent import CustomAgent, _prune_history
from smartm2m.config import ArmConfig, TaskSpec
from smartm2m.model import ModelError, ScriptedModel
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


def test_repeated_passing_test_preserves_patch(tmp_path: Path):
    repo = _repo(tmp_path)
    task = TaskSpec("synthetic__repeat", "Set VALUE to two.", repo_path=str(repo),
                    test_commands=('python -c "from src.value import VALUE; assert VALUE == 2"',))
    model = ScriptedModel([
        _response(1, "read_file", {"path": "src/value.py"}),
        _response(2, "edit_file", {"path": "src/value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}),
        _response(3, "run_tests"),
        _response(4, "run_tests"),
        _response(5, "submit_patch"),
    ])
    result = CustomAgent(model, arm=ArmConfig(max_turns=6)).run(task, ToolRunner(repo, task))
    assert result.status == "submitted"
    assert not result.recovery_used
    assert "VALUE = 2" in result.patch


def test_reading_different_ranges_does_not_exhaust_loop(tmp_path: Path):
    repo = _repo(tmp_path)
    task = TaskSpec("synthetic__ranges", "Set VALUE to two.", repo_path=str(repo),
                    test_commands=('python -c "from src.value import VALUE; assert VALUE == 2"',))
    responses = [_response(i, "read_file", {"path": "src/value.py", "start_line": 1, "end_line": i}) for i in range(1, 8)]
    responses.extend([
        _response(8, "edit_file", {"path": "src/value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}),
        _response(9, "run_tests"), _response(10, "submit_patch"),
    ])
    result = CustomAgent(ScriptedModel(responses), arm=ArmConfig(max_turns=12)).run(task, ToolRunner(repo, task))
    assert result.status == "submitted"


def test_import_failure_does_not_discard_valid_edit(tmp_path: Path):
    repo = _repo(tmp_path)
    task = TaskSpec("synthetic__import", "Set VALUE to two.", repo_path=str(repo), test_commands=(
        'python -c "raise ImportError(\'invalid test target\')"',
        'python -c "from src.value import VALUE; assert VALUE == 2"',
    ))
    responses = [
        _response(1, "read_file", {"path": "src/value.py"}),
        _response(2, "edit_file", {"path": "src/value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}),
        _response(3, "run_tests"),
        _response(4, "run_tests", {"command": "command_1"}),
        _response(5, "submit_patch"),
    ]
    result = CustomAgent(ScriptedModel(responses), arm=ArmConfig(max_turns=6)).run(task, ToolRunner(repo, task))
    assert result.status == "submitted"
    assert not any(event["kind"] == "automatic_rollback" for event in result.events)


def test_failed_repeated_command_preserves_edit(tmp_path: Path):
    repo = _repo(tmp_path)
    task = TaskSpec("synthetic__failure", "Set VALUE to two.", repo_path=str(repo), test_commands=(
        'python -c "assert False"', 'python -c "from src.value import VALUE; assert VALUE == 2"',
    ))
    responses = [
        _response(1, "read_file", {"path": "src/value.py"}),
        _response(2, "edit_file", {"path": "src/value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}),
        _response(3, "run_tests"), _response(4, "run_tests"),
        _response(5, "run_tests", {"command": "command_1"}), _response(6, "submit_patch"),
    ]
    result = CustomAgent(ScriptedModel(responses), arm=ArmConfig(max_turns=7)).run(task, ToolRunner(repo, task))
    assert result.status == "submitted"
    assert result.recovery_used
    assert any(event.get("result") == "workspace preserved" for event in result.events)


def test_protocol_error_can_recover_within_turn_budget(tmp_path: Path):
    class RecoveringModel(ScriptedModel):
        def complete(self, *args, **kwargs):
            if not self.logical_requests:
                self.logical_requests += 1
                self.request_attempts += 1
                raise ModelError("provider rejected malformed tool output", recoverable=True)
            return super().complete(*args, **kwargs)

    repo = _repo(tmp_path)
    task = TaskSpec("synthetic__protocol", "Set VALUE to two.", repo_path=str(repo),
                    test_commands=('python -c "from src.value import VALUE; assert VALUE == 2"',))
    model = RecoveringModel([
        _response(1, "read_file", {"path": "src/value.py"}),
        _response(2, "edit_file", {"path": "src/value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}),
        _response(3, "run_tests"), _response(4, "submit_patch"),
    ])
    result = CustomAgent(model, arm=ArmConfig(max_turns=6)).run(task, ToolRunner(repo, task))
    assert result.status == "submitted"
    assert result.model_requests == 5
    assert result.estimated_cost_usd is None
    assert any(event["kind"] == "model_error" for event in result.events)


def test_history_pruning_preserves_tool_pairs_and_json():
    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "issue"}]
    for index in range(12):
        messages.extend([
            {"role": "assistant", "tool_calls": [{"id": str(index), "type": "function", "function": {
                "name": "edit_file", "arguments": json.dumps({"old_text": "x" * 2000}),
            }}]},
            {"role": "tool", "tool_call_id": str(index), "content": json.dumps({
                "ok": True, "content": "source" * 1000, "metadata": {"path": "src/value.py"},
            })},
        ])
    pruned = _prune_history(messages, max_chars=24000)
    pending = set()
    for message in pruned:
        if message["role"] == "assistant":
            pending.update(call["id"] for call in message["tool_calls"])
        if message["role"] == "tool":
            pending.remove(message["tool_call_id"])
            assert json.loads(message["content"])["ok"]
    assert not pending
    assert len(json.dumps(pruned)) <= 24000
    assert len(pruned) < len(messages)
def test_controller_rejects_edit_before_successful_inspection(tmp_path: Path):
    repo = _repo(tmp_path)
    task = TaskSpec(
        "synthetic__inspection-1",
        "Make VALUE equal to 2.",
        repo_path=str(repo),
        test_commands=("python -m py_compile src/value.py",),
    )
    patch = """diff --git a/src/value.py b/src/value.py
--- a/src/value.py
+++ b/src/value.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 2
"""
    model = ScriptedModel([
        _response(1, "apply_patch", {"patch": patch}),
        _response(2, "read_file", {"path": "src/value.py"}),
        _response(3, "apply_patch", {"patch": patch}),
        _response(4, "run_tests"),
        _response(5, "submit_patch"),
    ])
    result = CustomAgent(model, arm=ArmConfig(max_turns=8, wall_time_seconds=60, command_timeout_seconds=20)).run(
        task, ToolRunner(repo, task, command_timeout=20)
    )

    assert result.status == "submitted"
    assert any(
        event["kind"] == "tool_result"
        and event["result"]["metadata"].get("error") == "inspection_required"
        for event in result.events
    )
    assert "VALUE = 2" in result.patch

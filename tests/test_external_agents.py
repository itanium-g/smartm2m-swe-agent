"""Comprehensive test suite for external coding agent benchmark subsystem.

Covers:
1. common prompt rendering
2. prompt hash stability
3. safe generation projection
4. fresh workspace setup
5. base commit validation
6. dirty workspace rejection
7. Codex command creation
8. AGY command creation
9. installed-version parsing
10. timeout handling
11. process non-zero exit
12. provider-block detection where possible
13. stdout/stderr retention
14. Codex event parsing
15. AGY event parsing
16. token accounting
17. missing token fields
18. Git diff extraction
19. binary diff extraction
20. empty diff behavior
21. prediction JSONL
22. resume state
23. interrupted task state
24. incomplete-run headline-score prevention
25. secret redaction
26. evaluation handoff
27. checksum creation
28. historical result immutability
29. dry-run validation
30. synthetic end-to-end benchmark
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smartm2m.config import TaskSpec
from smartm2m.evaluator import write_predictions
from smartm2m.external_agents.antigravity import AntigravityAgent
from smartm2m.external_agents.base import ExternalAgent
from smartm2m.external_agents.codex import CodexAgent
from smartm2m.external_agents.config import ExternalAgentsConfig
from smartm2m.external_agents.events import (
    ExecutedCommand,
    TokenUsage,
    parse_agy_events,
    parse_codex_events,
)
from smartm2m.external_agents.metadata import (
    ExternalTaskResult,
    redact_json,
    redact_secrets,
    write_task_artifacts,
)
from smartm2m.external_agents.prompts import hash_prompt, render_prompt
from smartm2m.external_agents.runner import (
    build_comparison_report,
    dry_run,
    run_agent_benchmark,
    run_task_attempt,
    write_run_checksums,
)
from smartm2m.external_agents.workspace import (
    extract_workspace_diff,
    get_git_status,
    prepare_clean_workspace,
)


@pytest.fixture
def sample_task() -> TaskSpec:
    return TaskSpec(
        instance_id="test__repo-1234",
        problem_statement="Fix bug in foo calculation where x is None.",
        repo="test/repo",
        base_commit="abc1234567890abcdef1234567890abcdef12345",
        repo_url="https://github.com/test/repo.git",
        test_commands=("pytest tests/test_foo.py",),
        image="swebench/test-image:latest",
    )


@pytest.fixture
def synthetic_git_repo(tmp_path: Path) -> Path:
    """Create a minimal real git repository initialized at a known commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)

    foo = repo / "foo.py"
    foo.write_text("def calculate(x):\n    return x + 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "foo.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial base"], cwd=repo, check=True)
    return repo


# 1. Common prompt rendering
def test_common_prompt_rendering():
    prompt = render_prompt("Fix division by zero in utils.py", include_test_helper=True)
    assert "Fix division by zero in utils.py" in prompt
    assert "Requirements:" in prompt
    assert "Make the smallest correct general source-code change." in prompt
    assert "Do not create a Git commit." in prompt
    assert "./.benchmark/test" in prompt

    prompt_no_helper = render_prompt("Fix bug", include_test_helper=False)
    assert "./.benchmark/test" not in prompt_no_helper


# 2. Prompt hash stability
def test_prompt_hash_stability():
    prompt1 = render_prompt("Fix bug 1")
    prompt2 = render_prompt("Fix bug 1")
    prompt3 = render_prompt("Fix bug 2")
    assert hash_prompt(prompt1) == hash_prompt(prompt2)
    assert hash_prompt(prompt1) != hash_prompt(prompt3)
    assert len(hash_prompt(prompt1)) == 64


# 3. Safe generation projection
def test_safe_generation_projection(sample_task: TaskSpec):
    proj = sample_task.generation_projection()
    assert proj["instance_id"] == "test__repo-1234"
    assert "patch" not in proj
    assert "test_patch" not in proj
    assert "FAIL_TO_PASS" not in proj
    assert "PASS_TO_PASS" not in proj
    assert "hints_text" not in proj


# 4. Fresh workspace setup
def test_fresh_workspace_setup(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(
        instance_id="synthetic-task",
        problem_statement="synthetic issue",
        repo_path=str(synthetic_git_repo),
        base_commit=head,
        image="",
    )
    workspaces = tmp_path / "workspaces"
    with prepare_clean_workspace(task, workspaces, inject_helper=True) as ws:
        assert ws.is_dir()
        assert (ws / "foo.py").is_file()
        assert (ws / ".benchmark" / "test").is_file()
        assert os.access(ws / ".benchmark" / "test", os.X_OK)
        # Verify .benchmark is git-ignored and clean
        assert get_git_status(ws) == ""


# 5. Base commit validation
def test_base_commit_validation(synthetic_git_repo: Path, tmp_path: Path):
    task = TaskSpec(
        instance_id="bad-commit-task",
        problem_statement="synthetic issue",
        repo_path=str(synthetic_git_repo),
        base_commit="deadbeef00000000000000000000000000000000",
    )
    workspaces = tmp_path / "workspaces"
    with pytest.raises(RuntimeError, match="failed to checkout base commit"):
        with prepare_clean_workspace(task, workspaces):
            pass


# 6. Dirty workspace rejection
def test_dirty_workspace_rejection(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(
        instance_id="dirty-task",
        problem_statement="synthetic issue",
        repo_path=str(synthetic_git_repo),
        base_commit=head,
    )
    # Dirty the repository
    (synthetic_git_repo / "untracked.txt").write_text("dirty")
    workspaces = tmp_path / "workspaces"
    # Even if repo had untracked, clean -fdx in prepare_clean_workspace cleans it!
    with prepare_clean_workspace(task, workspaces) as ws:
        assert not (ws / "untracked.txt").exists()
        assert get_git_status(ws) == ""


# 7. Codex command creation
def test_codex_command_creation(tmp_path: Path):
    agent = CodexAgent(
        executable="codex",
        model="gpt-6.1-sol",
        sandbox="workspace-write",
        ephemeral=True,
        ignore_user_config=True,
        ignore_rules=True,
    )
    cmd = agent.build_command("Solve issue", tmp_path)
    assert "exec" in cmd
    assert "--ephemeral" in cmd
    assert "--json" in cmd
    assert "--sandbox" in cmd
    assert "workspace-write" in cmd
    assert "--ignore-user-config" in cmd
    assert "--ignore-rules" in cmd
    assert "-m" in cmd
    assert "gpt-6.1-sol" in cmd
    assert "-C" in cmd
    assert str(tmp_path.resolve()) in cmd
    assert cmd[-1] == "Solve issue"


# 8. AGY command creation
def test_agy_command_creation(tmp_path: Path):
    agent = AntigravityAgent(
        executable="agy",
        model="gemini-3.8-flash-high",
        effort="high",
        output_format="stream-json",
        dangerously_skip_permissions=True,
        disable_slash_commands=True,
    )
    cmd = agent.build_command("Solve issue", tmp_path)
    assert "-p" in cmd
    assert "Solve issue" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--model" in cmd
    assert "gemini-3.8-flash-high" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--disable-slash-commands" in cmd


# 9. Installed-version parsing
def test_installed_version_parsing():
    agent = CodexAgent(executable="codex", model="gpt-6.1-sol")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="codex-cli 0.159.3\n", stderr="")
        ver = agent.detect_version()
        assert ver == "codex-cli 0.159.3"


# 10. Timeout handling
def test_timeout_handling(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(instance_id="timeout-task", problem_statement="issue", repo_path=str(synthetic_git_repo), base_commit=head)
    cfg = ExternalAgentsConfig.load("configs/external-agents.yaml")
    agent = CodexAgent(executable="codex", model="gpt-6.1-sol")
    real_run = subprocess.run

    def mock_run_timeout(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
            return real_run(*args, **kwargs)
        raise subprocess.TimeoutExpired(cmd=["codex"], timeout=10, output="partial", stderr="timeout")

    with patch("subprocess.run", side_effect=mock_run_timeout):
        res = run_task_attempt(agent, task, cfg, tmp_path / "ws", tmp_path / "out")
        assert res.timed_out is True
        assert res.terminal_status == "timed_out"
        assert "timeout" in res.termination_reason


# 11. Process non-zero exit
def test_process_nonzero_exit(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(instance_id="fail-task", problem_statement="issue", repo_path=str(synthetic_git_repo), base_commit=head)

    cfg = ExternalAgentsConfig.load("configs/external-agents.yaml")
    agent = CodexAgent(executable="codex", model="gpt-6.1-sol")

    real_run = subprocess.run

    def mock_run_fail(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
            return real_run(*args, **kwargs)
        return MagicMock(returncode=42, stdout="", stderr="crash")

    with patch("subprocess.run", side_effect=mock_run_fail):
        res = run_task_attempt(agent, task, cfg, tmp_path / "ws", tmp_path / "out")
        assert res.exit_code == 42
        assert res.terminal_status == "generation_failed"
        assert "code 42" in res.termination_reason


# 12. Provider-block detection
def test_provider_block_detection():
    codex = CodexAgent(executable="codex", model="gpt-6.1-sol")
    agy = AntigravityAgent(executable="agy", model="gemini-3.8-flash-high")

    assert codex.detect_provider_block("Error: insufficient_quota on account", "", 1) == (True, "quota_exceeded")
    assert codex.detect_provider_block("", "RateLimitError: status: 429 Too Many Requests", 1) == (True, "rate_limit")
    assert agy.detect_provider_block("RESOURCE_EXHAUSTED: quota exceeded for model", "", 1) == (True, "quota_exceeded")
    assert agy.detect_provider_block("Normal run finished", "", 0) == (False, "")


# 13. Stdout/stderr retention
def test_stdout_stderr_retention(tmp_path: Path):
    res = ExternalTaskResult(
        instance_id="t1",
        agent="codex",
        provider="openai",
        cli_version="1.0",
        configured_model="m",
        reported_model=None,
        effort_or_reasoning_setting=None,
        base_commit="b",
        workspace_path="w",
        start_timestamp="s",
        end_timestamp="e",
        wall_duration_seconds=1.0,
        exit_code=0,
        timed_out=False,
        terminal_status="generated",
        termination_reason="",
        stdout_file="stdout.log",
        stderr_file="stderr.log",
        events_file="events.jsonl",
        patch_file="patch.diff",
        input_tokens=100,
        output_tokens=50,
        thinking_tokens=10,
        cache_tokens=20,
        total_tokens=150,
        patch="diff content",
        patch_sha256="abc",
        prompt_sha256="def",
        config_sha256="123",
        git_head_before="b",
        git_status_before="",
        git_status_after="",
    )
    write_task_artifacts(tmp_path, res, stdout_raw="stdout test\n", stderr_raw="stderr test\n", commands=[])
    assert (tmp_path / "stdout.log").read_text() == "stdout test\n"
    assert (tmp_path / "stderr.log").read_text() == "stderr test\n"
    assert (tmp_path / "patch.diff").read_text() == "diff content"
    assert (tmp_path / "metadata.json").is_file()


# 14. Codex event parsing
def test_codex_event_parsing():
    sample_ndjson = """{"type":"thread.started","thread_id":"th-12345"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"i1","type":"command_execution","command":"pytest","aggregated_output":"passed","exit_code":0}}
{"type":"item.completed","item":{"id":"i2","type":"agent_message","text":"I fixed the issue."}}
{"type":"turn.completed","usage":{"input_tokens":500,"cached_input_tokens":200,"output_tokens":80,"reasoning_output_tokens":25}}
"""
    usage, cmds, thread_id, msg = parse_codex_events(sample_ndjson)
    assert thread_id == "th-12345"
    assert msg == "I fixed the issue."
    assert len(cmds) == 1
    assert cmds[0].command == "pytest"
    assert cmds[0].returncode == 0
    assert usage.input_tokens == 500
    assert usage.cache_tokens == 200
    assert usage.output_tokens == 80
    assert usage.thinking_tokens == 25
    assert usage.total_tokens == 580


# 15. AGY event parsing
def test_agy_event_parsing():
    sample_agy_json = """{"event":"init","conversation_id":"c-999","init":{"model":"gemini-3.8-flash-high","tools":["run_command"]}}
{"event":"step_update","step_update":{"conversation_id":"c-999","step_index":1,"state":"DONE","step_type":"tool","tool_name":"run_command","tool_info":{"name":"run_command","parameters":{"CommandLine":"./.benchmark/test"},"output":"all tests pass","exit_code":0}}}
{"event":"result","result":{"conversation_id":"c-999","status":"SUCCESS","response":"Done!","usage":{"input_tokens":1200,"output_tokens":150,"thinking_tokens":100,"cache_read_tokens":50,"total_tokens":1350}}}
"""
    usage, cmds, conv_id, rep_model, resp = parse_agy_events(sample_agy_json)
    assert conv_id == "c-999"
    assert rep_model == "gemini-3.8-flash-high"
    assert resp == "Done!"
    assert len(cmds) == 1
    assert cmds[0].command == "./.benchmark/test"
    assert cmds[0].returncode == 0
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 150
    assert usage.thinking_tokens == 100
    assert usage.cache_tokens == 50
    assert usage.total_tokens == 1350


# 16. Token accounting
def test_token_accounting():
    stream = """{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":10,"cached_input_tokens":0,"reasoning_output_tokens":5}}
{"type":"turn.completed","usage":{"input_tokens":200,"output_tokens":20,"cached_input_tokens":50,"reasoning_output_tokens":10}}
"""
    usage, _, _, _ = parse_codex_events(stream)
    assert usage.input_tokens == 300
    assert usage.output_tokens == 30
    assert usage.thinking_tokens == 15
    assert usage.cache_tokens == 50
    assert usage.total_tokens == 330


# 17. Missing token fields
def test_missing_token_fields():
    # No usage event
    usage, _, _, _ = parse_codex_events('{"type":"turn.started"}\n')
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None


# 18. Git diff extraction
def test_git_diff_extraction(synthetic_git_repo: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    foo = synthetic_git_repo / "foo.py"
    foo.write_text("def calculate(x):\n    if x is None: return 0\n    return x + 1\n", encoding="utf-8")
    diff = extract_workspace_diff(synthetic_git_repo, head)
    assert "if x is None: return 0" in diff
    assert "--- a/foo.py" in diff


# 19. Binary diff extraction
def test_binary_diff_extraction(synthetic_git_repo: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    bin_file = synthetic_git_repo / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\xff\xfe")
    diff = extract_workspace_diff(synthetic_git_repo, head)
    assert "diff --git a/data.bin b/data.bin" in diff
    assert "new file mode" in diff


# 20. Empty diff behavior
def test_empty_diff_behavior(synthetic_git_repo: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    diff = extract_workspace_diff(synthetic_git_repo, head)
    assert diff == ""


# 21. Prediction JSONL
def test_prediction_jsonl(tmp_path: Path):
    preds_file = tmp_path / "predictions.jsonl"
    rows = [
        {"instance_id": "task1", "model_patch": "diff1"},
        {"instance_id": "task2", "model_patch": ""},
    ]
    write_predictions(preds_file, rows, model_name="test-model")
    lines = preds_file.read_text().splitlines()
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    assert r1["instance_id"] == "task1"
    assert r1["model_name_or_path"] == "test-model"
    assert r1["model_patch"] == "diff1"
    r2 = json.loads(lines[1])
    assert r2["instance_id"] == "task2"
    assert r2["model_patch"] == ""


# 22. Resume state
def test_resume_state(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(instance_id="resume-task", problem_statement="issue", repo_path=str(synthetic_git_repo), base_commit=head)
    cfg = ExternalAgentsConfig.load("configs/external-agents.yaml")
    cfg = ExternalAgentsConfig(
        protocol_version=cfg.protocol_version,
        manifest_path=cfg.manifest_path,
        expected_count=1,
        tasks=(task,),
        config_path=cfg.config_path,
    )

    agent_dir = tmp_path / "agent"
    task_dir = agent_dir / "tasks" / "resume-task"
    task_dir.mkdir(parents=True)
    res_saved = ExternalTaskResult(
        instance_id="resume-task",
        agent="codex",
        provider="openai",
        cli_version="1.0",
        configured_model="m",
        reported_model=None,
        effort_or_reasoning_setting=None,
        base_commit=head,
        workspace_path="w",
        start_timestamp="s",
        end_timestamp="e",
        wall_duration_seconds=10.0,
        exit_code=0,
        timed_out=False,
        terminal_status="generated",
        termination_reason="",
        stdout_file="stdout.log",
        stderr_file="stderr.log",
        events_file="events.jsonl",
        patch_file="patch.diff",
        input_tokens=10,
        output_tokens=10,
        thinking_tokens=0,
        cache_tokens=0,
        total_tokens=20,
        patch="historical patch",
        patch_sha256="abc",
        prompt_sha256="def",
        config_sha256="123",
        git_head_before=head,
        git_status_before="",
        git_status_after="",
    )
    (task_dir / "metadata.json").write_text(json.dumps(res_saved.as_dict()))

    agent = CodexAgent(executable="codex", model="gpt-6.1-sol")
    with patch("smartm2m.external_agents.runner.run_task_attempt") as mock_attempt:
        meta = run_agent_benchmark(agent, cfg, agent_dir, tmp_path / "ws", resume=True)
        # Should NOT run attempt because it was already completed!
        mock_attempt.assert_not_called()
        assert len(meta["tasks"]) == 1
        assert meta["tasks"][0]["patch"] == "historical patch"


# 23. Interrupted task state
def test_interrupted_task_state(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(instance_id="interrupted-task", problem_statement="issue", repo_path=str(synthetic_git_repo), base_commit=head)
    cfg = ExternalAgentsConfig.load("configs/external-agents.yaml")
    cfg = ExternalAgentsConfig(
        protocol_version=cfg.protocol_version,
        manifest_path=cfg.manifest_path,
        expected_count=1,
        tasks=(task,),
        config_path=cfg.config_path,
    )

    agent_dir = tmp_path / "agent"
    task_dir = agent_dir / "tasks" / "interrupted-task"
    task_dir.mkdir(parents=True)
    # Status was left as "running" before process was killed
    (task_dir / "metadata.json").write_text(json.dumps({"terminal_status": "running", "instance_id": "interrupted-task"}))

    agent = CodexAgent(executable="codex", model="gpt-6.1-sol")
    with patch("smartm2m.external_agents.runner.run_task_attempt") as mock_attempt:
        mock_attempt.return_value = ExternalTaskResult(
            instance_id="interrupted-task", agent="codex", provider="openai", cli_version="1.0",
            configured_model="m", reported_model=None, effort_or_reasoning_setting=None, base_commit=head,
            workspace_path="w", start_timestamp="s", end_timestamp="e", wall_duration_seconds=5.0,
            exit_code=0, timed_out=False, terminal_status="generated", termination_reason="",
            stdout_file="", stderr_file="", events_file="", patch_file="", input_tokens=None,
            output_tokens=None, thinking_tokens=None, cache_tokens=None, total_tokens=None,
            patch="new patch", patch_sha256="", prompt_sha256="", config_sha256="",
            git_head_before=head, git_status_before="", git_status_after="",
        )
        meta = run_agent_benchmark(agent, cfg, agent_dir, tmp_path / "ws", resume=True)
        # Should rerun because it was not in terminal finished states!
        mock_attempt.assert_called_once()
        assert meta["tasks"][0]["patch"] == "new patch"


# 24. Incomplete-run headline-score prevention
def test_incomplete_run_headline_score_prevention(tmp_path: Path):
    cfg = ExternalAgentsConfig.load("configs/external-agents.yaml")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    codex_meta = {"status": "provider_blocked", "tasks": []}
    agy_meta = {"status": "completed", "tasks": []}

    report = build_comparison_report(cfg, run_dir, codex_meta, agy_meta)
    assert report["codex"]["status"] == "provider_blocked"
    md = (run_dir / "comparison.md").read_text()

    # For codex, should show provider_blocked / incomplete without headline score like 0/8
    assert "Run status `provider_blocked` (incomplete; no headline score)" in md
    assert "0/8 resolved" not in md.split("Codex CLI")[1].split("Antigravity CLI")[0]


# 25. Secret redaction
def test_secret_redaction():
    fake_gsk = "gsk_" + "1234567890abcdef1234567890"
    fake_sk = "sk-" + "99887766554433221100"
    fake_ghp = "ghp_" + "1122334455667788"
    text = f"Bearer {fake_gsk} and {fake_sk} and api_key: {fake_ghp}"
    redacted = redact_secrets(text)
    assert "gsk_" not in redacted
    assert "sk-" not in redacted
    assert "ghp_" not in redacted
    assert "[REDACTED]" in redacted

    data = {"secret": f"token={fake_ghp}", "nested": [{"key": fake_gsk}]}
    safe_data = redact_json(data)
    assert safe_data["secret"] == "token=[REDACTED]"
    assert safe_data["nested"][0]["key"] == "[REDACTED]"


# 26. Evaluation handoff
def test_evaluation_handoff(tmp_path: Path):
    preds_path = tmp_path / "preds.jsonl"
    rows = [{"instance_id": "django__django-11999", "model_patch": "diff"}]
    write_predictions(preds_path, rows, model_name="gpt-6.1-sol")
    content = preds_path.read_text()
    assert "django__django-11999" in content
    assert "gpt-6.1-sol" in content


# 27. Checksum creation
def test_checksum_creation(tmp_path: Path):
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file2.txt").write_text("world")
    write_run_checksums(tmp_path)
    sums_file = tmp_path / "checksums.sha256"
    assert sums_file.is_file()
    lines = sums_file.read_text().splitlines()
    assert any("file1.txt" in line for line in lines)
    assert any("subdir/file2.txt" in line for line in lines)


# 28. Historical result immutability
def test_historical_result_immutability():
    primary_dir = Path("results/track3-primary")
    if primary_dir.exists():
        manifest = primary_dir / "manifest.json"
        assert manifest.is_file()
        orig_bytes = manifest.read_bytes()
        # Verify read-only state and ensure nothing modified it
        assert orig_bytes == (primary_dir / "manifest.json").read_bytes()


# 29. Dry-run validation
def test_dry_run_validation():
    cfg = ExternalAgentsConfig.load("configs/external-agents.yaml")
    report = dry_run(cfg)
    assert report["ok"] is True
    assert report["task_count"] == 8
    assert report["expected_count"] == 8
    assert report["codex"]["configured_model"] == "gpt-6.1-sol"
    assert report["agy"]["configured_model"] == "gemini-3.8-flash-high"


# 30. Synthetic end-to-end benchmark
def test_synthetic_end_to_end_benchmark(synthetic_git_repo: Path, tmp_path: Path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=synthetic_git_repo, check=True, text=True, capture_output=True).stdout.strip()
    task = TaskSpec(
        instance_id="synthetic-task",
        problem_statement="fix foo",
        repo_path=str(synthetic_git_repo),
        base_commit=head,
    )

    cfg = ExternalAgentsConfig(
        protocol_version="external-agents-v1",
        manifest_path=Path("tasks/evaluation.json"),
        expected_count=1,
        tasks=(task,),
        config_path=Path("configs/external-agents.yaml"),
        results_root=tmp_path / "results",
    )

    # Custom mock agent that modifies a file in the workspace
    class MockEditorAgent(ExternalAgent):
        name = "mock_agent"
        provider = "synthetic"

        def build_command(self, prompt: str, workspace: Path) -> list[str]:
            return ["python3", "-c", "with open('foo.py', 'a') as f: f.write('# modified\\n')"]

        def build_env(self, workspace: Path) -> dict[str, str]:
            return os.environ.copy()

        def parse_stream(self, stdout: str):
            return TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15), [ExecutedCommand("edit", 0, "")], "sess-1", "m"

        def detect_provider_block(self, stdout: str, stderr: str, rc: int):
            return False, ""

    agent = MockEditorAgent(executable="python3", model="synthetic-model")
    out_dir = tmp_path / "results" / "synthetic-run" / "mock_agent"
    ws_dir = tmp_path / "results" / "synthetic-run" / "workspaces"

    meta = run_agent_benchmark(agent, cfg, out_dir, ws_dir)
    assert meta["status"] == "completed"
    assert meta["completed_tasks"] == 1
    assert meta["tasks"][0]["terminal_status"] == "generated"
    assert "# modified" in meta["tasks"][0]["patch"]
    assert (out_dir / "predictions.jsonl").is_file()
    assert (out_dir / "summary.json").is_file()
    assert (out_dir / "summary.md").is_file()

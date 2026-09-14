import os
import subprocess
from pathlib import Path

import pytest

from smartm2m.config import TaskSpec
from smartm2m.tools import ToolError, ToolRunner, validate_test_command
from smartm2m.validation import validate_clean_replay


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "maths.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (repo / "tests" / "check.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    return repo


def test_tool_applies_patch_and_replays_it_on_clean_base(tmp_path: Path):
    repo = make_repo(tmp_path)
    command = 'python -c "from src.maths import add; assert add(2, 3) == 5"'
    task = TaskSpec("synthetic__maths-1", "Fix addition.", repo_path=str(repo), test_commands=(command,))
    runner = ToolRunner(repo, task, command_timeout=20)
    patch = """diff --git a/src/maths.py b/src/maths.py
--- a/src/maths.py
+++ b/src/maths.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
    result = runner.apply_patch(patch)
    assert result.ok
    assert not runner.submit_patch().ok
    assert runner.run_tests().ok
    assert runner.submit_patch().ok
    validation = validate_clean_replay(repo, command, timeout_seconds=20)
    assert validation.status == "passed"
    assert validation.patch_sha256


def test_edit_boundary_rejects_tests_and_escape(tmp_path: Path):
    repo = make_repo(tmp_path)
    task = TaskSpec("x", "x", repo_path=str(repo))
    runner = ToolRunner(repo, task)
    with pytest.raises(ToolError):
        runner.apply_patch("""--- a/tests/check.py
+++ b/tests/check.py
@@ -0,0 +1 @@
+bad
""")
    with pytest.raises(ToolError):
        runner.read_file("../outside")


def test_targeted_test_command_boundary_rejects_shell_composition():
    validate_test_command("python -m pytest tests/test_one.py -q")
    with pytest.raises(ToolError):
        validate_test_command("pytest tests/test_one.py; rm -rf .")
    with pytest.raises(ToolError):
        validate_test_command("curl https://example.invalid/payload")
    with pytest.raises(ToolError):
        validate_test_command("python -c \"import os; os.remove('source.py')\"")
    with pytest.raises(ToolError):
        validate_test_command("pytest tests/test_one.py \"$(touch compromised)\"")
    with pytest.raises(ToolError):
        validate_test_command("pytest tests/test_one.py \"`touch compromised`\"")


def test_rollback_restores_new_source_files_without_double_applying(tmp_path: Path):
    repo = make_repo(tmp_path)
    task = TaskSpec("synthetic__new-file-1", "Add a source module.", repo_path=str(repo))
    runner = ToolRunner(repo, task)
    first = """diff --git a/src/new_module.py b/src/new_module.py
new file mode 100644
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1 @@
+VALUE = 1
"""
    second = """diff --git a/src/other_module.py b/src/other_module.py
new file mode 100644
--- /dev/null
+++ b/src/other_module.py
@@ -0,0 +1 @@
+VALUE = 2
"""
    assert runner.apply_patch(first).ok
    assert runner.apply_patch(second).ok
    assert runner.rollback().ok
    assert (repo / "src" / "new_module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (repo / "src" / "other_module.py").exists()


def test_container_test_path_records_infrastructure_failure_without_docker(tmp_path: Path):
    repo = make_repo(tmp_path)
    task = TaskSpec(
        "synthetic__container-1",
        "Run in the task image.",
        repo_path=str(repo),
        image="docker.io/example/not-installed:latest",
        test_commands=("python -m pytest -q",),
    )
    result = ToolRunner(repo, task).run_tests()
    assert not result.ok
    assert result.metadata["failure_class"] == "infra_failure"


def test_command_history_preserves_stdout_and_stderr(tmp_path: Path):
    repo = make_repo(tmp_path)
    task = TaskSpec(
        "synthetic__streams-1",
        "Capture both process streams.",
        repo_path=str(repo),
        test_commands=(
            "python -c \"import sys; print('stdout'); print('stderr', file=sys.stderr); sys.exit(1)\"",
        ),
    )
    runner = ToolRunner(repo, task, command_timeout=20)

    result = runner.run_tests()

    assert not result.ok
    record = runner.command_records()[0]
    assert "stdout" in record["stdout"]
    assert "stderr" in record["stderr"]


def test_container_daemon_socket_error_is_infrastructure_failure(monkeypatch, tmp_path: Path):
    repo = make_repo(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "echo 'docker: permission denied while trying to connect to the Docker daemon socket' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")
    task = TaskSpec(
        "synthetic__daemon-1",
        "Run in the task image.",
        repo_path=str(repo),
        image="docker.io/example/not-installed:latest",
        test_commands=("python -m pytest -q",),
    )

    result = ToolRunner(repo, task).run_tests()

    assert not result.ok
    assert result.metadata["failure_class"] == "infra_failure"

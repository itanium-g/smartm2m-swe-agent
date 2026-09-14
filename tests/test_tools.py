import subprocess
from pathlib import Path

import pytest

from smartm2m.config import TaskSpec
from smartm2m.tools import ToolError, ToolRunner
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

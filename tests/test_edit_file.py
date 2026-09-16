import subprocess
from pathlib import Path

import pytest

from smartm2m.config import TaskSpec
from smartm2m.tools import ToolError, ToolRunner


def make_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "sample.py").write_text(
        "def compute(x):\n"
        "    result = x * 2\n"
        "    return result\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_sample.py").write_text("# test file\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def test_edit_file_replaces_exact_unique_text(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix compute", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    res = runner.edit_file(
        "src/sample.py",
        old_text="    result = x * 2",
        new_text="    result = x * 3",
    )
    assert res.ok
    assert "Successfully edited" in res.content

    content = (repo / "src" / "sample.py").read_text(encoding="utf-8")
    assert "result = x * 3" in content
    assert "result = x * 2" not in content

    diff = runner.get_diff().content
    assert "+    result = x * 3" in diff
    assert "-    result = x * 2" in diff


def test_edit_file_rejects_non_unique_matches(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    # create a file with duplicated lines
    (repo / "src" / "multi.py").write_text("item = 1\nitem = 1\n", encoding="utf-8")
    task = TaskSpec("task1", "Fix multi", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    with pytest.raises(ToolError, match="matched 2 occurrences"):
        runner.edit_file("src/multi.py", old_text="item = 1", new_text="item = 2")


def test_edit_file_rejects_missing_text(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix compute", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    with pytest.raises(ToolError, match="old_text not found"):
        runner.edit_file("src/sample.py", old_text="def non_existent():", new_text="def foo():")


def test_edit_file_rejects_test_files(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix test", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    with pytest.raises(ToolError, match="test files are outside the generation edit boundary"):
        runner.edit_file("tests/test_sample.py", old_text="# test file", new_text="# new test")


def test_edit_file_rollback_restores_original_file(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix compute", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    runner.edit_file(
        "src/sample.py",
        old_text="    result = x * 2",
        new_text="    result = x * 99",
    )
    assert "result = x * 99" in (repo / "src" / "sample.py").read_text()

    rollback_res = runner.rollback()
    assert rollback_res.ok
    assert "result = x * 2" in (repo / "src" / "sample.py").read_text()
    assert runner.get_diff().content == ""


def test_edit_file_fuzzy_indentation_match(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix compute", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    # Line 1 has no indent, while file has 4 spaces
    res = runner.edit_file(
        "src/sample.py",
        old_text="result = x * 2\n    return result",
        new_text="result = x * 10\n    return result",
    )
    assert res.ok
    content = (repo / "src" / "sample.py").read_text()
    assert "    result = x * 10" in content


def test_edit_file_strips_line_number_prefixes(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix compute", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    res = runner.edit_file(
        "src/sample.py",
        old_text="2:     result = x * 2\n3:     return result",
        new_text="2:     result = x * 10\n3:     return result",
    )
    assert res.ok
    content = (repo / "src" / "sample.py").read_text()
    assert "    result = x * 10" in content


def test_edit_file_strips_line_numbers_from_old_when_new_has_none(tmp_path: Path):
    repo = make_test_repo(tmp_path)
    task = TaskSpec("task1", "Fix compute", repo_path=str(repo))
    runner = ToolRunner(repo, task)

    res = runner.edit_file(
        "src/sample.py",
        old_text="2:     result = x * 2",
        new_text="    result = x * 42",
    )
    assert res.ok
    content = (repo / "src" / "sample.py").read_text()
    assert "    result = x * 42" in content



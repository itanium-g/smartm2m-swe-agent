import subprocess
from pathlib import Path

import pytest

from smartm2m.config import ConfigError, TaskSpec
from smartm2m.task import generation_payload, prepared_workspace


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "task@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "task"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "later"], cwd=repo, check=True, capture_output=True)
    (repo / "untracked.txt").write_text("discard me\n", encoding="utf-8")
    return repo, base


def test_prepared_workspace_resets_copy_to_manifest_base(tmp_path: Path):
    repo, base = _repo(tmp_path)
    task = TaskSpec("synthetic__base-1", "Use the base.", repo_path=str(repo), base_commit=base)

    with prepared_workspace(task, tmp_path / "workspaces") as workspace:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
        assert head == base
        assert (workspace / "value.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        assert not (workspace / "untracked.txt").exists()


def test_generation_payload_allows_issue_prose_about_patches():
    task = TaskSpec("synthetic__payload-1", "Apply a patch to fix the regression.")
    assert generation_payload(task)["problem_statement"].startswith("Apply a patch")


def test_uppercase_evaluator_fields_are_rejected():
    with pytest.raises(ConfigError):
        TaskSpec.from_mapping({
            "instance_id": "synthetic__leak-1",
            "problem_statement": "x",
            "FAIL_TO_PASS": ["secret"],
        })

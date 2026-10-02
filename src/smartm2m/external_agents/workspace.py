"""Clean workspace preparation, git diff extraction, and test helper injection."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config import TaskSpec


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def get_git_head(root: Path) -> str:
    """Return the current HEAD commit hash."""
    res = _run_git(root, ["rev-parse", "HEAD"])
    return res.stdout.strip() if res.returncode == 0 else ""


def get_git_status(root: Path) -> str:
    """Return git status --porcelain."""
    res = _run_git(root, ["status", "--porcelain"])
    return res.stdout.strip() if res.returncode == 0 else ""


def inject_test_helper(root: Path, task: TaskSpec) -> None:
    """Inject safe .benchmark/test runner into task workspace and exclude from git."""
    benchmark_dir = root / ".benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    test_script = benchmark_dir / "test"

    default_cmd = task.test_commands[0] if task.test_commands else "python -m pytest -q"
    image = task.image or ""

    script_content = f"""#!/usr/bin/env bash
set -euo pipefail

# Bounded repository test runner helper for external benchmark agents.
# Executes tests inside the official SWE-bench task container when available.
DEFAULT_CMD={default_cmd!r}
IMAGE={image!r}

if [ "$#" -eq 0 ]; then
    CMD="$DEFAULT_CMD"
else
    CMD="$*"
fi

if [ -n "$IMAGE" ] && command -v docker >/dev/null 2>&1; then
    exec docker run --rm --init \\
        --volume "$PWD:/testbed" \\
        --workdir /testbed \\
        --env CI=1 \\
        --env PAGER=cat \\
        --env PYTHONDONTWRITEBYTECODE=1 \\
        --env PYTHONIOENCODING=utf-8 \\
        --env LANG=C.UTF-8 \\
        --env LC_ALL=C.UTF-8 \\
        "$IMAGE" bash -lc "$CMD"
else
    exec bash -c "$CMD"
fi
"""
    test_script.write_text(script_content, encoding="utf-8")
    test_script.chmod(0o755)

    # Exclude .benchmark and temporary test artifacts from git so git status and git diff remain pristine
    exclude_file = root / ".git" / "info" / "exclude"
    exclude_file.parent.mkdir(parents=True, exist_ok=True)
    current_exclude = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
    patterns = [".benchmark/", "__pycache__/", "*.pyc", "*.pyo", "*.pyd", ".pytest_cache/", ".ruff_cache/"]
    missing_patterns = [p for p in patterns if p not in current_exclude]
    if missing_patterns:
        exclude_file.write_text(f"{current_exclude}\n" + "\n".join(missing_patterns) + "\n", encoding="utf-8")


def extract_workspace_diff(root: Path, base_commit: str) -> str:
    """Extract authoritative binary git diff against base_commit.

    Stages intent-to-add for untracked files (excluding .benchmark and caches)
    so new files are captured in the diff, then computes git diff against base_commit.
    """
    _run_git(root, ["add", "-N", "."])
    diff_cmd = [
        "diff",
        "--binary",
        "--no-ext-diff",
        base_commit,
        "--",
        ".",
        ":(exclude)*.pyc",
        ":(exclude)__pycache__",
        ":(exclude).benchmark",
        ":(exclude).pytest_cache",
    ]
    res = _run_git(root, diff_cmd)
    if res.returncode not in (0, 1):
        raise RuntimeError(f"git diff failed ({res.returncode}): {res.stderr}")
    return res.stdout


@contextmanager
def prepare_clean_workspace(
    task: TaskSpec,
    parent_dir: str | Path,
    *,
    inject_helper: bool = True,
    preserve_workspace: bool = False,
) -> Iterator[Path]:
    """Materialize a clean task workspace pinned to base_commit."""
    parent = Path(parent_dir).resolve()
    parent.mkdir(parents=True, exist_ok=True)

    dest = Path(tempfile.mkdtemp(prefix=f"{task.instance_id.replace('/', '__')}-", dir=parent))
    try:
        # Clone or copy repository
        if task.repo_path and Path(task.repo_path).expanduser().is_dir():
            shutil.copytree(Path(task.repo_path).expanduser().resolve(), dest, dirs_exist_ok=True, symlinks=True)
        elif task.repo_url:
            clone_res = subprocess.run(
                ["git", "clone", "--no-tags", task.repo_url, str(dest)],
                text=True,
                capture_output=True,
                check=False,
            )
            if clone_res.returncode != 0:
                raise RuntimeError(f"git clone failed for {task.repo_url}: {clone_res.stderr.strip()}")
        else:
            raise RuntimeError(f"task {task.instance_id} has neither repo_path nor repo_url")

        # Checkout and verify base commit
        if task.base_commit:
            _run_git(dest, ["reset", "--hard"])
            _run_git(dest, ["clean", "-fdx"])
            checkout_res = _run_git(dest, ["checkout", "--detach", task.base_commit])
            if checkout_res.returncode != 0:
                raise RuntimeError(
                    f"failed to checkout base commit {task.base_commit} for {task.instance_id}: {checkout_res.stderr.strip()}"
                )
            _run_git(dest, ["reset", "--hard", task.base_commit])
            _run_git(dest, ["clean", "-fdx"])

            # Verify HEAD exactly matches base_commit
            actual_head = get_git_head(dest)
            if not actual_head.startswith(task.base_commit) and not task.base_commit.startswith(actual_head):
                raise RuntimeError(
                    f"HEAD verification failed: expected {task.base_commit}, observed {actual_head}"
                )

        # Verify working tree is clean before injecting helper
        initial_status = get_git_status(dest)
        if initial_status:
            raise RuntimeError(f"workspace is dirty before agent execution:\n{initial_status}")

        if inject_helper:
            inject_test_helper(dest, task)
            status_after_helper = get_git_status(dest)
            if status_after_helper:
                raise RuntimeError(f"test helper leaked into git status:\n{status_after_helper}")

        yield dest
    finally:
        if not preserve_workspace:
            shutil.rmtree(dest, ignore_errors=True)

"""Manifest loading and disposable task workspace preparation."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import ConfigError, TaskSpec, load_data


def load_manifest(path: str | Path) -> list[TaskSpec]:
    source = Path(path)
    raw: Any = load_data(source)
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
        values = raw["tasks"]
    else:
        raise ConfigError(f"{source} must contain a top-level tasks array")
    return [TaskSpec.from_mapping(dict(item)) for item in values]


def _git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def _run_setup(root: Path, commands: tuple[str, ...], image: str = "") -> None:
    for command in commands:
        if image:
            if shutil.which("docker") is None:
                raise RuntimeError(f"container runtime unavailable for task image {image}")
            if image.startswith("-") or any(char.isspace() for char in image):
                raise RuntimeError("task image is not a valid simple image reference")
            argv = [
                "docker", "run", "--rm", "--init",
                "--volume", f"{root}:/testbed", "--workdir", "/testbed",
                "--env", "CI=1", "--env", "PAGER=cat", image, "bash", "-lc", command,
            ]
            result = subprocess.run(
                argv,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        else:
            result = subprocess.run(
                command,
                cwd=root,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "CI": "1", "PAGER": "cat"},
                check=False,
            )
        if result.returncode != 0:
            raise RuntimeError(f"setup command failed ({result.returncode}): {command}\n{result.stdout[-4000:]}")


def _checkout_clean_base(root: Path, base_commit: str) -> None:
    """Reset the disposable copy before detaching it at the requested commit."""
    reset = _git(root, ["reset", "--hard"])
    if reset.returncode != 0:
        raise RuntimeError(reset.stderr.strip() or "task source is not a usable git repository")
    cleaned = _git(root, ["clean", "-fdx"])
    if cleaned.returncode != 0:
        raise RuntimeError(cleaned.stderr.strip() or "could not clean the task workspace")
    checked = _git(root, ["checkout", "--detach", base_commit])
    if checked.returncode != 0:
        raise RuntimeError(checked.stderr.strip() or f"could not checkout base commit {base_commit}")
    reset = _git(root, ["reset", "--hard", base_commit])
    if reset.returncode != 0:
        raise RuntimeError(reset.stderr.strip() or f"could not reset to base commit {base_commit}")
    cleaned = _git(root, ["clean", "-fdx"])
    if cleaned.returncode != 0:
        raise RuntimeError(cleaned.stderr.strip() or "could not clean the checked-out task workspace")


@contextmanager
def prepared_workspace(task: TaskSpec, parent: str | Path) -> Iterator[Path]:
    """Materialize a clean task workspace and remove it on exit.

    A manifest may point at an already downloaded repository (`repo_path`) or
    provide a clone URL. Network cloning is explicit in the manifest and is
    never initiated during preflight.
    """
    root = Path(parent).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=f"{task.instance_id.replace('/', '_')}-", dir=root))
    try:
        if task.repo_path:
            source = Path(task.repo_path).expanduser().resolve()
            if not source.is_dir():
                raise RuntimeError(f"repo_path does not exist: {source}")
            shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
        elif task.repo_url:
            cloned = subprocess.run(
                ["git", "clone", "--no-tags", task.repo_url, str(destination)],
                text=True,
                capture_output=True,
                check=False,
            )
            if cloned.returncode != 0:
                raise RuntimeError(cloned.stderr.strip() or "git clone failed")
        elif task.repo:
            raise RuntimeError(f"task {task.instance_id} needs repo_url or repo_path for local execution")
        else:
            raise RuntimeError(f"task {task.instance_id} has no repository source")

        if task.base_commit:
            _checkout_clean_base(destination, task.base_commit)
        _run_setup(destination, task.setup_commands, task.image)
        yield destination
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def generation_payload(task: TaskSpec) -> dict[str, Any]:
    """Build the exact safe input projection and assert hidden-field absence.

    The check is key-based: ordinary issue prose is allowed to mention a patch
    or test names without being mistaken for leaked evaluator data.
    """
    payload = task.generation_projection()
    forbidden = {"patch", "test_patch", "hints_text", "fail_to_pass", "pass_to_pass", "FAIL_TO_PASS", "PASS_TO_PASS"}

    def check_keys(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key) in forbidden:
                    raise ConfigError(f"forbidden evaluator field appeared in generation payload: {key}")
                check_keys(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                check_keys(nested)

    check_keys(payload)
    return payload

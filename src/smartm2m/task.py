"""Manifest loading and disposable task workspace preparation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import ConfigError, TaskSpec


def load_manifest(path: str | Path) -> list[TaskSpec]:
    source = Path(path)
    raw: Any
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConfigError(f"{source} requires PyYAML because it is not JSON-compatible") from exc
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
        values = raw["tasks"]
    else:
        raise ConfigError(f"{source} must contain a top-level tasks array")
    return [TaskSpec.from_mapping(dict(item)) for item in values]


def _git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def _run_setup(root: Path, commands: tuple[str, ...]) -> None:
    for command in commands:
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
            checked = _git(destination, ["checkout", "--detach", task.base_commit])
            if checked.returncode != 0:
                raise RuntimeError(checked.stderr.strip() or f"could not checkout base commit {task.base_commit}")
        _run_setup(destination, task.setup_commands)
        yield destination
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def generation_payload(task: TaskSpec) -> dict[str, Any]:
    """Build the exact safe input projection and assert hidden-field absence."""
    payload = task.generation_projection()
    encoded = json.dumps(payload, sort_keys=True)
    for forbidden in ("patch", "test_patch", "hints_text", "FAIL_TO_PASS", "PASS_TO_PASS"):
        if forbidden in encoded:
            raise ConfigError(f"forbidden evaluator token appeared in generation payload: {forbidden}")
    return payload

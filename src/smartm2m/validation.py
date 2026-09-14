"""Patch capture and clean-base visible-test validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .tools import ToolError, _docker_argv, _git_patch, validate_test_command


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_value(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise ToolError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


@dataclass
class ValidationResult:
    status: str
    patch_sha256: str
    command_sha256: str
    base_commit: str
    command: str
    returncode: int | None
    timed_out: bool
    duration_seconds: float
    output: str
    reason: str = ""
    setup_commands: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_patch(root: str | Path) -> str:
    return _git_patch(Path(root).resolve())


def _fresh_base(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "archive", "HEAD"], cwd=root, capture_output=True, check=False)
    if archive.returncode != 0:
        raise ToolError(archive.stderr.decode(errors="replace") or "could not archive clean base")
    extracted = subprocess.run(["tar", "-x", "-C", str(destination)], input=archive.stdout, capture_output=True, check=False)
    if extracted.returncode != 0:
        raise ToolError(extracted.stderr.decode(errors="replace") or "could not extract clean base")


def validate_clean_replay(
    root: str | Path,
    command: str,
    *,
    timeout_seconds: int = 120,
    max_output_chars: int = 20000,
    setup_commands: tuple[str, ...] = (),
    container_image: str = "",
) -> ValidationResult:
    workspace = Path(root).resolve()
    patch = capture_patch(workspace)
    patch_hash = sha256_text(patch)
    command_hash = sha256_text("\n".join((*setup_commands, command)))
    base = git_value(workspace, "rev-parse", "HEAD")
    if not patch:
        return ValidationResult("invalid", patch_hash, command_hash, base, command, None, False, 0.0, "", "empty patch")
    try:
        validate_test_command(command, declared=True)
    except ToolError as exc:
        return ValidationResult("invalid", patch_hash, command_hash, base, command, None, False, 0.0, str(exc), str(exc), setup_commands)
    if container_image and shutil.which("docker") is None:
        return ValidationResult(
            "unavailable", patch_hash, command_hash, base, command, None, False, 0.0,
            f"docker is not installed for {container_image}", "container runtime unavailable", setup_commands,
        )
    with tempfile.TemporaryDirectory(prefix="smartm2m-validate-") as temp:
        clean = Path(temp)
        _fresh_base(workspace, clean)
        applied = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=clean,
            input=patch,
            text=True,
            capture_output=True,
            check=False,
        )
        if applied.returncode != 0:
            return ValidationResult(
                "invalid", patch_hash, command_hash, base, command, applied.returncode, False, 0.0,
                applied.stderr.strip(), "patch could not be replayed on clean base",
            )
        started = time.monotonic()
        setup_output: list[str] = []
        for setup in setup_commands:
            try:
                if container_image:
                    prepared_argv: list[str] | str = _docker_argv(clean, container_image, setup)
                    prepared_shell = False
                else:
                    prepared_argv = setup
                    prepared_shell = True
                prepared = subprocess.run(
                    prepared_argv,
                    cwd=clean,
                    shell=prepared_shell,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    env={**os.environ, "CI": "1", "PAGER": "cat"},
                    check=False,
                )
                setup_output.append(f"$ {setup}\n{prepared.stdout or ''}")
            except subprocess.TimeoutExpired as exc:
                setup_output.append(
                    f"$ {setup}\n{(exc.stdout or '') if isinstance(exc.stdout, str) else ''}"
                    f"\n[timeout after {timeout_seconds}s]"
                )
                return ValidationResult(
                    "failed",
                    patch_hash,
                    command_hash,
                    base,
                    command,
                    None,
                    True,
                    time.monotonic() - started,
                    "\n".join(setup_output)[-max_output_chars:],
                    "setup command timed out",
                    setup_commands,
                )
            if prepared.returncode != 0:
                return ValidationResult(
                    "failed",
                    patch_hash,
                    command_hash,
                    base,
                    command,
                    prepared.returncode,
                    False,
                    time.monotonic() - started,
                    "\n".join(setup_output)[-max_output_chars:],
                    "setup command failed",
                    setup_commands,
                )
        timed_out = False
        try:
            if container_image:
                test_argv: list[str] | str = _docker_argv(clean, container_image, command)
                test_shell = False
            else:
                test_argv = command
                test_shell = True
            tested = subprocess.run(
                test_argv,
                cwd=clean,
                shell=test_shell,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                env={**os.environ, "CI": "1", "PAGER": "cat"},
                check=False,
            )
            returncode: int | None = tested.returncode
            output = "\n".join([*setup_output, tested.stdout or ""])
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = None
            output = "\n".join([
                *setup_output,
                (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            ])
            output += f"\n[timeout after {timeout_seconds}s]"
        duration = time.monotonic() - started
        return ValidationResult(
            "passed" if returncode == 0 and not timed_out else "failed",
            patch_hash,
            command_hash,
            base,
            command,
            returncode,
            timed_out,
            duration,
            output[-max_output_chars:],
            "" if returncode == 0 and not timed_out else "visible test command failed",
            setup_commands,
        )


def write_validation(path: str | Path, result: ValidationResult) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

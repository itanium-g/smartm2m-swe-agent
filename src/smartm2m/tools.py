"""Checked, auditable tools exposed to the custom agent."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .config import TaskSpec
from .protocol import ToolCall


class ToolError(RuntimeError):
    """A tool request was invalid or could not be executed."""


@dataclass
class ToolResult:
    ok: bool
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandRecord:
    command: str
    returncode: int | None
    output: str
    duration_seconds: float
    timed_out: bool = False
    signal: int | None = None
    output_chars: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "output": self.output,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "signal": self.signal,
            "output_chars": self.output_chars,
        }


@dataclass
class Checkpoint:
    tracked_patch: str
    untracked: dict[str, bytes]


def _run_git(root: Path, args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _safe_relative(root: Path, relative: str, *, allow_root: bool = False) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ToolError(f"path escapes task workspace: {relative}") from exc
    if not allow_root and candidate == root.resolve():
        raise ToolError("workspace root is not a file")
    return candidate


def _patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        value = line[4:].split("\t", 1)[0].split(" ", 1)[0]
        if value == "/dev/null":
            continue
        if value.startswith(("a/", "b/")):
            value = value[2:]
        paths.append(value)
    return paths


def _validate_patch_paths(patch: str) -> None:
    paths = _patch_paths(patch)
    if not paths:
        raise ToolError("patch has no file headers")
    for value in paths:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or any(part.lower() == ".git" for part in path.parts):
            raise ToolError(f"unsafe patch path: {value}")
        lower = value.lower()
        if lower.startswith(("tests/", "test/")) or "/tests/" in lower:
            raise ToolError("test files are outside the generation edit boundary")
        if lower.startswith((".github/", ".gitlab/")) or lower in {"makefile", "dockerfile"}:
            raise ToolError("automation and container files are outside the generation edit boundary")
        if lower.endswith((
            "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "package.json",
            "package-lock.json", "requirements.txt", "poetry.lock", "uv.lock",
        )):
            raise ToolError("build/configuration files are outside the generation edit boundary")


def _git_patch(root: Path) -> str:
    tracked = _run_git(root, ["diff", "--binary", "--no-ext-diff", "HEAD"])
    if tracked.returncode not in (0, 1):
        raise ToolError(f"could not capture git diff: {tracked.stderr.strip()}")
    chunks = [tracked.stdout]
    untracked = _run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    if untracked.returncode != 0:
        raise ToolError(f"could not list untracked files: {untracked.stderr.strip()}")
    for raw in untracked.stdout.split("\0"):
        if not raw:
            continue
        path = _safe_relative(root, raw)
        if path.is_symlink() or not path.is_file():
            continue
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "/dev/null", "--", raw],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if diff.returncode in (0, 1):
            chunks.append(diff.stdout)
    return "".join(chunks)


class ToolRunner:
    """Execute only narrow operations inside one task-owned workspace."""

    def __init__(self, root: str | Path, task: TaskSpec, *, command_timeout: int = 120, max_output_chars: int = 10000):
        self.root = Path(root).resolve()
        self.task = task
        self.command_timeout = command_timeout
        self.max_output_chars = max_output_chars
        self.checkpoints: list[Checkpoint] = []
        self.commands: list[CommandRecord] = []
        self.submitted = False
        self.last_patch_error: str | None = None
        self._last_test_patch_sha256: str | None = None
        if not self.root.is_dir():
            raise ToolError(f"task workspace does not exist: {self.root}")

    def execute(self, call: ToolCall) -> ToolResult:
        handlers = {
            "list_files": self.list_files,
            "search": self.search,
            "read_file": self.read_file,
            "apply_patch": self.apply_patch,
            "run_tests": self.run_tests,
            "get_diff": self.get_diff,
            "submit_patch": self.submit_patch,
            "rollback": self.rollback,
        }
        handler = handlers.get(call.name)
        if handler is None:
            return ToolResult(False, f"unknown tool: {call.name}", {"error": "unknown_tool"})
        try:
            return handler(**call.arguments)
        except (ToolError, TypeError, ValueError) as exc:
            return ToolResult(False, str(exc), {"error": type(exc).__name__})

    def list_files(self, prefix: str = "", max_files: int = 200) -> ToolResult:
        base = _safe_relative(self.root, prefix, allow_root=True) if prefix else self.root
        if not base.exists() or not base.is_dir():
            raise ToolError(f"directory not found: {prefix}")
        files: list[str] = []
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(self.root).as_posix()
            if any(part in {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"} for part in path.parts):
                continue
            if path.is_file():
                files.append(relative)
            if len(files) >= max(1, min(int(max_files), 1000)):
                break
        return ToolResult(True, "\n".join(files) or "(no files)", {"count": len(files)})

    def search(self, query: str, path: str = ".", max_results: int = 80) -> ToolResult:
        if not query or len(query) > 300:
            raise ToolError("query must be 1-300 characters")
        base = _safe_relative(self.root, path, allow_root=True)
        if not base.exists():
            raise ToolError(f"search path not found: {path}")
        if shutil.which("rg"):
            proc = subprocess.run(
                [
                    "rg", "--line-number", "--no-heading", "--color", "never", "--hidden",
                    "-g", "!.git", "--", query, str(base),
                ],
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
            )
            output = proc.stdout if proc.returncode in (0, 1) else proc.stderr
        else:
            matches: list[str] = []
            for file in base.rglob("*"):
                if not file.is_file() or ".git" in file.parts:
                    continue
                try:
                    for number, line in enumerate(file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if query.lower() in line.lower():
                            matches.append(f"{file.relative_to(self.root)}:{number}:{line}")
                except OSError:
                    continue
            output = "\n".join(matches)
        lines = output.splitlines()[: max(1, min(int(max_results), 500))]
        return ToolResult(True, "\n".join(lines) or "(no matches)", {"count": len(lines)})

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> ToolResult:
        target = _safe_relative(self.root, path)
        if not target.is_file():
            raise ToolError(f"file not found: {path}")
        if target.stat().st_size > 1_000_000:
            raise ToolError("file exceeds 1 MiB read limit; search it or read a smaller file")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(start_line))
        end = len(lines) if end_line is None else min(len(lines), int(end_line))
        if end < start:
            raise ToolError("end_line must be >= start_line")
        selected = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
        return ToolResult(True, selected, {"path": path, "start_line": start, "end_line": end})

    def _checkpoint(self) -> None:
        tracked = _git_patch(self.root)
        untracked: dict[str, bytes] = {}
        listing = _run_git(self.root, ["ls-files", "--others", "--exclude-standard", "-z"])
        if listing.returncode != 0:
            raise ToolError("workspace is not a usable git repository")
        for raw in listing.stdout.split("\0"):
            if not raw:
                continue
            path = _safe_relative(self.root, raw)
            if path.is_file() and not path.is_symlink():
                untracked[raw] = path.read_bytes()
        self.checkpoints.append(Checkpoint(tracked, untracked))
        if len(self.checkpoints) > 3:
            self.checkpoints.pop(0)

    def apply_patch(self, patch: str) -> ToolResult:
        if not isinstance(patch, str) or len(patch) > 500_000:
            raise ToolError("patch must be a string no larger than 500 KiB")
        _validate_patch_paths(patch)
        self._checkpoint()
        checked = _run_git(self.root, ["apply", "--check", "--whitespace=nowarn", "-"], input_text=patch)
        if checked.returncode != 0:
            self.last_patch_error = checked.stderr.strip() or checked.stdout.strip()
            return ToolResult(False, f"patch rejected: {self.last_patch_error}", {"error": "patch_check_failed"})
        applied = _run_git(self.root, ["apply", "--whitespace=nowarn", "-"], input_text=patch)
        if applied.returncode != 0:
            self.last_patch_error = applied.stderr.strip() or applied.stdout.strip()
            return ToolResult(False, f"patch application failed: {self.last_patch_error}", {"error": "patch_apply_failed"})
        check = _run_git(self.root, ["diff", "--check"])
        if check.returncode != 0:
            self._last_test_patch_sha256 = None
            return ToolResult(False, f"patch has whitespace errors: {check.stdout or check.stderr}", {"error": "diff_check_failed"})
        self._last_test_patch_sha256 = None
        return ToolResult(True, f"applied patch to {len(set(_patch_paths(patch)))} file(s)", {"paths": _patch_paths(patch)})

    def run_tests(self, command: str = "default", timeout_seconds: int | None = None) -> ToolResult:
        if command == "default":
            command = self.task.test_commands[0]
        elif command.startswith("command_") and command[8:].isdigit():
            index = int(command[8:])
            try:
                command = self.task.test_commands[index]
            except IndexError as exc:
                raise ToolError(f"unknown declared test command: {command}") from exc
        if command not in self.task.test_commands:
            raise ToolError("run_tests only accepts an exact command from the trusted task manifest")
        timeout = self.command_timeout if timeout_seconds is None else max(1, min(int(timeout_seconds), self.command_timeout))
        started = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                command,
                cwd=self.root,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
                env={**os.environ, "PAGER": "cat", "CI": "1"},
            )
            returncode: int | None = proc.returncode
            output = proc.stdout or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = None
            output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            output += f"\n[timeout after {timeout}s]"
        duration = time.monotonic() - started
        full_chars = len(output)
        visible = output[-self.max_output_chars :] if full_chars > self.max_output_chars else output
        record = CommandRecord(command, returncode, output, duration, timed_out, None, full_chars)
        self.commands.append(record)
        current_patch_sha256 = hashlib.sha256(_git_patch(self.root).encode()).hexdigest()
        self._last_test_patch_sha256 = current_patch_sha256 if returncode == 0 and not timed_out else None
        lower = output.lower()
        build_failure = any(marker in lower for marker in ("syntaxerror", "indentationerror", "modulenotfounderror", "importerror"))
        metadata = {
            "command": command,
            "returncode": returncode,
            "duration_seconds": duration,
            "timed_out": timed_out,
            "output_chars": full_chars,
            "truncated": full_chars > self.max_output_chars,
            "failure_class": "build_failure" if build_failure else ("test_failure" if returncode else "pass"),
        }
        return ToolResult(returncode == 0 and not timed_out, visible, metadata)

    def get_diff(self) -> ToolResult:
        patch = _git_patch(self.root)
        return ToolResult(True, patch[-500_000:] if len(patch) > 500_000 else patch, {"patch_sha256": hashlib.sha256(patch.encode()).hexdigest()})

    def submit_patch(self) -> ToolResult:
        patch = _git_patch(self.root)
        patch_sha256 = hashlib.sha256(patch.encode()).hexdigest()
        if not patch:
            return ToolResult(
                False,
                "no source changes were found",
                {"patch_sha256": patch_sha256, "has_changes": False, "error": "empty_patch"},
            )
        if self._last_test_patch_sha256 != patch_sha256:
            return ToolResult(
                False,
                "run a declared test command successfully after the latest edit before submitting",
                {"patch_sha256": patch_sha256, "has_changes": True, "error": "tests_required"},
            )
        self.submitted = True
        return ToolResult(
            True,
            "patch sealed for validation",
            {"patch_sha256": patch_sha256, "has_changes": True},
        )

    def rollback(self) -> ToolResult:
        if not self.checkpoints:
            raise ToolError("no checkpoint is available")
        checkpoint = self.checkpoints[-1]
        reset = _run_git(self.root, ["reset", "--hard", "HEAD"])
        if reset.returncode != 0:
            raise ToolError(reset.stderr.strip() or "git reset failed during rollback")
        current = _run_git(self.root, ["ls-files", "--others", "--exclude-standard", "-z"])
        for raw in current.stdout.split("\0"):
            if not raw:
                continue
            path = _safe_relative(self.root, raw)
            if path.is_file() or path.is_symlink():
                path.unlink()
        for relative, content in checkpoint.untracked.items():
            path = _safe_relative(self.root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if checkpoint.tracked_patch:
            apply = _run_git(self.root, ["apply", "--whitespace=nowarn", "-"], input_text=checkpoint.tracked_patch)
            if apply.returncode != 0:
                raise ToolError(apply.stderr.strip() or "could not restore checkpoint patch")
        self._last_test_patch_sha256 = None
        return ToolResult(True, "restored the latest checkpoint", {"patch_sha256": hashlib.sha256(_git_patch(self.root).encode()).hexdigest()})

    def state_hash(self) -> str:
        patch = _git_patch(self.root)
        files = self.list_files(max_files=1000).content
        return hashlib.sha256((patch + "\0" + files).encode()).hexdigest()

    def command_records(self) -> list[dict[str, Any]]:
        return [record.as_dict() for record in self.commands]


def tool_schemas(task: TaskSpec) -> list[dict[str, Any]]:
    commands = ["default", *[f"command_{i}" for i in range(len(task.test_commands))]]
    return [
        {"type": "function", "function": {"name": "list_files", "description": "List source files in the task repository.", "parameters": {"type": "object", "properties": {"prefix": {"type": "string"}, "max_files": {"type": "integer"}}, "required": []}}},
        {"type": "function", "function": {"name": "search", "description": "Search repository text for a symbol, error, or behavior.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "read_file", "description": "Read a bounded range from a source file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "apply_patch", "description": "Apply a unified diff to non-test source files. Inspect first and keep the patch minimal.", "parameters": {"type": "object", "properties": {"patch": {"type": "string"}}, "required": ["patch"]}}},
        {"type": "function", "function": {"name": "run_tests", "description": "Run a trusted test command. Declared commands: " + ", ".join(commands), "parameters": {"type": "object", "properties": {"command": {"type": "string", "enum": commands}, "timeout_seconds": {"type": "integer"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_diff", "description": "Inspect the current source diff before submitting.", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "rollback", "description": "Restore the latest pre-edit checkpoint after a broken patch or recovery decision.", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "submit_patch", "description": "Seal the current patch for clean replay validation after all checks pass.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    ]

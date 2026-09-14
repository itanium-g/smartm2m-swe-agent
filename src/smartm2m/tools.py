"""Checked, auditable tools exposed to the custom agent."""

from __future__ import annotations

import hashlib
import os
import shlex
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
    container_image: str = ""
    stdout: str = ""
    stderr: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "output": self.output,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "signal": self.signal,
            "output_chars": self.output_chars,
            "container_image": self.container_image,
            "stdout": self.stdout,
            "stderr": self.stderr,
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


def _git_tracked_patch(root: Path) -> str:
    tracked = _run_git(root, ["diff", "--binary", "--no-ext-diff", "HEAD"])
    if tracked.returncode not in (0, 1):
        raise ToolError(f"could not capture git diff: {tracked.stderr.strip()}")
    return tracked.stdout


def _git_patch(root: Path) -> str:
    """Capture tracked and ordinary untracked source changes."""
    chunks = [_git_tracked_patch(root)]
    untracked = _run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    if untracked.returncode != 0:
        raise ToolError(f"could not list untracked files: {untracked.stderr.strip()}")
    for raw in untracked.stdout.split("\0"):
        if not raw:
            continue
        path = _safe_relative(root, raw)
        if path.is_symlink():
            raise ToolError(f"symlink changes are not supported: {raw}")
        if not path.is_file():
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


_DYNAMIC_TEST_RUNNERS = {
    "pytest", "py.test", "tox", "nox", "python", "python3", "go", "cargo",
    "npm", "mvn", "gradle", "dotnet", "mix", "ruby", "php",
}


def _has_unquoted_shell_control(command: str) -> bool:
    quote = ""
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if char in {"'", '"'}:
            if not quote:
                quote = char
            elif quote == char:
                quote = ""
            continue
        if not quote and (char in ";|<>\n\r`" or char == "&"):
            return True
    return bool(quote)


def validate_test_command(command: str, *, declared: bool = False) -> None:
    """Validate a bounded repository-test command before shell execution.

    Declared commands come from the frozen safe manifest. Model-selected
    commands still need to be useful for debugging, but are limited to common
    test runners and cannot contain shell composition, redirection, traversal,
    or package/system-management commands.
    """
    if not isinstance(command, str) or not command.strip() or len(command) > 1000:
        raise ToolError("test command must be a non-empty string no longer than 1000 characters")
    if (_has_unquoted_shell_control(command) or "$(" in command or "${" in command or "`" in command):
        raise ToolError("test command cannot contain shell control operators or expansion")
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ToolError(f"test command has invalid quoting: {exc}") from exc
    if not tokens:
        raise ToolError("test command is empty")
    if any(token == ".." or token.startswith("../") or "/../" in token for token in tokens):
        raise ToolError("test command cannot traverse outside the task workspace")
    if declared:
        return
    executable = Path(tokens[0]).name
    if executable not in _DYNAMIC_TEST_RUNNERS:
        raise ToolError("model-selected commands must start with a supported repository test runner")
    if executable in {"python", "python3"}:
        if len(tokens) >= 2 and tokens[1] == "-c":
            raise ToolError("model-selected Python commands cannot execute inline code")
        is_module = len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] in {"pytest", "unittest"}
        is_repo_runner = len(tokens) >= 2 and (
            tokens[1].endswith(".py") and not Path(tokens[1]).is_absolute()
        )
        if not (is_module or is_repo_runner):
            raise ToolError("Python test commands must use pytest/unittest or a repository test script")
    if executable in {"npm", "mvn", "gradle", "dotnet", "cargo", "go", "mix"} and len(tokens) < 2:
        raise ToolError("test runner command is missing its test action")


def _docker_argv(root: Path, image: str, command: str) -> list[str]:
    if not image or image.startswith("-") or any(char.isspace() for char in image):
        raise ToolError("container image must be a simple image reference")
    return [
        # SWE-bench's pinned evaluator and mini-swe-agent Docker environment
        # use Docker's default network mode. Match that task environment;
        # command safety comes from the typed runner and container boundary.
        "docker", "run", "--rm", "--init",
        "--volume", f"{root}:/testbed", "--workdir", "/testbed",
        "--env", "CI=1", "--env", "PAGER=cat", image, "bash", "-lc", command,
    ]


class ToolRunner:
    """Execute only narrow operations inside one task-owned workspace."""

    def __init__(
        self,
        root: str | Path,
        task: TaskSpec,
        *,
        command_timeout: int = 120,
        max_output_chars: int = 10000,
        container_image: str | None = None,
    ):
        self.root = Path(root).resolve()
        self.task = task
        self.command_timeout = command_timeout
        self.max_output_chars = max_output_chars
        self.checkpoints: list[Checkpoint] = []
        self.commands: list[CommandRecord] = []
        self.container_image = container_image or task.image
        self.submitted = False
        self.last_patch_error: str | None = None
        self._last_test_patch_sha256: str | None = None
        self._last_successful_test_command: str | None = None
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
        # Keep untracked files separate: applying an untracked-file diff and
        # restoring its bytes would otherwise restore the same file twice.
        tracked = _git_tracked_patch(self.root)
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
        for value in _patch_paths(patch):
            if (self.root / value).is_symlink():
                self.rollback()
                raise ToolError(f"symlink changes are not supported: {value}")
        check = _run_git(self.root, ["diff", "--check"])
        if check.returncode != 0:
            self._last_test_patch_sha256 = None
            return ToolResult(False, f"patch has whitespace errors: {check.stdout or check.stderr}", {"error": "diff_check_failed"})
        self._last_test_patch_sha256 = None
        self._last_successful_test_command = None
        return ToolResult(True, f"applied patch to {len(set(_patch_paths(patch)))} file(s)", {"paths": _patch_paths(patch)})

    def run_tests(self, command: str = "default", timeout_seconds: int | None = None) -> ToolResult:
        declared = True
        if command == "default":
            command = self.task.test_commands[0]
        elif command.startswith("command_") and command[8:].isdigit():
            index = int(command[8:])
            try:
                command = self.task.test_commands[index]
            except IndexError as exc:
                raise ToolError(f"unknown declared test command: {command}") from exc
        elif command not in self.task.test_commands:
            declared = False
        validate_test_command(command, declared=declared)
        timeout = self.command_timeout if timeout_seconds is None else max(1, min(int(timeout_seconds), self.command_timeout))
        started = time.monotonic()
        timed_out = False
        execution_command = command
        argv: list[str] | str = command
        returncode: int | None = None
        output = ""
        stdout = ""
        stderr = ""
        should_execute = True
        if self.container_image:
            if shutil.which("docker") is None:
                output = f"[container runtime unavailable: docker is not installed; image={self.container_image}]"
                stdout = output
                metadata_failure = "infra_failure"
                should_execute = False
            else:
                argv = _docker_argv(self.root, self.container_image, command)
                execution_command = " ".join(shlex.quote(value) for value in argv)
                metadata_failure = ""
        else:
            metadata_failure = ""
        try:
            if should_execute:
                proc = subprocess.run(
                    argv,
                    cwd=self.root,
                    shell=isinstance(argv, str),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    check=False,
                    env={**os.environ, "PAGER": "cat", "CI": "1"},
                )
                returncode = proc.returncode
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
                output = stdout
                if stderr:
                    output += f"\n[stderr]\n{stderr}"
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = None
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            output = stdout
            if stderr:
                output += f"\n[stderr]\n{stderr}"
            output += f"\n[timeout after {timeout}s]"
        duration = time.monotonic() - started
        full_chars = len(output)
        visible = output[-self.max_output_chars :] if full_chars > self.max_output_chars else output
        signal = -returncode if returncode is not None and returncode < 0 else None
        record = CommandRecord(
            command,
            returncode,
            output,
            duration,
            timed_out,
            signal,
            full_chars,
            self.container_image,
            stdout,
            stderr,
        )
        self.commands.append(record)
        current_patch_sha256 = hashlib.sha256(_git_patch(self.root).encode()).hexdigest()
        self._last_test_patch_sha256 = current_patch_sha256 if returncode == 0 and not timed_out else None
        if self._last_test_patch_sha256:
            self._last_successful_test_command = command
        lower = output.lower()
        container_failure = self.container_image and returncode not in (None, 0) and any(
            marker in lower for marker in ("cannot connect to the docker daemon", "is the docker daemon running")
        )
        build_failure = any(marker in lower for marker in ("syntaxerror", "indentationerror", "modulenotfounderror", "importerror"))
        metadata = {
            "command": command,
            "executed_command": execution_command,
            "returncode": returncode,
            "signal": signal,
            "duration_seconds": duration,
            "timed_out": timed_out,
            "output_chars": full_chars,
            "truncated": full_chars > self.max_output_chars,
            "failure_class": metadata_failure or (
                "infra_failure" if container_failure else
                ("timeout" if timed_out else
                ("build_failure" if build_failure else ("test_failure" if returncode else "pass"))
                )
            ),
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
        try:
            _validate_patch_paths(patch)
        except ToolError as exc:
            return ToolResult(
                False,
                f"source-only patch validation failed: {exc}",
                {"patch_sha256": patch_sha256, "has_changes": True, "error": "unsafe_patch"},
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
        # The task workspace is disposable; remove ignored test/build output
        # too so a rollback cannot leave a stale artifact affecting evidence.
        cleaned = _run_git(self.root, ["clean", "-fdx"])
        if cleaned.returncode != 0:
            raise ToolError(cleaned.stderr.strip() or "git clean failed during rollback")
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
        self._last_successful_test_command = None
        return ToolResult(True, "restored the latest checkpoint", {"patch_sha256": hashlib.sha256(_git_patch(self.root).encode()).hexdigest()})

    def state_hash(self) -> str:
        patch = _git_patch(self.root)
        files = self.list_files(max_files=1000).content
        return hashlib.sha256((patch + "\0" + files).encode()).hexdigest()

    def command_records(self) -> list[dict[str, Any]]:
        return [record.as_dict() for record in self.commands]

    def last_successful_test_command(self) -> str | None:
        return self._last_successful_test_command


def tool_schemas(task: TaskSpec) -> list[dict[str, Any]]:
    commands = ["default", *[f"command_{i}" for i in range(len(task.test_commands))]]
    return [
        {"type": "function", "function": {"name": "list_files", "description": "List source files in the task repository.", "parameters": {"type": "object", "properties": {"prefix": {"type": "string"}, "max_files": {"type": "integer"}}, "required": []}}},
        {"type": "function", "function": {"name": "search", "description": "Search repository text for a symbol, error, or behavior.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "read_file", "description": "Read a bounded range from a source file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "apply_patch", "description": "Apply a unified diff to non-test source files. Inspect first and keep the patch minimal.", "parameters": {"type": "object", "properties": {"patch": {"type": "string"}}, "required": ["patch"]}}},
        {"type": "function", "function": {"name": "run_tests", "description": "Run a bounded repository-native test command. Use a declared alias (" + ", ".join(commands) + ") or a targeted pytest/unittest/Django test command; shell composition and destructive commands are rejected.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_diff", "description": "Inspect the current source diff before submitting.", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "rollback", "description": "Restore the latest pre-edit checkpoint after a broken patch or recovery decision.", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "submit_patch", "description": "Seal the current patch for clean replay validation after all checks pass.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    ]

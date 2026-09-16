"""Checked, auditable tools exposed to the custom agent."""

from __future__ import annotations

import hashlib
import inspect
import os
import re
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


def _validate_target_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(part.lower() == ".git" for part in path.parts):
        raise ToolError(f"unsafe path: {value}")
    lower = value.lower()
    if lower.startswith(("tests/", "test/")) or "/tests/" in lower or "/test/" in lower:
        raise ToolError("test files are outside the generation edit boundary")
    if lower.startswith(("docs/", "doc/")) or "/docs/" in lower or "/doc/" in lower:
        raise ToolError("documentation files are outside the generation edit boundary; modify the package source code instead")
    if lower.endswith((".rst", ".txt", ".md", ".html")):
        raise ToolError("documentation and markup files are outside the generation edit boundary; modify the package source code (*.py) instead")
    if lower.startswith((".github/", ".gitlab/")) or lower in {"makefile", "dockerfile"}:
        raise ToolError("automation and container files are outside the generation edit boundary")
    if lower.endswith((
        "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "package.json",
        "package-lock.json", "requirements.txt", "poetry.lock", "uv.lock",
    )):
        raise ToolError("build/configuration files are outside the generation edit boundary")
    return path


def _validate_patch_paths(patch: str) -> None:
    paths = _patch_paths(patch)
    if not paths:
        raise ToolError("patch has no file headers. Use edit_file(path, old_text, new_text) for bounded deterministic source editing instead.")
    for value in paths:
        _validate_target_path(value)


def _normalize_patch(patch: str) -> str:
    """Normalize non-standard patch formats (e.g. *** Begin Patch / *** Update File:)."""
    if "*** Begin Patch" in patch or "*** Update File:" in patch:
        lines = patch.splitlines()
        normalized: list[str] = []
        for line in lines:
            if line.startswith("*** Begin Patch") or line.startswith("*** End Patch"):
                continue
            if line.startswith("*** Update File:"):
                filepath = line.split("Update File:", 1)[1].strip()
                normalized.append(f"--- a/{filepath}")
                normalized.append(f"+++ b/{filepath}")
                continue
            if line.strip() == "@@":
                normalized.append("@@ -1,1 +1,1 @@")
                continue
            normalized.append(line)
        return "\n".join(normalized) + "\n"
    return patch


def _extract_hunks_for_direct_apply(patch: str) -> list[tuple[str, str, str]]:
    """Extract (rel_path, old_text, new_text) from unified diff or custom patch format."""
    lines = patch.splitlines()
    updates: list[tuple[str, list[str]]] = []
    current_file = None
    hunk_lines: list[str] = []
    for line in lines:
        if line.startswith("--- a/") or line.startswith("--- "):
            if current_file and hunk_lines:
                updates.append((current_file, hunk_lines))
                hunk_lines = []
            val = line[4:].strip()
            if val.startswith("a/"):
                val = val[2:]
            current_file = val
        elif line.startswith("*** Update File:"):
            if current_file and hunk_lines:
                updates.append((current_file, hunk_lines))
                hunk_lines = []
            current_file = line.split("Update File:", 1)[1].strip()
        elif line.startswith((" ", "+", "-")) and not line.startswith(("---", "+++")):
            hunk_lines.append(line)
    if current_file and hunk_lines:
        updates.append((current_file, hunk_lines))

    result: list[tuple[str, str, str]] = []
    for f, h in updates:
        old_part = "\n".join(line[1:] for line in h if line.startswith((" ", "-")))
        new_part = "\n".join(line[1:] for line in h if line.startswith((" ", "+")))
        if old_part and old_part != new_part:
            result.append((f, old_part, new_part))
    return result


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


def _is_unfiltered_test_suite_run(command: str) -> tuple[bool, str]:
    """Detect if a test command runs Django's entire monolithic test suite without app targets."""
    try:
        tokens = shlex.split(command)
    except Exception:
        return False, ""
    if not tokens:
        return False, ""
    # Check for Django runtests.py
    runtests_idx = -1
    for i, tok in enumerate(tokens):
        if tok.endswith("runtests.py"):
            runtests_idx = i
            break
    if runtests_idx >= 0:
        skip_next = False
        labels = []
        for tok in tokens[runtests_idx + 1:]:
            if skip_next:
                skip_next = False
                continue
            if tok in {"--settings", "--verbosity", "-v", "--parallel", "-p"}:
                skip_next = True
                continue
            if tok.startswith("-"):
                continue
            labels.append(tok)
        if not labels:
            return True, (
                "Running tests/runtests.py without specifying target test app(s) runs the entire test suite and times out after 120s. "
                "Specify a targeted test app or module, e.g.: 'python tests/runtests.py <app_name>' (search under tests/ to find the relevant test directory)."
            )
    return False, ""


def _docker_argv(root: Path, image: str, command: str) -> list[str]:
    if not image or image.startswith("-") or any(char.isspace() for char in image):
        raise ToolError("container image must be a simple image reference")
    return [
        # SWE-bench's pinned evaluator and mini-swe-agent Docker environment
        # use Docker's default network mode. Match that task environment;
        # command safety comes from the typed runner and container boundary.
        "docker", "run", "--rm", "--init",
        "--volume", f"{root}:/testbed", "--workdir", "/testbed",
        "--env", "CI=1", "--env", "PAGER=cat", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTHONIOENCODING=utf-8", "--env", "LANG=C.UTF-8", "--env", "LC_ALL=C.UTF-8",
        image, "bash", "-lc", command,
    ]


def _strip_line_numbers(text: str) -> tuple[str, bool]:
    """Strip line number prefixes like '123: ' or '123| ' if present on all non-empty lines."""
    lines = text.splitlines()
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return text, False
    pattern = re.compile(r"^\s*\d+[:|]\s?")
    if any(pattern.match(line) for line in non_empty):
        stripped = [pattern.sub("", line) for line in lines]
        return "\n".join(stripped), True
    return text, False


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
            "edit_file": self.edit_file,
            "apply_patch": self.apply_patch,
            "run_tests": self.run_tests,
            "get_diff": self.get_diff,
            "submit_patch": self.submit_patch,
            "rollback": self.rollback,
            "commentary": lambda **kwargs: ToolResult(True, "noted", {"commentary": kwargs}),
        }
        handler = handlers.get(call.name)
        if handler is None:
            return ToolResult(False, f"unknown tool: {call.name}", {"error": "unknown_tool"})
        if "__invalid_json_raw__" in call.arguments or "__invalid_args_raw__" in call.arguments:
            raw = call.arguments.get("__invalid_json_raw__") or call.arguments.get("__invalid_args_raw__")
            return ToolResult(
                False,
                f"The tool call arguments could not be parsed as valid JSON: {raw!r}. "
                "Please call the tool again with valid, properly formatted JSON arguments.",
                {"error": "invalid_json_arguments"},
            )
        try:
            sig = inspect.signature(handler)
            has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            filtered = call.arguments if has_varkw else {k: v for k, v in call.arguments.items() if k in sig.parameters}
            return handler(**filtered)
        except (ToolError, TypeError, ValueError) as exc:
            return ToolResult(False, str(exc), {"error": type(exc).__name__})

    def list_files(self, prefix: str = "", max_files: int = 200) -> ToolResult:
        base = _safe_relative(self.root, prefix, allow_root=True) if prefix else self.root
        if not base.exists() or not base.is_dir():
            raise ToolError(f"directory not found: {prefix}")
        files: list[str] = []
        # Sort direct children first, then subdirectories by depth and path
        for path in sorted(base.rglob("*"), key=lambda p: (len(p.relative_to(base).parts), p.as_posix())):
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
        target_path = "." if base == self.root else base.relative_to(self.root).as_posix()
        if shutil.which("rg"):
            rg_base = [
                "rg", "--line-number", "--no-heading", "--color", "never", "--hidden",
                "-g", "!.git", "-g", "!*.pyc",
            ]
            if target_path == ".":
                rg_base.extend(["-g", "!docs/**", "-g", "!doc/**"])
            # Try literal/fixed-string search first with smart case
            proc = subprocess.run(
                [*rg_base, "-F", "-S", "--", query, target_path],
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                output = proc.stdout
            elif proc.returncode == 1:
                # Try case-insensitive fixed string
                proc_i = subprocess.run(
                    [*rg_base, "-F", "-i", "--", query, target_path],
                    cwd=self.root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if proc_i.returncode == 0:
                    output = proc_i.stdout
                else:
                    # Try regex search with smart case
                    reg_proc = subprocess.run(
                        [*rg_base, "-S", "--", query, target_path],
                        cwd=self.root,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if reg_proc.returncode == 0:
                        output = reg_proc.stdout
                    else:
                        # Try placeholder substitution for uppercase metavariables like FOO, FIELD, BAR
                        placeholder_query = re.sub(r'(?<=_)[A-Z]{2,}(?=_|\b)', lambda m: r'[^\s_]+', query)
                        if placeholder_query != query:
                            ph_proc = subprocess.run(
                                [*rg_base, "-S", "--", placeholder_query, target_path],
                                cwd=self.root,
                                text=True,
                                capture_output=True,
                                check=False,
                            )
                            output = ph_proc.stdout if ph_proc.returncode == 0 else ""
                        else:
                            output = ""
                        # If still no matches and query has multiple words, try significant code tokens
                        if not output and len(query.split()) > 1:
                            _STOP_WORDS = {
                                "the", "and", "for", "with", "from", "that", "this", "when",
                                "object", "files", "file", "handling", "code", "in", "of",
                                "to", "a", "is", "by", "on", "into", "as", "at", "an",
                            }
                            tokens = [
                                w for w in re.findall(r'[A-Za-z0-9_]+', query)
                                if len(w) >= 3 and w.lower() not in _STOP_WORDS
                            ]
                            tokens.sort(key=lambda w: (not (w[0].isupper() or "_" in w), -len(w)))
                            for tok in tokens:
                                tok_proc = subprocess.run(
                                    [*rg_base, "-S", "-F", "--", tok, target_path],
                                    cwd=self.root,
                                    text=True,
                                    capture_output=True,
                                    check=False,
                                )
                                if tok_proc.returncode == 0 and tok_proc.stdout.strip():
                                    output = tok_proc.stdout
                                    break
            else:
                output = ""
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
        lines = output.splitlines()
        limit = max(1, min(int(max_results), 500))
        visible_lines = lines[:limit]
        content = "\n".join(visible_lines) or (
            "(no matches: if your query contains placeholder names like 'FOO' or 'FIELD', "
            "or full sentences, search for shorter invariant symbols like '_display' or function/class names, "
            "or search a broader path like path='.')"
        )
        if len(lines) > limit:
            content += f"\n[... {len(lines) - limit} additional matches truncated. Narrow the search query or specify a focused path (e.g. path='django/db/models') to see specific results. ...]"
        return ToolResult(True, content, {"count": len(visible_lines), "total_matches": len(lines)})

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
        # Ensure minimum window of 25 lines so model has adequate context
        # and doesn't get trapped in a 1-line creeping loop
        if end_line is not None and (end - start) < 20:
            end = min(len(lines), start + 35)
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

    def edit_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
        """Safely replace an exact block of code (old_text) with new_text in a source file."""
        if not isinstance(path, str) or not path.strip():
            raise ToolError("path must be a non-empty string")
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise ToolError("old_text and new_text must be strings")
        if not old_text:
            raise ToolError("old_text cannot be empty; specify the exact block of code to replace")
        if old_text == new_text:
            raise ToolError("old_text and new_text are identical; no changes made")

        _validate_target_path(path)
        target = _safe_relative(self.root, path)
        if target.is_symlink():
            raise ToolError(f"symlink changes are not supported: {path}")
        if not target.is_file():
            raise ToolError(f"file not found: {path}")
        if target.stat().st_size > 1_000_000:
            raise ToolError("file exceeds 1 MiB edit limit; search or edit smaller portions")

        content = target.read_text(encoding="utf-8", errors="replace")

        cand_old = old_text
        cand_new = new_text
        if cand_old not in content:
            stripped_old, was_stripped = _strip_line_numbers(old_text)
            if was_stripped:
                cand_old = stripped_old
                stripped_new, _ = _strip_line_numbers(new_text)
                cand_new = stripped_new

        count = content.count(cand_old)
        if count == 1:
            matched_old = cand_old
            adjusted_new = cand_new
        elif count > 1:
            raise ToolError(
                f"old_text matched {count} occurrences in {path}. "
                "Please provide more surrounding context lines in old_text so that the match is unique."
            )
        else:
            file_lines = content.splitlines()
            old_lines = cand_old.splitlines()
            if not old_lines:
                raise ToolError("old_text cannot be empty")
            old_stripped = [line.strip() for line in old_lines]
            matches = []
            for i in range(len(file_lines) - len(old_lines) + 1):
                window = [file_lines[i + j].strip() for j in range(len(old_lines))]
                if window == old_stripped:
                    matches.append(i)
            if len(matches) == 1:
                start_idx = matches[0]
                matched_old = "\n".join(file_lines[start_idx : start_idx + len(old_lines)])
                first_file_line = file_lines[start_idx]
                file_indent = first_file_line[: len(first_file_line) - len(first_file_line.lstrip())]
                first_old_line = old_lines[0]
                old_indent = first_old_line[: len(first_old_line) - len(first_old_line.lstrip())]
                if file_indent and not old_indent:
                    new_lines = cand_new.splitlines()
                    adjusted_new = "\n".join(
                        (file_indent + line if line.strip() and not line.startswith(file_indent) else line)
                        for line in new_lines
                    )
                else:
                    adjusted_new = cand_new
            elif len(matches) > 1:
                raise ToolError(
                    f"old_text matched {len(matches)} occurrences in {path}. "
                    "Please provide more surrounding context lines in old_text so that the match is unique."
                )
            else:
                raise ToolError(
                    f"old_text not found in {path}. "
                    "Read the file first around the target line to copy the exact code block including whitespace and indentation."
                )

        self._checkpoint()
        new_content = content.replace(matched_old, adjusted_new, 1)
        target.write_text(new_content, encoding="utf-8")
        self._last_test_patch_sha256 = None
        self._last_successful_test_command = None
        return ToolResult(
            True,
            f"Successfully edited {path} (replaced 1 occurrence). Run run_tests to verify your fix.",
            {"path": path},
        )

    def apply_patch(self, patch: str) -> ToolResult:
        if not isinstance(patch, str) or len(patch) > 500_000:
            raise ToolError("patch must be a string no larger than 500 KiB")
        normalized = _normalize_patch(patch)
        _validate_patch_paths(normalized)
        self._checkpoint()
        checked = _run_git(self.root, ["apply", "--check", "--whitespace=nowarn", "-"], input_text=normalized)
        if checked.returncode == 0:
            applied = _run_git(self.root, ["apply", "--whitespace=nowarn", "-"], input_text=normalized)
            if applied.returncode == 0:
                for value in _patch_paths(normalized):
                    if (self.root / value).is_symlink():
                        self.rollback()
                        raise ToolError(f"symlink changes are not supported: {value}")
                check = _run_git(self.root, ["diff", "--check"])
                if check.returncode == 0:
                    self._last_test_patch_sha256 = None
                    self._last_successful_test_command = None
                    return ToolResult(
                        True,
                        f"applied patch to {len(set(_patch_paths(normalized)))} file(s)",
                        {"paths": _patch_paths(normalized)},
                    )

        # Fallback: attempt direct hunk replacement if git apply failed
        hunks = _extract_hunks_for_direct_apply(normalized)
        if hunks:
            success = True
            applied_files: set[str] = set()
            for rel_path, old_text, new_text in hunks:
                try:
                    _validate_target_path(rel_path)
                    target = _safe_relative(self.root, rel_path)
                    if not target.is_file() or target.is_symlink():
                        success = False
                        break
                    content = target.read_text(encoding="utf-8", errors="replace")
                    if content.count(old_text) == 1:
                        target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
                        applied_files.add(rel_path)
                    else:
                        success = False
                        break
                except Exception:
                    success = False
                    break
            if success and applied_files:
                self._last_test_patch_sha256 = None
                self._last_successful_test_command = None
                return ToolResult(
                    True,
                    f"applied patch hunks to {len(applied_files)} file(s)",
                    {"paths": sorted(applied_files)},
                )
            # Revert to checkpoint if fallback failed
            self.rollback()

        self.last_patch_error = checked.stderr.strip() or checked.stdout.strip()
        return ToolResult(
            False,
            f"patch rejected: {self.last_patch_error}. "
            "apply_patch requires a strict unified diff. "
            "Use edit_file(path, old_text, new_text) for bounded deterministic source editing instead.",
            {"error": "patch_check_failed"},
        )

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
                unfiltered, warning_msg = _is_unfiltered_test_suite_run(command)
                if unfiltered:
                    return ToolResult(
                        False,
                        warning_msg,
                        {"error": "unfiltered_test_suite", "failure_class": "test_failure"},
                    )
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
            output += (
                f"\n[timeout after {timeout}s: command timed out. In large repositories, "
                "running without a test filter times out. Specify a targeted test app or test file "
                "(e.g. 'python tests/runtests.py <app_name>' or 'python -m pytest <test_path>').]"
            )
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
            marker in lower for marker in (
                "cannot connect to the docker daemon",
                "is the docker daemon running",
                "docker daemon",
                "error during connect",
                "failed to dial",
                "permission denied while trying to connect",
            )
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
                "run a test command successfully with run_tests after the latest edit before submitting",
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
        # The task workspace is disposable; remove untracked build output
        # while excluding pyc/pycache that may have host permission constraints.
        cleaned = _run_git(self.root, ["clean", "-fd", "-e", "*.pyc", "-e", "__pycache__"])
        if cleaned.returncode != 0 and "permission denied" not in cleaned.stderr.lower():
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
        {"type": "function", "function": {"name": "edit_file", "description": "Safely replace an exact block of code (old_text) with new code (new_text) in a non-test source file. Include enough surrounding lines in old_text so it matches uniquely. Do not include line numbers or prefixes like '123: ' in old_text or new_text. Preferred over apply_patch for making changes.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative path to the file to edit."}, "old_text": {"type": "string", "description": "Exact text to replace in the file (without line numbers)."}, "new_text": {"type": "string", "description": "Replacement text to insert (without line numbers)."}}, "required": ["path", "old_text", "new_text"]}}},
        {"type": "function", "function": {"name": "apply_patch", "description": "Apply a unified diff to non-test source files. Inspect first and keep the patch minimal.", "parameters": {"type": "object", "properties": {"patch": {"type": "string"}}, "required": ["patch"]}}},
        {"type": "function", "function": {"name": "run_tests", "description": "Run a bounded repository-native test command. Use a declared alias (" + ", ".join(commands) + ") or a targeted pytest/unittest/Django test command; shell composition and destructive commands are rejected.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_diff", "description": "Inspect the current source diff before submitting.", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "rollback", "description": "Restore the latest pre-edit checkpoint only in case of catastrophic failure. Do NOT use rollback for normal test assertion failures; use edit_file to refine your code instead.", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "submit_patch", "description": "Seal the current patch for clean replay validation after all checks pass.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    ]

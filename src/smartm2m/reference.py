"""Integration boundary for the unmodified mini-swe-agent reference arm."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sysconfig
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import ExperimentConfig, TaskSpec


@dataclass
class ReferenceRun:
    status: str
    command: list[str]
    returncode: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    output_path: str
    reason: str = ""
    working_directory: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _task_filter(tasks: tuple[TaskSpec, ...]) -> str:
    return "^(?:" + "|".join(re.escape(task.instance_id) for task in tasks) + ")$"


def _redacted_result(result: ReferenceRun) -> dict[str, Any]:
    payload = result.as_dict()
    for field in ("stdout", "stderr", "reason"):
        payload[field] = re.sub(
            r"(?i)(authorization\s*:\s*bearer\s+|api[_-]?key\s*[=:]\s*|token\s*[=:]\s*)[^\s\"']+",
            r"\1[REDACTED]",
            str(payload.get(field, "")),
        )
    return payload


def _resolve_executable(executable: str) -> str:
    """Resolve a user-installed console script without changing its code."""
    found = shutil.which(executable)
    if found:
        return found
    candidate = Path(sysconfig.get_path("scripts", scheme="posix_user")) / executable
    if candidate.is_file() and candidate.stat().st_mode & 0o111:
        return str(candidate)
    return executable


class ReferenceRunner:
    """Run stock mini-extra in batch mode without importing or altering it."""

    def __init__(self, config: ExperimentConfig):
        self.config = config

    def _reference_config_path(self) -> str:
        configured = self.config.reference.config_path
        if not configured:
            return ""
        candidate = Path(configured)
        if candidate.is_absolute():
            return str(candidate)
        repo_root = self.config.config_path.parent.parent
        for base in (self.config.config_path.parent, repo_root):
            resolved = (base / candidate).resolve()
            if resolved.is_file():
                return str(resolved)
        return configured

    def _environment(self) -> dict[str, str]:
        environment = {**os.environ, "PAGER": "cat", "CI": "1"}
        key = os.environ.get(self.config.model.api_key_env)
        if key:
            # The locked default model uses LiteLLM's openai-compatible route.
            # Keep the credential in the environment; never put it in argv or artifacts.
            environment["OPENAI_API_KEY"] = key
        environment["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = str(self.config.model.max_retries + 1)
        return environment

    def command(self, output_dir: Path, *, dataset_path: str | None = None) -> list[str]:
        reference = self.config.reference
        output_dir.mkdir(parents=True, exist_ok=True)
        reference_config = self._reference_config_path()
        subset = dataset_path or reference.subset
        if reference.command_template:
            rendered = reference.command_template.format(
                model=self.config.model.model,
                subset=subset,
                split=reference.split,
                workers=reference.workers,
                base_url=self.config.model.base_url,
                temperature=self.config.model.temperature,
                seed=self.config.model.seed if self.config.model.seed is not None else "null",
                max_tokens=self.config.model.max_tokens,
                timeout=self.config.model.timeout_seconds,
                output=str(output_dir),
                config=reference.config_path,
                reference_config=reference_config,
                task_filter=_task_filter(self.config.tasks),
            )
            return shlex.split(rendered)
        command = [
            reference.executable,
            "swebench",
            "--model", self.config.model.model,
            "--subset", subset,
            "--split", reference.split,
            "--workers", str(reference.workers),
            "--filter", _task_filter(self.config.tasks),
            "--output", str(output_dir),
        ]
        if reference_config:
            command.extend(["--config", reference_config])
        return command

    def run(
        self,
        output_dir: str | Path,
        *,
        dry_run: bool = False,
        dataset_path: str | None = None,
    ) -> ReferenceRun:
        destination = Path(output_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        command = self.command(destination, dataset_path=dataset_path)
        if dry_run:
            return ReferenceRun(
                "dry_run", command, None, 0.0, "", "", str(destination),
                working_directory=str(destination),
            )
        executable = _resolve_executable(command[0])
        command[0] = executable
        if not Path(executable).is_absolute() and shutil.which(executable) is None:
            result = ReferenceRun(
                "unavailable", command, None, 0.0, "", "", str(destination),
                f"executable not found: {command[0]}",
                str(destination),
            )
            (destination / "reference-run.json").write_text(
                json.dumps(_redacted_result(result), indent=2) + "\n", encoding="utf-8"
            )
            return result
        started = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment(),
                cwd=destination,
                timeout=max(300, self.config.baseline.wall_time_seconds * max(1, len(self.config.tasks))),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timeout_stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            timeout_stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            result = ReferenceRun(
                "timeout",
                command,
                None,
                time.monotonic() - started,
                timeout_stdout,
                timeout_stderr,
                str(destination),
                "reference process timeout",
                str(destination),
            )
            (destination / "reference-run.json").write_text(
                json.dumps(_redacted_result(result), indent=2) + "\n", encoding="utf-8"
            )
            return result
        except OSError as exc:
            result = ReferenceRun(
                "error", command, None, time.monotonic() - started, "", str(exc),
                str(destination), str(exc), str(destination),
            )
            (destination / "reference-run.json").write_text(
                json.dumps(_redacted_result(result), indent=2) + "\n", encoding="utf-8"
            )
            return result
        status = "completed" if proc.returncode == 0 else "failed"
        result = ReferenceRun(
            status, command, proc.returncode, time.monotonic() - started,
            proc.stdout, proc.stderr, str(destination), working_directory=str(destination),
        )
        (destination / "reference-run.json").write_text(
            json.dumps(_redacted_result(result), indent=2) + "\n", encoding="utf-8"
        )
        return result


def find_prediction_file(root: str | Path) -> Path | None:
    base = Path(root)
    candidates = [base / "preds.jsonl", base / "preds.json", base / "all_preds.jsonl"]
    candidates.extend(sorted(base.rglob("preds.jsonl")))
    candidates.extend(sorted(base.rglob("preds.json")))
    return next((path for path in candidates if path.is_file()), None)


def load_prediction_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read mini's JSON object output or a standard JSONL prediction file."""
    source = Path(path)
    if source.suffix == ".json":
        parsed = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            rows: list[dict[str, Any]] = []
            for instance_id, value in parsed.items():
                if isinstance(value, dict):
                    rows.append({**value, "instance_id": value.get("instance_id", instance_id)})
            return rows
        if isinstance(parsed, list):
            return [value for value in parsed if isinstance(value, dict)]
        return []
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows

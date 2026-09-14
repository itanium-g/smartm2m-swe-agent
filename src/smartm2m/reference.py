"""Integration boundary for the unmodified mini-swe-agent reference arm."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _task_filter(tasks: tuple[TaskSpec, ...]) -> str:
    return "^(?:" + "|".join(re.escape(task.instance_id) for task in tasks) + ")$"


class ReferenceRunner:
    """Run stock mini-extra in batch mode without importing or altering it."""

    def __init__(self, config: ExperimentConfig):
        self.config = config

    def command(self, output_dir: Path) -> list[str]:
        reference = self.config.reference
        output_dir.mkdir(parents=True, exist_ok=True)
        if reference.command_template:
            rendered = reference.command_template.format(
                model=self.config.model.model,
                subset=reference.subset,
                split=reference.split,
                output=str(output_dir),
                config=reference.config_path,
                task_filter=_task_filter(self.config.tasks),
            )
            return shlex.split(rendered)
        command = [
            reference.executable,
            "swebench",
            "--model", self.config.model.model,
            "--subset", reference.subset,
            "--split", reference.split,
            "--workers", str(reference.workers),
            "--filter", _task_filter(self.config.tasks),
            "--output", str(output_dir),
        ]
        if reference.config_path:
            command.extend(["--config", reference.config_path])
        return command

    def run(self, output_dir: str | Path, *, dry_run: bool = False) -> ReferenceRun:
        destination = Path(output_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        command = self.command(destination)
        if dry_run:
            return ReferenceRun("dry_run", command, None, 0.0, "", "", str(destination))
        if shutil.which(command[0]) is None:
            return ReferenceRun(
                "unavailable", command, None, 0.0, "", "", str(destination),
                f"executable not found: {command[0]}",
            )
        started = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "PAGER": "cat", "CI": "1"},
                check=False,
            )
        except OSError as exc:
            return ReferenceRun("error", command, None, time.monotonic() - started, "", str(exc), str(destination), str(exc))
        status = "completed" if proc.returncode == 0 else "failed"
        result = ReferenceRun(status, command, proc.returncode, time.monotonic() - started, proc.stdout, proc.stderr, str(destination))
        (destination / "reference-run.json").write_text(
            json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        return result


def find_prediction_file(root: str | Path) -> Path | None:
    base = Path(root)
    candidates = [base / "preds.jsonl", base / "preds.json", base / "all_preds.jsonl"]
    candidates.extend(sorted(base.rglob("preds.jsonl")))
    candidates.extend(sorted(base.rglob("preds.json")))
    return next((path for path in candidates if path.is_file()), None)

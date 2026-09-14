"""Official SWE-bench evaluator boundary and prediction serialization."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import ExperimentConfig


@dataclass
class EvaluationRun:
    status: str
    command: list[str]
    returncode: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    run_id: str
    reason: str = ""
    working_directory: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _patch_text(value: Any) -> str:
    return "" if value is None else str(value)


def write_predictions(
    path: str | Path,
    rows: Iterable[dict[str, Any]],
    *,
    model_name: str,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps({
                "instance_id": str(row["instance_id"]),
                "model_name_or_path": model_name,
                "model_patch": _patch_text(row.get("model_patch", row.get("patch", ""))),
            }, ensure_ascii=False) + "\n")


class OfficialEvaluator:
    def __init__(self, config: ExperimentConfig):
        self.config = config

    def command(self, predictions: Path, run_id: str) -> list[str]:
        if self.config.official_evaluator_command:
            return shlex.split(self.config.official_evaluator_command.format(
                dataset_name=self.config.dataset_name,
                predictions=str(predictions),
                run_id=run_id,
                split=self.config.reference.split,
            ))
        return [
            sys.executable,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            self.config.dataset_name,
            "--split",
            self.config.reference.split,
            "--predictions_path",
            str(predictions),
            "--max_workers",
            "1",
            "--run_id",
            run_id,
        ]

    def run(self, predictions: str | Path, run_id: str, output_dir: str | Path) -> EvaluationRun:
        prediction_path = Path(predictions).resolve()
        destination = Path(output_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        command = self.command(prediction_path, run_id)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "PAGER": "cat", "CI": "1"},
                cwd=destination,
                timeout=max(1800, 1800 * max(1, len(self.config.tasks))),
                check=False,
            )
            result = EvaluationRun(
                "completed" if proc.returncode == 0 else "failed",
                command,
                proc.returncode,
                time.monotonic() - started,
                proc.stdout,
                proc.stderr,
                run_id,
                "" if proc.returncode == 0 else "official evaluator returned non-zero",
                str(destination),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            result = EvaluationRun(
                "timeout", command, None, time.monotonic() - started, stdout, stderr, run_id,
                "official evaluator timeout",
                str(destination),
            )
        except OSError as exc:
            result = EvaluationRun(
                "unavailable", command, None, time.monotonic() - started, "", str(exc), run_id, str(exc), str(destination)
            )
        (destination / "evaluation-run.json").write_text(
            json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        return result

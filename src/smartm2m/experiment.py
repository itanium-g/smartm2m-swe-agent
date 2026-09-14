"""Experiment lifecycle: preflight, paired generation, evaluation, and audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import AgentResult, CustomAgent
from .config import ConfigError, ExperimentConfig, environment_summary
from .evaluator import OfficialEvaluator, write_predictions
from .model import OpenAICompatibleModel
from .reference import ReferenceRunner, find_prediction_file
from .reporting import (
    hash_result_bundle,
    load_records,
    outcomes_for_tasks,
    summary_for_pairs,
    write_summary,
)
from .task import prepared_workspace
from .tools import ToolRunner
from .validation import validate_clean_replay, write_validation


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _redact(value: str) -> str:
    replacements = [
        (r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key\s*[=:]\s*)[^\s\"']+", r"\1[REDACTED]"),
        (r"(?i)(token\s*[=:]\s*)[^\s\"']+", r"\1[REDACTED]"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    return value


def _utc_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"


def preflight(config: ExperimentConfig, *, allow_unresolved: bool = False) -> dict[str, Any]:
    manifest_issues = config.validate_manifest(allow_unresolved=True)
    unresolved_issues = list(manifest_issues)
    errors = [
        issue for issue in manifest_issues
        if not (allow_unresolved and issue.startswith("manifest has "))
    ]
    warnings: list[str] = []
    checks: dict[str, Any] = {
        "manifest_path": str(config.manifest_path),
        "manifest_sha256": hashlib.sha256(config.manifest_path.read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(config.config_path.read_bytes()).hexdigest(),
        "lock_fingerprint": config.lock_fingerprint(),
        "environment": environment_summary(),
        "tasks": len(config.tasks),
        "expected_count": config.expected_count,
        "unresolved_manifest_errors": unresolved_issues,
    }
    if not config.tasks:
        warnings.append("no runnable tasks are present; provide the employer-confirmed fixed manifest")
    for task in config.tasks:
        if task.repo_path and not Path(task.repo_path).expanduser().exists():
            errors.append(f"{task.instance_id}: repo_path does not exist: {task.repo_path}")
        if not task.repo_path and not task.repo_url:
            warnings.append(f"{task.instance_id}: no local repo_path/repo_url; execution will be blocked")
    if shutil.which(config.reference.executable) is None:
        warnings.append(f"reference executable is not installed: {config.reference.executable}")
    if not os.environ.get(config.model.api_key_env):
        warnings.append(
            f"model key is not set ({config.model.api_key_env}); generation will record provider_error"
        )
    checks["warnings"] = warnings
    checks["errors"] = errors
    checks["ok"] = not errors
    return checks


def _write_agent_artifacts(
    directory: Path,
    result: AgentResult,
    task: Any,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _json_write(directory / "agent.json", result.as_dict())
    _json_write(directory / "trajectory.json", {
        "instance_id": task.instance_id,
        "events": result.events,
        "generation_input": task.generation_projection(),
    })
    with (directory / "commands.jsonl").open("w", encoding="utf-8") as stream:
        for command in result.commands:
            safe = {**command, "output": _redact(str(command.get("output", "")))}
            stream.write(json.dumps(safe, ensure_ascii=False) + "\n")
    (directory / "candidate.patch").write_text(result.patch, encoding="utf-8")


def _custom_generation(config: ExperimentConfig, run_dir: Path) -> list[dict[str, Any]]:
    workspace_root = run_dir / "workspaces"
    model = OpenAICompatibleModel(config.model)
    rows: list[dict[str, Any]] = []
    for task in config.tasks:
        instance_dir = run_dir / "custom" / task.instance_id.replace("/", "__")
        try:
            with prepared_workspace(task, workspace_root) as workspace:
                runner = ToolRunner(
                    workspace,
                    task,
                    command_timeout=config.custom.command_timeout_seconds,
                    max_output_chars=config.custom.max_output_chars,
                )
                result = CustomAgent(
                    model,
                    arm=config.custom,
                    model_config=config.model,
                ).run(task, runner)
                _write_agent_artifacts(instance_dir, result, task)
                validation = None
                if result.patch:
                    validation = validate_clean_replay(
                        workspace,
                        task.test_commands[0],
                        timeout_seconds=config.custom.command_timeout_seconds,
                    )
                    write_validation(instance_dir / "validation.json", validation)
                row = result.as_dict()
                row["model_patch"] = result.patch
                row["validation_status"] = validation.status if validation else "not_run"
                rows.append(row)
        except Exception as exc:
            row = {
                "instance_id": task.instance_id,
                "status": "sandbox_error",
                "reason": str(exc),
                "turns": 0,
                "model_requests": 0,
                "estimated_cost_usd": None,
                "patch_sha256": hashlib.sha256(b"").hexdigest(),
                "model_patch": "",
                "validation_status": "not_run",
                "recovery_used": False,
            }
            _json_write(instance_dir / "agent.json", row)
            rows.append(row)
    rows_path = run_dir / "custom" / "generation.jsonl"
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    with rows_path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_predictions(run_dir / "custom" / "predictions.jsonl", rows, model_name=config.model.model)
    return rows


def _reference_generation(config: ExperimentConfig, run_dir: Path, result: Any) -> list[dict[str, Any]]:
    reference_dir = run_dir / "reference"
    source = find_prediction_file(result.output_path)
    rows_by_id: dict[str, dict[str, Any]] = {}
    if source:
        try:
            for line in source.read_text(encoding="utf-8").splitlines():
                value = json.loads(line)
                if value.get("instance_id"):
                    rows_by_id[str(value["instance_id"])] = value
            shutil.copy2(source, reference_dir / "predictions.raw.jsonl")
        except (OSError, json.JSONDecodeError):
            pass
    rows: list[dict[str, Any]] = []
    for task in config.tasks:
        value = rows_by_id.get(task.instance_id, {})
        patch = str(value.get("model_patch", ""))
        rows.append({
            "instance_id": task.instance_id,
            "status": "submitted" if patch else result.status,
            "reason": result.reason if not patch else "",
            "turns": None,
            "model_requests": None,
            "estimated_cost_usd": None,
            "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
            "model_patch": patch,
            "validation_status": "not_applicable_reference",
        })
    with (reference_dir / "generation.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_predictions(reference_dir / "predictions.jsonl", rows, model_name=config.model.model)
    return rows


def audit_run(run_dir: str | Path, config: ExperimentConfig) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    task_ids = [task.instance_id for task in config.tasks]
    baseline_generation = load_records(root / "reference" / "generation.jsonl")
    custom_generation = load_records(root / "custom" / "generation.jsonl")
    baseline_evaluation = load_records(root / "evaluation" / "reference")
    custom_evaluation = load_records(root / "evaluation" / "custom")
    baseline = outcomes_for_tasks(task_ids, baseline_generation, baseline_evaluation)
    custom = outcomes_for_tasks(task_ids, custom_generation, custom_evaluation)
    summary = summary_for_pairs(task_ids, baseline, custom, config.expected_count)
    summary["run_id"] = root.name
    summary["bundle_sha256_before_checksums"] = hash_result_bundle(root)
    write_summary(root / "summary.json", summary)
    _json_write(root / "summary.json", summary)
    return summary


def reproduce(
    config: ExperimentConfig,
    *,
    run_id: str | None = None,
    allow_unresolved: bool = False,
    dry_run_reference: bool = False,
) -> Path:
    checks = preflight(config, allow_unresolved=allow_unresolved)
    if not checks["ok"]:
        raise ConfigError("preflight failed: " + "; ".join(checks["errors"]))
    if not config.tasks:
        raise ConfigError("no runnable tasks are present; fill tasks/evaluation.json before reproduce")
    run_dir = config.results_root / (run_id or _utc_run_id(config.run_id_prefix))
    if run_dir.exists():
        raise ConfigError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    _json_write(run_dir / "preflight.json", checks)
    _json_write(run_dir / "manifest.json", {
        "run_id": run_dir.name,
        "protocol_version": config.protocol_version,
        "lock_fingerprint": config.lock_fingerprint(),
        "config_sha256": hashlib.sha256(config.config_path.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(config.manifest_path.read_bytes()).hexdigest(),
        "expected_count": config.expected_count,
        "tasks": [task.generation_projection() for task in config.tasks],
        "model": config.model.__dict__,
        "reference": config.reference.__dict__,
        "environment": environment_summary(),
    })
    (run_dir / "configs").mkdir()
    shutil.copy2(config.config_path, run_dir / "configs" / config.config_path.name)
    shutil.copy2(config.manifest_path, run_dir / "configs" / config.manifest_path.name)

    reference_result = ReferenceRunner(config).run(
        run_dir / "reference",
        dry_run=dry_run_reference,
    )
    _json_write(run_dir / "reference" / "run.json", reference_result.as_dict())
    _reference_generation(config, run_dir, reference_result)
    _custom_generation(config, run_dir)

    evaluator = OfficialEvaluator(config)
    evaluation = run_dir / "evaluation"
    evaluator.run(
        run_dir / "reference" / "predictions.jsonl",
        f"{run_dir.name}-reference",
        evaluation / "reference",
    )
    evaluator.run(
        run_dir / "custom" / "predictions.jsonl",
        f"{run_dir.name}-custom",
        evaluation / "custom",
    )
    summary = audit_run(run_dir, config)
    _json_write(run_dir / "run.json", {
        "run_id": run_dir.name,
        "status": "complete_with_explicit_failures",
        "summary": summary,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    _write_checksums(run_dir)
    return run_dir


def _write_checksums(root: Path) -> None:
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

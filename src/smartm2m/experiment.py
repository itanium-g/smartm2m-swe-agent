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
from .reference import ReferenceRunner, find_prediction_file, load_prediction_rows
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


def _redact_json(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_json(item) for key, item in value.items()}
    return value


def _utc_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"


def preflight(config: ExperimentConfig, *, allow_unresolved: bool = False) -> dict[str, Any]:
    manifest_issues = config.validate_manifest(allow_unresolved=True)
    unresolved_issues = list(manifest_issues)
    errors = [
        issue for issue in manifest_issues
        if not (allow_unresolved and not config.tasks and issue.startswith("manifest has "))
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
        if not task.base_commit:
            errors.append(f"{task.instance_id}: base_commit is required for a reproducible run")
        if task.repo_path and not Path(task.repo_path).expanduser().exists():
            errors.append(f"{task.instance_id}: repo_path does not exist: {task.repo_path}")
        if not task.repo_path and not task.repo_url:
            errors.append(f"{task.instance_id}: no local repo_path/repo_url")
    if shutil.which(config.reference.executable) is None:
        warnings.append(f"reference executable is not installed: {config.reference.executable}")
    if config.model.input_usd_per_million is None or config.model.output_usd_per_million is None:
        warnings.append("model pricing is incomplete; observed API spend and cost-limit parity cannot be verified")
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
        "events": _redact_json(result.events),
        "generation_input": _redact_json(task.generation_projection()),
    })
    with (directory / "commands.jsonl").open("w", encoding="utf-8") as stream:
        for command in result.commands:
            safe = _redact_json(command)
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
                if result.patch and result.status == "submitted":
                    validation = validate_clean_replay(
                        workspace,
                        task.test_commands[0],
                        timeout_seconds=config.custom.command_timeout_seconds,
                        setup_commands=task.setup_commands,
                    )
                    write_validation(instance_dir / "validation.json", validation)
                row = result.as_dict()
                sealed = result.patch if validation and validation.status == "passed" else ""
                row["model_patch"] = sealed
                row["validation_status"] = validation.status if validation else "not_run"
                if result.patch and result.status == "submitted" and not sealed:
                    row["status"] = "validation_failed"
                    row["reason"] = validation.reason if validation else "clean replay was not run"
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
            for value in load_prediction_rows(source):
                if value.get("instance_id"):
                    rows_by_id[str(value["instance_id"])] = value
            shutil.copy2(source, reference_dir / f"predictions.raw{source.suffix}")
        except (OSError, json.JSONDecodeError):
            pass
    rows: list[dict[str, Any]] = []
    for task in config.tasks:
        value = rows_by_id.get(task.instance_id, {})
        raw_patch = value.get("model_patch", value.get("patch", ""))
        patch = "" if raw_patch is None else str(raw_patch)
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
    selected_run_id = run_id or _utc_run_id(config.run_id_prefix)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", selected_run_id):
        raise ConfigError("run_id must contain only letters, numbers, '.', '_' or '-' and be at most 128 characters")
    run_dir = config.results_root / selected_run_id
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
    custom_rows = _custom_generation(config, run_dir)
    usage_rows = [
        {
            "arm": "custom",
            "instance_id": row.get("instance_id"),
            "model_requests": row.get("model_requests"),
            "estimated_cost_usd": row.get("estimated_cost_usd"),
        }
        for row in custom_rows
    ]
    (run_dir / "usage.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in usage_rows) + "\n",
        encoding="utf-8",
    )
    (run_dir / "contamination.md").write_text(
        "# Contamination review\n\n"
        "Primary generation artifacts are retained under reference/ and custom/. "
        "Complete the post-sealing trajectory review before publishing benchmark claims. "
        "The current run does not infer that a patch difference proves absence of memorization.\n",
        encoding="utf-8",
    )

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

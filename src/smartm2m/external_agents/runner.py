"""Benchmark execution engine, task sequencing, resume support, and paired evaluation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..config import ConfigError, environment_summary
from ..dataset import materialize_pinned_dataset
from ..evaluator import OfficialEvaluator, write_predictions
from ..reporting import _evaluation_value, load_records
from .antigravity import AntigravityAgent
from .base import ExternalAgent
from .codex import CodexAgent
from .config import ExternalAgentsConfig
from .metadata import ExternalTaskResult, redact_json, write_task_artifacts
from .prompts import hash_prompt, render_prompt
from .workspace import extract_workspace_diff, get_git_head, get_git_status, prepare_clean_workspace


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dry_run(config: ExternalAgentsConfig) -> dict[str, Any]:
    """Validate all prerequisites, executables, task fingerprints, and docker images."""
    errors = config.validate_manifest()
    warnings: list[str] = []

    codex = CodexAgent(
        executable=config.codex_executable,
        model=config.codex_model,
        sandbox=config.codex_sandbox,
        ephemeral=config.codex_ephemeral,
        ignore_user_config=config.codex_ignore_user_config,
        ignore_rules=config.codex_ignore_rules,
    )
    codex_ver = codex.detect_version()

    agy = AntigravityAgent(
        executable=config.agy_executable,
        model=config.agy_model,
        effort=config.agy_effort,
        output_format=config.agy_output_format,
        dangerously_skip_permissions=config.agy_dangerously_skip_permissions,
        disable_slash_commands=config.agy_disable_slash_commands,
    )
    agy_ver = agy.detect_version()

    # Probe Docker
    docker_available = shutil.which("docker") is not None
    docker_version = ""
    if docker_available:
        try:
            res = subprocess.run(["docker", "--version"], text=True, capture_output=True, timeout=10, check=False)
            docker_version = res.stdout.strip()
        except Exception as exc:
            warnings.append(f"docker probe failed: {exc}")
    else:
        warnings.append("docker is not installed on host; container test helpers will fallback to host")

    # Check required task images
    task_images: dict[str, bool] = {}
    if docker_available:
        for t in config.tasks:
            if t.image:
                try:
                    inspect_res = subprocess.run(
                        ["docker", "image", "inspect", t.image],
                        text=True,
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    task_images[t.image] = inspect_res.returncode == 0
                except Exception:
                    task_images[t.image] = False

    missing_images = [img for img, ok in task_images.items() if not ok]
    if missing_images:
        warnings.append(f"missing local SWE-bench docker images: {', '.join(missing_images)}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "protocol_version": config.protocol_version,
        "manifest_path": str(config.manifest_path),
        "manifest_sha256": config.manifest_sha256,
        "config_sha256": config.config_sha256,
        "task_count": len(config.tasks),
        "expected_count": config.expected_count,
        "codex": {
            "executable": codex.resolve_executable(),
            "version": codex_ver,
            "configured_model": config.codex_model,
            "sandbox": config.codex_sandbox,
        },
        "agy": {
            "executable": agy.resolve_executable(),
            "version": agy_ver,
            "configured_model": config.agy_model,
            "effort": config.agy_effort,
        },
        "docker": {
            "available": docker_available,
            "version": docker_version,
            "images_verified": len(task_images) - len(missing_images),
            "missing_images": missing_images,
        },
        "environment": environment_summary(),
    }


def run_task_attempt(
    agent: ExternalAgent,
    task: Any,
    config: ExternalAgentsConfig,
    workspaces_dir: Path,
    task_output_dir: Path,
) -> ExternalTaskResult:
    """Run a single task attempt in a completely fresh, isolated workspace."""
    start_ts = _utc_iso()
    t0 = time.monotonic()

    with prepare_clean_workspace(task, workspaces_dir, inject_helper=True) as workspace:
        git_head_before = get_git_head(workspace)
        git_status_before = get_git_status(workspace)

        prompt_str = render_prompt(task.problem_statement, include_test_helper=True)
        p_sha = hash_prompt(prompt_str)

        cmd = agent.build_command(prompt_str, workspace)
        env = agent.build_env(workspace)

        timed_out = False
        exit_code: int | None = None
        stdout_raw = ""
        stderr_raw = ""

        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=config.wall_time_seconds,
                check=False,
            )
            exit_code = proc.returncode
            stdout_raw = proc.stdout or ""
            stderr_raw = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_raw = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode(errors="replace") if exc.stdout else "")
            stderr_raw = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode(errors="replace") if exc.stderr else "")
            exit_code = None
        except Exception as exc:
            stderr_raw = f"process spawn failed: {exc}"
            exit_code = 127

        wall_duration = time.monotonic() - t0
        end_ts = _utc_iso()

        # Authoritative git diff from working tree against base commit
        patch = extract_workspace_diff(workspace, task.base_commit)
        patch_sha = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        git_status_after = get_git_status(workspace)

        # Parse structured stream
        usage, commands, session_id, reported_model = agent.parse_stream(stdout_raw)

        # Detect provider block
        is_blocked, block_reason = agent.detect_provider_block(stdout_raw, stderr_raw, exit_code or 0)

        if is_blocked:
            term_status = "provider_blocked"
            term_reason = block_reason
        elif timed_out:
            term_status = "timed_out"
            term_reason = f"wall timeout exceeded {config.wall_time_seconds}s"
        elif exit_code != 0:
            term_status = "generation_failed"
            term_reason = f"process exited with code {exit_code}"
        else:
            term_status = "generated"
            term_reason = ""

        result = ExternalTaskResult(
            instance_id=task.instance_id,
            agent=agent.name,
            provider=agent.provider,
            cli_version=agent.detect_version(),
            configured_model=agent.configured_model,
            reported_model=reported_model,
            effort_or_reasoning_setting=agent.effort,
            base_commit=task.base_commit,
            workspace_path=str(workspace),
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            wall_duration_seconds=wall_duration,
            exit_code=exit_code,
            timed_out=timed_out,
            terminal_status=term_status,
            termination_reason=term_reason,
            stdout_file="stdout.log",
            stderr_file="stderr.log",
            events_file="events.jsonl",
            patch_file="patch.diff",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            thinking_tokens=usage.thinking_tokens,
            cache_tokens=usage.cache_tokens,
            total_tokens=usage.total_tokens,
            patch=patch,
            patch_sha256=patch_sha,
            prompt_sha256=p_sha,
            config_sha256=config.config_sha256,
            git_head_before=git_head_before,
            git_status_before=git_status_before,
            git_status_after=git_status_after,
            evaluator_status="not_evaluated",
            commands_count=len(commands),
        )

        write_task_artifacts(
            task_output_dir,
            result,
            stdout_raw=stdout_raw,
            stderr_raw=stderr_raw,
            commands=commands,
        )
        return result


def run_agent_benchmark(
    agent: ExternalAgent,
    config: ExternalAgentsConfig,
    agent_dir: Path,
    workspaces_dir: Path,
    *,
    resume: bool = False,
    target_task_id: str | None = None,
) -> dict[str, Any]:
    """Execute the benchmark tasks for one agent arm sequentially."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    tasks_root = agent_dir / "tasks"
    tasks_root.mkdir(parents=True, exist_ok=True)

    results: list[ExternalTaskResult] = []
    agent_status = "completed"
    blocker_reason = ""

    tasks_to_run = config.tasks
    if target_task_id:
        tasks_to_run = tuple(t for t in config.tasks if t.instance_id == target_task_id)
        if not tasks_to_run:
            raise ConfigError(f"target task {target_task_id} not found in manifest")

    for task in tasks_to_run:
        instance_dir = tasks_root / task.instance_id.replace("/", "__")
        meta_file = instance_dir / "metadata.json"

        # Check resume condition
        if resume and meta_file.is_file():
            try:
                saved = json.loads(meta_file.read_text(encoding="utf-8"))
                saved_res = ExternalTaskResult.from_dict(saved)
                # If attempt previously finished (generated, generation_failed, or timed_out), keep it
                if saved_res.terminal_status in {"generated", "generation_failed", "timed_out"}:
                    results.append(saved_res)
                    continue
            except Exception:
                pass  # Rerun corrupted task metadata

        task_result = run_task_attempt(agent, task, config, workspaces_dir, instance_dir)
        results.append(task_result)

        if task_result.terminal_status == "provider_blocked":
            agent_status = "provider_blocked"
            blocker_reason = task_result.termination_reason
            break

    # If tasks remain unattempted due to blocker or target filter
    if len(results) < len(config.tasks) and not target_task_id:
        if agent_status != "provider_blocked":
            agent_status = "incomplete"

    # Write predictions.jsonl
    predictions_path = agent_dir / "predictions.jsonl"
    prediction_rows = [
        {
            "instance_id": r.instance_id,
            "model_name_or_path": r.configured_model,
            "model_patch": r.patch,
        }
        for r in results
    ]
    write_predictions(predictions_path, prediction_rows, model_name=agent.configured_model)

    # Write metadata.json
    agent_meta = {
        "agent": agent.name,
        "provider": agent.provider,
        "cli_version": agent.detect_version(),
        "configured_model": agent.configured_model,
        "effort_or_reasoning_setting": agent.effort,
        "status": agent_status,
        "blocker_reason": blocker_reason,
        "completed_tasks": len(results),
        "expected_tasks": len(config.tasks),
        "tasks": [r.as_dict() for r in results],
    }
    (agent_dir / "metadata.json").write_text(
        json.dumps(redact_json(agent_meta), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Write arm summary
    summary_data = {
        "agent": agent.name,
        "status": agent_status,
        "tasks_attempted": len(results),
        "expected_tasks": len(config.tasks),
        "generated_patches": sum(1 for r in results if r.patch.strip()),
        "empty_patches": sum(1 for r in results if not r.patch.strip()),
    }
    (agent_dir / "summary.json").write_text(json.dumps(summary_data, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        f"# {agent.name.upper()} Benchmark Arm Summary",
        "",
        f"- Status: **{agent_status}**",
        f"- Model: `{agent.configured_model}`",
        f"- Attempted: **{len(results)}/{len(config.tasks)}**",
        f"- Generated non-empty patches: **{summary_data['generated_patches']}**",
        "",
        "| Instance | Status | Exit Code | Wall Time (s) | Patch SHA-256 | Total Tokens |",
        "|---|---|---:|---:|---|---:|",
    ]
    for r in results:
        md_lines.append(
            f"| {r.instance_id} | {r.terminal_status} | {r.exit_code} | "
            f"{r.wall_duration_seconds:.1f} | {r.patch_sha256[:12]} | {r.total_tokens or 'n/a'} |"
        )
    (agent_dir / "summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return agent_meta


def evaluate_arm(
    config: ExternalAgentsConfig,
    predictions_path: Path,
    eval_output_dir: Path,
    evaluator_dataset_path: Path | None,
    run_label: str,
) -> None:
    """Run the official SWE-bench evaluator on an arm's predictions."""
    eval_config = SimpleNamespace(
        dataset_name=config.dataset_name,
        official_evaluator_command="",
        reference=SimpleNamespace(split=config.split),
        tasks=config.tasks,
    )
    evaluator = OfficialEvaluator(eval_config)  # type: ignore[arg-type]
    evaluator.run(
        predictions=predictions_path,
        run_id=run_label,
        output_dir=eval_output_dir,
        dataset_name=str(evaluator_dataset_path) if evaluator_dataset_path else None,
    )


def build_comparison_report(
    config: ExternalAgentsConfig,
    run_dir: Path,
    codex_meta: dict[str, Any] | None,
    agy_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build paired comparison summary and markdown from official evaluation records."""
    codex_eval = load_records(run_dir / "evaluation" / "codex")
    agy_eval = load_records(run_dir / "evaluation" / "agy")

    codex_tasks = {t["instance_id"]: t for t in (codex_meta or {}).get("tasks", [])}
    agy_tasks = {t["instance_id"]: t for t in (agy_meta or {}).get("tasks", [])}

    rows: list[dict[str, Any]] = []
    both_solved = 0
    codex_only = 0
    agy_only = 0
    neither = 0

    codex_resolved_count = 0
    agy_resolved_count = 0

    for task in config.tasks:
        iid = task.instance_id
        c_task = codex_tasks.get(iid, {})
        a_task = agy_tasks.get(iid, {})

        c_eval_record = codex_eval.get(iid, {})
        a_eval_record = agy_eval.get(iid, {})

        c_res, c_reason = _evaluation_value(c_eval_record) if c_eval_record else (False, "not evaluated")
        a_res, a_reason = _evaluation_value(a_eval_record) if a_eval_record else (False, "not evaluated")

        if c_res:
            codex_resolved_count += 1
        if a_res:
            agy_resolved_count += 1

        if c_res and a_res:
            both_solved += 1
        elif c_res:
            codex_only += 1
        elif a_res:
            agy_only += 1
        else:
            neither += 1

        rows.append({
            "instance_id": iid,
            "base_commit": task.base_commit,
            "codex_status": c_task.get("terminal_status", "not_run"),
            "codex_patch_sha": c_task.get("patch_sha256", ""),
            "codex_resolved": c_res,
            "codex_eval_reason": c_reason,
            "agy_status": a_task.get("terminal_status", "not_run"),
            "agy_patch_sha": a_task.get("patch_sha256", ""),
            "agy_resolved": a_res,
            "agy_eval_reason": a_reason,
        })

    total_expected = config.expected_count
    comparison = {
        "run_id": run_dir.name,
        "protocol_version": config.protocol_version,
        "expected_count": total_expected,
        "codex": {
            "model": config.codex_model,
            "resolved": codex_resolved_count,
            "percent": round(100.0 * codex_resolved_count / total_expected, 2) if total_expected else 0.0,
            "status": (codex_meta or {}).get("status", "unknown"),
        },
        "agy": {
            "model": config.agy_model,
            "effort": config.agy_effort,
            "resolved": agy_resolved_count,
            "percent": round(100.0 * agy_resolved_count / total_expected, 2) if total_expected else 0.0,
            "status": (agy_meta or {}).get("status", "unknown"),
        },
        "pairs": {
            "both_solved": both_solved,
            "codex_only": codex_only,
            "agy_only": agy_only,
            "neither": neither,
        },
        "tasks": rows,
    }

    # Write comparison.json
    (run_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Write comparison.md
    c_status = comparison["codex"]["status"]
    a_status = comparison["agy"]["status"]

    md_lines = [
        "# Exploratory External Coding-Agent Benchmark: Codex CLI vs Antigravity CLI",
        "",
        "> [!NOTE]",
        "> This exploratory benchmark evaluates OpenAI Codex CLI and Google Antigravity CLI (`agy`) as complete coding-agent harnesses on the same frozen eight-task SWE-bench Verified sample under identical workspace, time, and evaluation conditions. Because each CLI incorporates its own system prompts, tool designs, context handling, and model routing, this is not an apples-to-apples single-model comparison.",
        "",
        "## Overall Results",
        "",
    ]

    if c_status != "completed":
        md_lines.append(f"- **Codex CLI (`{config.codex_model}`):** Run status `{c_status}` (incomplete; no headline score).")
    else:
        md_lines.append(
            f"- **Codex CLI (`{config.codex_model}`):** **{codex_resolved_count}/{total_expected} resolved ({comparison['codex']['percent']}%)**"
        )

    if a_status != "completed":
        md_lines.append(f"- **Antigravity CLI (`{config.agy_model}`):** Run status `{a_status}` (incomplete; no headline score).")
    else:
        md_lines.append(
            f"- **Antigravity CLI (`{config.agy_model}`):** **{agy_resolved_count}/{total_expected} resolved ({comparison['agy']['percent']}%)**"
        )

    md_lines.extend([
        "",
        "## Paired Outcomes",
        "",
        "| Both solved | Codex only | AGY only | Neither verified |",
        "|---:|---:|---:|---:|",
        f"| {both_solved} | {codex_only} | {agy_only} | {neither} |",
        "",
        "## Task-Level Verification",
        "",
        "| Instance | Codex Status | Codex Resolved | AGY Status | AGY Resolved | Notes |",
        "|---|---|---:|---|---:|---|",
    ])
    for r in rows:
        notes = []
        if r["codex_eval_reason"]:
            notes.append(f"Codex: {r['codex_eval_reason']}")
        if r["agy_eval_reason"]:
            notes.append(f"AGY: {r['agy_eval_reason']}")
        notes_str = "; ".join(notes).replace("|", "\\|")
        md_lines.append(
            f"| {r['instance_id']} | {r['codex_status']} | {'yes' if r['codex_resolved'] else 'no'} | "
            f"{r['agy_status']} | {'yes' if r['agy_resolved'] else 'no'} | {notes_str} |"
        )

    (run_dir / "comparison.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return comparison


def write_run_checksums(root: Path) -> None:
    """Generate sha256 checksums file for all retained artifacts in run bundle."""
    lines: list[str] = []
    disposable_dirs = {"workspaces", "dataset-evaluation", "__pycache__", ".pytest_cache", ".ruff_cache", ".git"}
    for path in sorted(root.rglob("*")):
        if disposable_dirs.intersection(path.relative_to(root).parts[:-1]):
            continue
        if path.is_file() and path.name != "checksums.sha256":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(
    config: ExternalAgentsConfig,
    *,
    agent_choice: str = "all",  # "codex", "agy", "all"
    run_id: str | None = None,
    resume: bool = False,
    dry_run_only: bool = False,
    generation_only: bool = False,
    evaluate_only: bool = False,
    target_task_id: str | None = None,
) -> Path:
    """Execute the full external agents benchmark workflow."""
    if dry_run_only:
        report = dry_run(config)
        print(json.dumps(report, indent=2))
        return config.results_root

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    selected_run_id = run_id or f"cli-comparison-{stamp}"
    run_dir = config.results_root / selected_run_id

    if evaluate_only:
        if not run_dir.exists():
            raise ConfigError(f"run directory does not exist for evaluate-only: {run_dir}")
        # Materialize evaluator dataset if needed
        eval_ds = materialize_pinned_dataset(
            config,  # type: ignore[arg-type]
            run_dir / "dataset-evaluation",
            evaluator_only=True,
        )
        codex_preds = run_dir / "codex" / "predictions.jsonl"
        agy_preds = run_dir / "agy" / "predictions.jsonl"
        if codex_preds.exists():
            evaluate_arm(config, codex_preds, run_dir / "evaluation" / "codex", Path(eval_ds.path), f"{run_dir.name}-codex")
        if agy_preds.exists():
            evaluate_arm(config, agy_preds, run_dir / "evaluation" / "agy", Path(eval_ds.path), f"{run_dir.name}-agy")

        codex_meta_path = run_dir / "codex" / "metadata.json"
        agy_meta_path = run_dir / "agy" / "metadata.json"
        codex_meta = json.loads(codex_meta_path.read_text()) if codex_meta_path.exists() else None
        agy_meta = json.loads(agy_meta_path.read_text()) if agy_meta_path.exists() else None

        build_comparison_report(config, run_dir, codex_meta, agy_meta)
        write_run_checksums(run_dir)
        return run_dir

    if not resume and run_dir.exists():
        raise ConfigError(f"run directory already exists: {run_dir}. Use --resume to continue an interrupted run.")

    run_dir.mkdir(parents=True, exist_ok=True)
    workspaces_dir = run_dir / "workspaces"

    # Manifest and config retention
    manifest_record = {
        "run_id": run_dir.name,
        "protocol_version": config.protocol_version,
        "created_at": _utc_iso(),
        "config_sha256": config.config_sha256,
        "manifest_sha256": config.manifest_sha256,
        "expected_count": config.expected_count,
        "agent_choice": agent_choice,
        "tasks": [t.generation_projection() for t in config.tasks],
        "codex": {
            "model": config.codex_model,
            "sandbox": config.codex_sandbox,
        },
        "agy": {
            "model": config.agy_model,
            "effort": config.agy_effort,
        },
        "environment": environment_summary(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest_record, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(config.config_path, run_dir / "config.yaml")

    common_prompt_sample = render_prompt("{{problem_statement}}", include_test_helper=True)
    (run_dir / "prompt.txt").write_text(common_prompt_sample, encoding="utf-8")

    codex_meta: dict[str, Any] | None = None
    agy_meta: dict[str, Any] | None = None

    # Sequential execution: Codex first, then AGY
    if agent_choice in {"codex", "all"}:
        codex_agent = CodexAgent(
            executable=config.codex_executable,
            model=config.codex_model,
            sandbox=config.codex_sandbox,
            ephemeral=config.codex_ephemeral,
            structured_output=config.codex_structured_output,
            ignore_user_config=config.codex_ignore_user_config,
            ignore_rules=config.codex_ignore_rules,
            reasoning_effort=config.codex_effort,
        )
        codex_meta = run_agent_benchmark(
            codex_agent,
            config,
            run_dir / "codex",
            workspaces_dir,
            resume=resume,
            target_task_id=target_task_id,
        )

    if agent_choice in {"agy", "all"}:
        agy_agent = AntigravityAgent(
            executable=config.agy_executable,
            model=config.agy_model,
            effort=config.agy_effort,
            output_format=config.agy_output_format,
            dangerously_skip_permissions=config.agy_dangerously_skip_permissions,
            disable_slash_commands=config.agy_disable_slash_commands,
        )
        agy_meta = run_agent_benchmark(
            agy_agent,
            config,
            run_dir / "agy",
            workspaces_dir,
            resume=resume,
            target_task_id=target_task_id,
        )

    if not generation_only:
        # Materialize evaluator dataset only after predictions are sealed
        eval_ds = None
        try:
            eval_ds = materialize_pinned_dataset(
                config,  # type: ignore[arg-type]
                run_dir / "dataset-evaluation",
                evaluator_only=True,
            )
        except Exception as exc:
            (run_dir / "evaluation_dataset_error.txt").write_text(str(exc), encoding="utf-8")

        if codex_meta:
            codex_preds = run_dir / "codex" / "predictions.jsonl"
            evaluate_arm(
                config,
                codex_preds,
                run_dir / "evaluation" / "codex",
                Path(eval_ds.path) if eval_ds else None,
                f"{run_dir.name}-codex",
            )
        if agy_meta:
            agy_preds = run_dir / "agy" / "predictions.jsonl"
            evaluate_arm(
                config,
                agy_preds,
                run_dir / "evaluation" / "agy",
                Path(eval_ds.path) if eval_ds else None,
                f"{run_dir.name}-agy",
            )

        build_comparison_report(config, run_dir, codex_meta, agy_meta)

    write_run_checksums(run_dir)
    return run_dir
